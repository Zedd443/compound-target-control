from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import jsonify, request

import termux_app as appmod

ROOT = Path(__file__).resolve().parent
HISTORY_FILE = ROOT / ".ctc_history.json"


def _mid_from_book(data: dict) -> float:
    bids = data.get("bids") or data.get("data", {}).get("bids")
    asks = data.get("asks") or data.get("data", {}).get("asks")
    if not bids or not asks:
        raise RuntimeError("order book kosong")
    return (float(bids[0][0]) + float(asks[0][0])) / 2


def get_usdt_idr_rate() -> tuple[float, str]:
    errors: list[str] = []

    try:
        r = requests.get(
            "https://cloudme-toko.2meta.app/api/v1/depth",
            params={"symbol": "BTCIDR"},
            timeout=8,
        )
        r.raise_for_status()
        btc_idr = _mid_from_book(r.json())
        btc_usdt = appmod.client.mark_price("BTCUSDT")
        if btc_idr > 0 and btc_usdt > 0:
            return btc_idr / btc_usdt, "Tokocrypto BTCIDR ÷ Binance BTCUSDT"
    except Exception as exc:
        errors.append(f"Tokocrypto NextMe: {exc}")

    for symbol in ("BTC_IDR", "BTCIDR"):
        try:
            r = requests.get(
                "https://www.tokocrypto.com/open/v1/market/depth",
                params={"symbol": symbol},
                timeout=8,
            )
            r.raise_for_status()
            btc_idr = _mid_from_book(r.json())
            btc_usdt = appmod.client.mark_price("BTCUSDT")
            if btc_idr > 0 and btc_usdt > 0:
                return btc_idr / btc_usdt, "Tokocrypto public BTCIDR ÷ Binance BTCUSDT"
        except Exception as exc:
            errors.append(f"Tokocrypto public {symbol}: {exc}")

    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "tether", "vs_currencies": "idr"},
            timeout=8,
            headers={"accept": "application/json", "user-agent": "compound-target-control/1.0"},
        )
        r.raise_for_status()
        rate = float(r.json()["tether"]["idr"])
        if rate > 0:
            return rate, "CoinGecko USDT/IDR"
    except Exception as exc:
        errors.append(f"CoinGecko: {exc}")

    raise RuntimeError("Semua sumber FX gagal: " + " | ".join(errors[-3:]))


def _numbers(text: str) -> list[float]:
    values: list[float] = []
    for token in re.findall(r"(?<![A-Z0-9])\d+(?:[.,]\d+)?", text.upper()):
        try:
            values.append(float(token.replace(",", ".")))
        except ValueError:
            pass
    return values


def _price_numbers(line: str, strip_label_number: bool = False) -> list[float]:
    cleaned = line.upper()
    if strip_label_number:
        cleaned = re.sub(r"\b(?:TP|TARGET)\s*\d+\b", "TP", cleaned)
    return _numbers(cleaned)


def parse_signal_v2(text: str) -> dict:
    cleaned = text.upper().replace("—", "-").replace("–", "-").strip()
    if not cleaned:
        raise ValueError("Signal kosong.")

    symbol_match = re.search(r"\b([A-Z0-9]{2,20})\s*/?\s*USDT\b", cleaned)
    if symbol_match:
        symbol = symbol_match.group(1) + "USDT"
    else:
        first_nonempty = next((x.strip() for x in cleaned.splitlines() if x.strip()), "")
        first_token = re.match(r"([A-Z0-9]{2,20})\b", first_nonempty)
        if not first_token:
            raise ValueError("Ticker coin tidak ditemukan. Contoh: PUMP LONG atau BTCUSDT LONG.")
        base = first_token.group(1)
        if base in {"LONG", "SHORT", "BUY", "SELL"}:
            raise ValueError("Ticker coin tidak ditemukan di baris pertama.")
        symbol = base if base.endswith("USDT") else base + "USDT"

    if re.search(r"\b(LONG|BUY)\b", cleaned):
        side = "LONG"
    elif re.search(r"\b(SHORT|SELL)\b", cleaned):
        side = "SHORT"
    else:
        raise ValueError("LONG/SHORT tidak ditemukan di signal.")

    entry_values: list[float] = []
    stop = None
    targets: list[float] = []
    leverage = None

    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        lev_match = re.search(r"(?:LEV(?:ERAGE)?\s*[:=]?\s*)?(\d+(?:\.\d+)?)\s*[X×]", line)
        if lev_match:
            leverage = float(lev_match.group(1))

        if re.search(r"\b(SL|STOP\s*LOSS|STOP)\b", line):
            nums = _price_numbers(line)
            if nums:
                stop = nums[-1]
            continue

        if re.search(r"\b(TP\s*\d*|TARGET\s*\d*|TAKE\s*PROFIT\s*\d*)\b", line):
            nums = _price_numbers(line, strip_label_number=True)
            if nums:
                targets.append(nums[-1])
            continue

        if re.search(r"\b(ENTRY|ENTRIES|ENTRY\s*ZONE|BUY\s*ZONE|SELL\s*ZONE)\b", line):
            nums = _price_numbers(line)
            if nums:
                entry_values.extend(nums[:2])
            continue

    targets = list(dict.fromkeys(targets))
    if not entry_values:
        raise ValueError("Entry tidak ditemukan.")
    if stop is None:
        raise ValueError("Stop loss tidak ditemukan.")
    if not targets:
        raise ValueError("Minimal satu TP tidak ditemukan.")

    entry_low = min(entry_values)
    entry_high = max(entry_values)
    entry = (entry_low + entry_high) / 2

    if side == "LONG" and stop >= entry:
        raise ValueError("Untuk LONG, SL harus di bawah entry.")
    if side == "SHORT" and stop <= entry:
        raise ValueError("Untuk SHORT, SL harus di atas entry.")

    return {
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop,
        "targets": targets,
        "leverage": leverage or 5.0,
        "leverage_source": "signal" if leverage else "default",
    }


def _load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_history(rows: list[dict]) -> None:
    HISTORY_FILE.write_text(json.dumps(rows[-2000:], ensure_ascii=False, indent=2), encoding="utf-8")


def api_plan_v2():
    try:
        data = request.get_json(force=True)
        snap = appmod.build_goal_snapshot(appmod.goal_from(data), float(data["current_equity"]), appmod.date.today())
        return jsonify({
            "ok": True,
            "baseline_equity": snap.baseline_equity,
            "progress_pct": snap.progress_pct,
            "schedule_variance_pct": snap.schedule_variance_pct,
            "days_elapsed": snap.days_elapsed,
            "days_remaining": snap.days_remaining,
            "original_daily_return": snap.original_daily_return,
            "current_daily_return": snap.current_daily_return,
            "original_monthly_return": snap.original_monthly_return,
            "current_monthly_return": snap.current_monthly_return,
            "target_pressure": snap.target_pressure,
            "status": snap.status.value,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Plan error: {exc}"}), 400


def api_history():
    if request.method == "GET":
        rows = _load_history()
        return jsonify({"ok": True, "rows": rows[-30:]})

    try:
        data = request.get_json(force=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "futures_equity": float(data.get("futures_equity", 0)),
            "copy_balance": float(data.get("copy_balance", 0)),
            "planning_usdt": float(data.get("planning_usdt", 0)),
            "fx_rate": float(data.get("fx_rate", 0)),
            "planning_idr": float(data.get("planning_idr", 0)),
            "reason": str(data.get("reason", "refresh")),
        }
        rows = _load_history()
        last = rows[-1] if rows else None
        should_append = True
        if last and row["reason"] == "refresh":
            same_values = (
                abs(float(last.get("planning_usdt", 0)) - row["planning_usdt"]) < 0.01
                and abs(float(last.get("fx_rate", 0)) - row["fx_rate"]) < 1
            )
            if same_values:
                should_append = False
        if should_append:
            rows.append(row)
            _save_history(rows)
        return jsonify({"ok": True, "saved": should_append})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"History error: {exc}"}), 400


appmod.get_usdt_idr_rate = get_usdt_idr_rate
appmod.parse_signal = parse_signal_v2
appmod.app.view_functions["api_plan"] = api_plan_v2
appmod.app.add_url_rule("/api/history", "api_history", api_history, methods=["GET", "POST"])

old_mission = '''<div id="mission" class="tabpane"><div class="grid"><div class="card metric"><small>Current Equity</small><b id="mCurrent">—</b></div><div class="card metric"><small>Target</small><b id="mTarget">—</b></div><div class="card metric"><small>Required Monthly</small><b id="mReq">—</b></div><div class="card metric"><small>Target Pressure</small><b id="mPressure">—</b></div><div class="card metric"><small>Drawdown</small><b id="mDD">—</b></div><div class="card metric"><small>Open Risk</small><b id="mOpenRisk">—</b></div></div></div>'''
new_mission = '''<div id="mission" class="tabpane"><div class="grid"><div class="card metric"><small>Current Equity</small><b id="mCurrent">—</b></div><div class="card metric"><small>Final Target</small><b id="mTarget">—</b></div><div class="card metric"><small>Target Today</small><b id="mToday">—</b></div><div class="card metric"><small>Gap vs Target Today</small><b id="mGap">—</b></div><div class="card metric"><small>Required Daily</small><b id="mDaily">—</b></div><div class="card metric"><small>Required Monthly</small><b id="mReq">—</b></div><div class="card metric"><small>Original Daily</small><b id="mOrigDaily">—</b></div><div class="card metric"><small>Target Pressure</small><b id="mPressure">—</b></div><div class="card metric"><small>Progress to Final</small><b id="mProgress">—</b></div><div class="card metric"><small>Days Left</small><b id="mDays">—</b></div><div class="card metric"><small>Drawdown</small><b id="mDD">—</b></div><div class="card metric"><small>Open Risk</small><b id="mOpenRisk">—</b></div></div><div class="card section"><small class="muted">Target Pressure = required monthly sekarang ÷ required monthly awal. 1.00× berarti sesuai pace awal; di atas 1× berarti pace yang dibutuhkan meningkat.</small></div><div class="card section"><h3>Recent Tracking</h3><div id="historyRows" class="notice">Belum ada snapshot.</div></div></div>'''
appmod.HTML = appmod.HTML.replace(old_mission, new_mission)

old_save = "function copyBalance(){return Number(localStorage.getItem('ctc_copy_balance')||0)}function saveCopyBalance(){localStorage.setItem('ctc_copy_balance',Number($('copyBalance').value||0));refreshAll()}function planningUsdt(){return (acct?acct.equity:0)+copyBalance()}function planningIdr(){return fxRate?planningUsdt()*fxRate:0}"
new_save = "function copyBalance(){return Number(localStorage.getItem('ctc_copy_balance')||0)}async function saveCopyBalance(){localStorage.setItem('ctc_copy_balance',Number($('copyBalance').value||0));await refreshAll();await recordSnapshot('copy_balance')}function planningUsdt(){return (acct?acct.equity:0)+copyBalance()}function planningIdr(){return fxRate?planningUsdt()*fxRate:0}async function recordSnapshot(reason='refresh'){if(!acct||!fxRate)return;try{await fetchJson('/api/history',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({futures_equity:acct.equity,copy_balance:copyBalance(),planning_usdt:planningUsdt(),fx_rate:fxRate,planning_idr:planningIdr(),reason})})}catch(e){}}async function loadHistory(){try{const h=await fetchJson('/api/history');if(!$('historyRows'))return;const rows=h.rows||[];if(!rows.length){$('historyRows').textContent='Belum ada snapshot.';return}$('historyRows').innerHTML=rows.slice(-8).reverse().map(x=>'<div style=\"padding:6px 0;border-bottom:1px solid var(--line)\"><b>'+new Date(x.ts).toLocaleString('id-ID')+'</b> · '+fmtU(x.planning_usdt)+' · '+fmtI(x.planning_idr)+'</div>').join('')}catch(e){}}"
appmod.HTML = appmod.HTML.replace(old_save, new_save)

old_refresh_plan = "async function refreshPlan(p){const current=planningIdr();lastPlanSnapshot=await fetchJson('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,current_equity:current})});const dd=updatePeak();$('mCurrent').textContent=fmtI(current);$('mTarget').textContent=fmtI(p.target_equity);$('mReq').textContent=pct(lastPlanSnapshot.current_monthly_return);$('mPressure').textContent=Number(lastPlanSnapshot.target_pressure).toFixed(2)+'×';$('mDD').textContent=pct(dd);$('mOpenRisk').textContent=pct(acct.open_risk_pct);$('pStart').textContent=fmtI(p.start_equity);$('pStartDate').textContent=p.start_date;$('pTargetDate').textContent=p.target_date}"
new_refresh_plan = "async function refreshPlan(p){const current=planningIdr();lastPlanSnapshot=await fetchJson('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,current_equity:current})});const dd=updatePeak(),gap=current-lastPlanSnapshot.baseline_equity;$('mCurrent').textContent=fmtI(current);$('mTarget').textContent=fmtI(p.target_equity);$('mToday').textContent=fmtI(lastPlanSnapshot.baseline_equity);$('mGap').textContent=(gap>=0?'+':'')+fmtI(gap);$('mDaily').textContent=pct(lastPlanSnapshot.current_daily_return);$('mReq').textContent=pct(lastPlanSnapshot.current_monthly_return);$('mOrigDaily').textContent=pct(lastPlanSnapshot.original_daily_return);$('mPressure').textContent=Number(lastPlanSnapshot.target_pressure).toFixed(2)+'×';$('mProgress').textContent=pct(lastPlanSnapshot.progress_pct);$('mDays').textContent=lastPlanSnapshot.days_remaining+' hari';$('mDD').textContent=pct(dd);$('mOpenRisk').textContent=pct(acct.open_risk_pct);$('pStart').textContent=fmtI(p.start_equity);$('pStartDate').textContent=p.start_date;$('pTargetDate').textContent=p.target_date;await loadHistory()}"
appmod.HTML = appmod.HTML.replace(old_refresh_plan, new_refresh_plan)

old_refresh_end = "if(p){$('createPlan').classList.add('hidden');$('planView').classList.remove('hidden');await refreshPlan(p)}else{$('createPlan').classList.remove('hidden');$('planView').classList.add('hidden')}}catch(e)"
new_refresh_end = "if(p){$('createPlan').classList.add('hidden');$('planView').classList.remove('hidden');await refreshPlan(p);await recordSnapshot('refresh')}else{$('createPlan').classList.remove('hidden');$('planView').classList.add('hidden')}}catch(e)"
appmod.HTML = appmod.HTML.replace(old_refresh_end, new_refresh_end)

old_tp = "$('tpRows').innerHTML=result.partial.targets.map(x=>'<div class=\"tp\"><b>'+x.name+' · '+Number(x.price).toLocaleString('en-US')+'</b><span>'+Number(x.r_multiple).toFixed(2)+'R</span><b>'+Math.round(x.fraction*100)+'%</b></div>').join('');"
new_tp = "$('tpRows').innerHTML=result.partial.targets.map(x=>{const gain=(signal.side==='LONG'?(x.price-signal.entry):(signal.entry-x.price))/signal.entry;return '<div class=\"tp\"><b>'+x.name+' · '+Number(x.price).toLocaleString('en-US')+'</b><span>'+Number(x.r_multiple).toFixed(2)+'R · '+(gain*100).toFixed(2)+'%</span><b>'+Math.round(x.fraction*100)+'%</b></div>'}).join('');"
appmod.HTML = appmod.HTML.replace(old_tp, new_tp)

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
