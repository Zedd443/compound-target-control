from __future__ import annotations

from datetime import date
from pathlib import Path
import math
import re
import sys

import requests
from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from compound_control.config import load_config
from compound_control.domain.models import Goal, TradeSetup, VolatilityRegime
from compound_control.exchange.binance.client import BinanceApiError, BinanceUsdMReadOnlyClient
from compound_control.goals.compound import build_goal_snapshot
from compound_control.risk.controller import RiskController
from compound_control.services.planner import PlanningService

app = Flask(__name__)
config = load_config(ROOT / "config/settings.yaml")
client = BinanceUsdMReadOnlyClient.from_sources()
planner = PlanningService(
    risk_controller=RiskController(config.risk),
    execution_config=config.execution,
)


def account_state() -> dict:
    account = client.account()
    equity = float(account.get("totalMarginBalance", account.get("totalWalletBalance", 0)))
    available = float(account.get("availableBalance", 0))
    unrealized = float(account.get("totalUnrealizedProfit", 0))
    if equity <= 0 and "totalMarginBalance" not in account and "totalWalletBalance" not in account:
        raise BinanceApiError("Unexpected Binance account response.")

    open_risk_usdt, missing_stops = calculate_open_risk(equity)
    return {
        "equity": equity,
        "available": available,
        "unrealized": unrealized,
        "open_risk_usdt": open_risk_usdt,
        "open_risk_pct": (open_risk_usdt / equity) if equity > 0 else 0.0,
        "missing_stop_symbols": missing_stops,
    }


def calculate_open_risk(equity: float) -> tuple[float, list[str]]:
    positions = [p for p in client.positions() if abs(float(p.get("positionAmt", 0))) > 0]
    if not positions:
        return 0.0, []
    orders = client.open_orders()
    total_loss = 0.0
    missing: list[str] = []

    for position in positions:
        symbol = str(position.get("symbol", ""))
        qty = abs(float(position.get("positionAmt", 0)))
        entry = float(position.get("entryPrice", 0))
        is_long = float(position.get("positionAmt", 0)) > 0
        candidates = []
        for order in orders:
            if order.get("symbol") != symbol:
                continue
            if str(order.get("type", "")).upper() not in {"STOP", "STOP_MARKET", "STOP_LOSS", "STOP_LOSS_LIMIT"}:
                continue
            stop = float(order.get("stopPrice", 0) or 0)
            side = str(order.get("side", "")).upper()
            if stop <= 0:
                continue
            if is_long and side == "SELL" and stop < entry:
                candidates.append(stop)
            elif not is_long and side == "BUY" and stop > entry:
                candidates.append(stop)
        if not candidates:
            missing.append(symbol)
            continue
        stop = max(candidates) if is_long else min(candidates)
        total_loss += abs(entry - stop) * qty

    return total_loss, missing


def get_usdt_idr_rate() -> tuple[float, str]:
    # Implied USDT/IDR = BTC/IDR midpoint on Tokocrypto divided by BTC/USDT mark on Binance.
    url = "https://cloudme-toko.2meta.app/api/v1/depth"
    response = requests.get(url, params={"symbol": "BTCIDR", "limit": 5}, timeout=8)
    response.raise_for_status()
    data = response.json()
    bids = data.get("bids") or data.get("data", {}).get("bids")
    asks = data.get("asks") or data.get("data", {}).get("asks")
    if not bids or not asks:
        raise RuntimeError("Tokocrypto BTCIDR order book unavailable")
    btc_idr = (float(bids[0][0]) + float(asks[0][0])) / 2
    btc_usdt = client.mark_price("BTCUSDT")
    if btc_idr <= 0 or btc_usdt <= 0:
        raise RuntimeError("Invalid market price for FX calculation")
    return btc_idr / btc_usdt, "Tokocrypto BTCIDR ÷ Binance BTCUSDT"


def volatility_context(symbol: str) -> dict:
    candles = client.klines(symbol, interval="1h", limit=120)
    if len(candles) < 30:
        return {"regime": "normal", "atr_pct": None, "percentile": None}

    trs: list[float] = []
    closes: list[float] = []
    previous_close = None
    for candle in candles:
        high = float(candle[2])
        low = float(candle[3])
        close = float(candle[4])
        if previous_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
        trs.append(tr)
        closes.append(close)
        previous_close = close

    atr_series: list[float] = []
    for i in range(13, len(trs)):
        atr = sum(trs[i - 13 : i + 1]) / 14
        if closes[i] > 0:
            atr_series.append(atr / closes[i])
    current = atr_series[-1]
    percentile = sum(1 for value in atr_series if value <= current) / len(atr_series)
    if percentile <= 0.25:
        regime = "low"
    elif percentile <= 0.75:
        regime = "normal"
    elif percentile <= 0.90:
        regime = "high"
    else:
        regime = "extreme"
    return {"regime": regime, "atr_pct": current, "percentile": percentile}


def parse_numbers(text: str) -> list[float]:
    values = []
    for raw in re.findall(r"\d+(?:[.,]\d+)?", text):
        token = raw.replace(",", ".")
        try:
            values.append(float(token))
        except ValueError:
            pass
    return values


def parse_signal(text: str) -> dict:
    cleaned = text.upper().replace("—", "-").replace("–", "-")
    symbol_match = re.search(r"\b([A-Z0-9]{2,12})\s*/?\s*USDT\b", cleaned)
    if not symbol_match:
        raise ValueError("Symbol USDT tidak ditemukan. Contoh: BTCUSDT atau BTC/USDT.")
    symbol = symbol_match.group(1) + "USDT"

    if re.search(r"\bLONG\b|\bBUY\b", cleaned):
        side = "LONG"
    elif re.search(r"\bSHORT\b|\bSELL\b", cleaned):
        side = "SHORT"
    else:
        raise ValueError("LONG/SHORT tidak ditemukan di signal.")

    entry_values: list[float] = []
    stop = None
    targets: list[float] = []
    leverage = None

    for line in cleaned.splitlines():
        line = line.strip()
        nums = parse_numbers(line)
        if not nums:
            continue
        if re.search(r"\b(SL|STOP\s*LOSS|STOP)\b", line):
            stop = nums[-1]
            continue
        if re.search(r"\b(TP\s*\d*|TARGET\s*\d*|TAKE\s*PROFIT\s*\d*)\b", line):
            # Remove TP numbering such as TP1 before reading the price.
            price_candidates = [n for n in nums if n > 10]
            if price_candidates:
                targets.append(price_candidates[-1])
            continue
        if re.search(r"\b(ENTRY|ENTRIES|ENTRY\s*ZONE|BUY\s*ZONE|SELL\s*ZONE)\b", line):
            price_candidates = [n for n in nums if n > 10]
            entry_values.extend(price_candidates[:2])
            continue
        lev_match = re.search(r"(?:LEV(?:ERAGE)?\s*[:=]?\s*)?(\d+(?:\.\d+)?)\s*[X×]", line)
        if lev_match:
            leverage = float(lev_match.group(1))

    if not entry_values:
        entry_match = re.search(r"ENTRY[^\n\r]*", cleaned)
        if entry_match:
            entry_values = [n for n in parse_numbers(entry_match.group(0)) if n > 10][:2]
    if stop is None:
        stop_match = re.search(r"(?:SL|STOP(?:\s*LOSS)?)[^\n\r]*", cleaned)
        if stop_match:
            candidates = [n for n in parse_numbers(stop_match.group(0)) if n > 10]
            if candidates:
                stop = candidates[-1]

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


def adaptive_partial_plan(side: str, entry: float, stop: float, targets: list[float], pressure: float, drawdown: float, volatility: str) -> dict:
    n = len(targets)
    if n == 0:
        return {"profile": "none", "runner_fraction": 0.0, "targets": [], "weighted_r": 0.0}

    aggressive = pressure >= 1.05 and drawdown < 0.05 and volatility in {"low", "normal"}
    defensive = pressure <= 0.95 or drawdown >= 0.05 or volatility in {"high", "extreme"}

    if aggressive:
        profile = "growth"
        runner = 0.15
        raw = list(range(1, n + 1))
    elif defensive:
        profile = "protect"
        runner = 0.10
        raw = list(range(n, 0, -1))
    else:
        profile = "balanced"
        runner = 0.10
        raw = [1] * n

    total_raw = sum(raw)
    fractions = [(1 - runner) * x / total_raw for x in raw]
    risk_distance = abs(entry - stop)
    rows = []
    weighted_r = 0.0
    for index, (target, fraction) in enumerate(zip(targets, fractions), start=1):
        if risk_distance <= 0:
            r_multiple = 0.0
        elif side == "LONG":
            r_multiple = (target - entry) / risk_distance
        else:
            r_multiple = (entry - target) / risk_distance
        weighted_r += fraction * r_multiple
        rows.append({
            "name": f"TP{index}",
            "price": target,
            "fraction": fraction,
            "r_multiple": r_multiple,
        })
    return {
        "profile": profile,
        "runner_fraction": runner,
        "targets": rows,
        "weighted_r": weighted_r,
    }


def goal_from(data: dict) -> Goal:
    return Goal(
        start_equity=float(data["start_equity"]),
        target_equity=float(data["target_equity"]),
        start_date=date.fromisoformat(data["start_date"]),
        target_date=date.fromisoformat(data["target_date"]),
        reporting_currency="IDR",
    )


@app.get("/api/account")
def api_account():
    try:
        return jsonify({"ok": True, **account_state()})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Backend error: {type(exc).__name__}: {exc}"}), 502


@app.get("/api/fx")
def api_fx():
    try:
        rate, source = get_usdt_idr_rate()
        return jsonify({"ok": True, "rate": rate, "source": source})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"FX error: {exc}"}), 502


@app.get("/api/market/<symbol>")
def api_market(symbol: str):
    try:
        vol = volatility_context(symbol)
        return jsonify({"ok": True, "mark_price": client.mark_price(symbol), **vol})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Market error: {exc}"}), 502


@app.post("/api/parse-signal")
def api_parse_signal():
    try:
        data = request.get_json(force=True)
        parsed = parse_signal(str(data.get("text", "")))
        return jsonify({"ok": True, **parsed})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/plan")
def api_plan():
    try:
        data = request.get_json(force=True)
        snapshot = build_goal_snapshot(goal_from(data), float(data["current_equity"]), date.today())
        return jsonify({
            "ok": True,
            "baseline_equity": snapshot.baseline_equity,
            "progress_pct": snapshot.progress_pct,
            "schedule_variance_pct": snapshot.schedule_variance_pct,
            "days_remaining": snapshot.days_remaining,
            "original_monthly_return": snapshot.original_monthly_return,
            "current_monthly_return": snapshot.current_monthly_return,
            "target_pressure": snapshot.target_pressure,
            "status": snapshot.status.value,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Plan error: {exc}"}), 400


@app.post("/api/size")
def api_size():
    try:
        data = request.get_json(force=True)
        parsed = data["signal"]
        symbol = str(parsed["symbol"]).upper()
        market = volatility_context(symbol)
        setup = TradeSetup(
            symbol=symbol,
            side=str(parsed["side"]).upper(),
            entry=float(parsed["entry"]),
            stop_loss=float(parsed["stop_loss"]),
            leverage=float(parsed.get("leverage", 5.0)),
        )
        result = planner.plan_trade(
            goal=goal_from(data),
            reporting_equity=float(data["reporting_equity"]),
            trading_equity=float(data["trading_equity"]),
            as_of=date.today(),
            drawdown_pct=float(data.get("drawdown_pct", 0.0)),
            volatility_regime=VolatilityRegime(market["regime"]),
            open_risk_pct=float(data.get("open_risk_pct", 0.0)),
            setup=setup,
        )
        partial = adaptive_partial_plan(
            setup.side,
            setup.entry,
            setup.stop_loss,
            [float(x) for x in parsed.get("targets", [])],
            result.goal.target_pressure,
            float(data.get("drawdown_pct", 0.0)),
            market["regime"],
        )
        return jsonify({
            "ok": True,
            "effective_risk_pct": result.risk.effective_risk_pct,
            "max_planned_loss": result.position.risk_budget,
            "recommended_notional": result.position.recommended_notional,
            "required_margin": result.position.required_margin,
            "stop_distance_pct": result.position.stop_distance_pct,
            "estimated_loss_at_stop": result.position.estimated_loss_at_stop,
            "account_risk_pct": result.position.account_risk_pct,
            "target_pressure": result.goal.target_pressure,
            "volatility": market,
            "partial": partial,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Sizing error: {type(exc).__name__}: {exc}"}), 400


@app.get("/")
def home():
    return HTML


HTML = r'''<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0f14"><title>Compound Target Control</title>
<style>
:root{color-scheme:dark;--bg:#0b0f14;--card:#121821;--muted:#8d97a6;--line:#202938;--accent:#5aa7ff;--ok:#4cc38a;--bad:#ff7272}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#f4f7fb;font-family:system-ui,-apple-system,Segoe UI,sans-serif}.wrap{max-width:760px;margin:auto;padding:18px 14px 44px}.head{display:flex;justify-content:space-between;align-items:center;gap:12px}.title{font-size:26px;font-weight:800}.sub,.muted{color:var(--muted);font-size:12px}.btn{border:0;border-radius:12px;padding:12px 14px;background:#1b2635;color:#fff;font-weight:700}.primary{background:var(--accent);color:#07101d}.danger{background:#3a1d22;color:#ffb3b3}.status,.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px}.status{margin:16px 0}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.metric small{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}.metric b{font-size:19px}.section{margin-top:14px}.tabs{display:flex;gap:8px;margin:14px 0}.tab{flex:1}.tab.active{background:#29415f}.hidden{display:none}.field{margin-bottom:11px}.field label{display:block;color:var(--muted);font-size:12px;margin-bottom:6px}input,textarea{width:100%;border:1px solid var(--line);border-radius:11px;background:#0d131b;color:#fff;padding:12px;font-size:16px}textarea{min-height:170px;resize:vertical}.wide{width:100%}.good{color:var(--ok)}.bad{color:var(--bad)}.tp{display:grid;grid-template-columns:1fr .8fr .8fr;gap:8px;padding:9px 0;border-bottom:1px solid var(--line);font-size:13px}.notice{font-size:12px;color:var(--muted);margin-top:8px;overflow-wrap:anywhere}@media(max-width:480px){.title{font-size:23px}.metric b{font-size:17px}}
</style></head>
<body><div class="wrap">
<div class="head"><div><div class="title">Compound Target Control</div><div class="sub">Termux · Binance read-only · auto risk context</div></div><button class="btn" onclick="refreshAll()">Refresh</button></div>
<div id="status" class="status">Connecting...</div>
<div class="grid">
<div class="card metric"><small>Futures Equity</small><b id="eq">—</b></div><div class="card metric"><small>Available</small><b id="avail">—</b></div>
<div class="card metric"><small>Planning Equity</small><b id="planningEq">—</b></div><div class="card metric"><small>USDT → IDR</small><b id="fx">—</b></div>
</div>
<div class="card section"><div class="field"><label>Copy Trading balance (USDT, manual karena standard Futures API tidak membacanya)</label><input id="copyBalance" type="number" step="0.01" value="0"></div><button class="btn wide" onclick="saveCopyBalance()">Save copy balance</button><div id="accountNote" class="notice"></div></div>

<div id="createPlan" class="card section hidden"><h3>Buat Target</h3><div class="field"><label>Target Equity (IDR)</label><input id="target" type="number" value="10000000000"></div><div class="field"><label>Horizon (bulan)</label><input id="months" type="number" min="1" max="240" value="24"></div><button class="btn primary wide" onclick="startPlan()">Start Plan</button></div>

<div id="planView" class="hidden"><div class="tabs"><button class="btn tab active" onclick="showTab('mission',this)">Mission</button><button class="btn tab" onclick="showTab('trade',this)">Trade</button><button class="btn tab" onclick="showTab('plan',this)">Plan</button></div>
<div id="mission" class="tabpane"><div class="grid"><div class="card metric"><small>Current Equity</small><b id="mCurrent">—</b></div><div class="card metric"><small>Target</small><b id="mTarget">—</b></div><div class="card metric"><small>Required Monthly</small><b id="mReq">—</b></div><div class="card metric"><small>Target Pressure</small><b id="mPressure">—</b></div><div class="card metric"><small>Drawdown</small><b id="mDD">—</b></div><div class="card metric"><small>Open Risk</small><b id="mOpenRisk">—</b></div></div></div>
<div id="trade" class="tabpane hidden"><div class="card"><div class="field"><label>Paste signal</label><textarea id="signalText" placeholder="BTCUSDT LONG\nENTRY 68000-68200\nSL 66500\nTP1 69500\nTP2 71000\nTP3 73500\n10X"></textarea></div><button class="btn primary wide" onclick="parseAndSize()">Parse & Calculate</button><div id="parsed" class="notice"></div></div><div id="tradeResult" class="hidden"><div class="grid section"><div class="card metric"><small>Effective R</small><b id="rEff">—</b></div><div class="card metric"><small>Max Planned Loss</small><b id="maxLoss">—</b></div><div class="card metric"><small>Notional</small><b id="notional">—</b></div><div class="card metric"><small>Margin</small><b id="margin">—</b></div><div class="card metric"><small>Volatility</small><b id="vol">—</b></div><div class="card metric"><small>Stop Distance</small><b id="stopDist">—</b></div></div><div class="card section"><h3>Adaptive Partial Plan</h3><div id="partialProfile" class="notice"></div><div id="tpRows"></div><div class="tp"><b>Runner</b><span>open</span><b id="runner">—</b></div><div class="notice">Weighted R hanya menghitung TP yang punya harga; runner belum diberi outcome.</div></div></div></div>
<div id="plan" class="tabpane hidden"><div class="card"><div class="metric"><small>Start Equity</small><b id="pStart">—</b></div><br><div class="metric"><small>Start Date</small><b id="pStartDate">—</b></div><br><div class="metric"><small>Target Date</small><b id="pTargetDate">—</b></div><br><button class="btn danger wide" onclick="resetPlan()">Reset Plan</button></div></div></div>
<div class="notice" style="text-align:center;margin-top:18px">Target pressure dapat mengubah risk dan distribusi partial, bukan memindahkan harga TP signal.</div>
</div>
<script>
let acct=null,fxRate=null,fxSource='',lastPlanSnapshot=null;
const $=id=>document.getElementById(id),fmtU=n=>Number(n).toLocaleString('en-US',{maximumFractionDigits:2})+' USDT',fmtI=n=>'Rp'+Math.round(Number(n)).toLocaleString('id-ID'),pct=n=>(Number(n)*100).toFixed(2)+'%';
function planData(){return JSON.parse(localStorage.getItem('ctc_plan')||'null')}function today(){return new Date().toISOString().slice(0,10)}function addMonths(s,m){const d=new Date(s+'T00:00:00'),day=d.getDate();d.setDate(1);d.setMonth(d.getMonth()+Number(m));d.setDate(Math.min(day,new Date(d.getFullYear(),d.getMonth()+1,0).getDate()));return d.toISOString().slice(0,10)}
async function fetchJson(url,opt){const r=await fetch(url,opt),t=await r.text();let d;try{d=JSON.parse(t)}catch(e){throw new Error('Backend non-JSON HTTP '+r.status)}if(!d.ok)throw new Error(d.error||('HTTP '+r.status));return d}
function copyBalance(){return Number(localStorage.getItem('ctc_copy_balance')||0)}function saveCopyBalance(){localStorage.setItem('ctc_copy_balance',Number($('copyBalance').value||0));refreshAll()}function planningUsdt(){return (acct?acct.equity:0)+copyBalance()}function planningIdr(){return fxRate?planningUsdt()*fxRate:0}
function updatePeak(){const cur=planningUsdt();let peak=Number(localStorage.getItem('ctc_peak_equity')||0);if(cur>peak){peak=cur;localStorage.setItem('ctc_peak_equity',peak)}return peak>0?Math.max((peak-cur)/peak,0):0}
async function refreshAll(){try{$('status').textContent='Refreshing...';acct=await fetchJson('/api/account');const f=await fetchJson('/api/fx');fxRate=f.rate;fxSource=f.source;$('copyBalance').value=copyBalance();$('eq').textContent=fmtU(acct.equity);$('avail').textContent=fmtU(acct.available);$('planningEq').textContent=fmtU(planningUsdt())+' · '+fmtI(planningIdr());$('fx').textContent='Rp'+Math.round(fxRate).toLocaleString('id-ID');$('accountNote').textContent='FX: '+fxSource+(acct.missing_stop_symbols.length?' · posisi tanpa SL terdeteksi: '+acct.missing_stop_symbols.join(', '):'');$('status').innerHTML='<span class="good">Connected</span> · live Binance + market FX';const p=planData();if(p){$('createPlan').classList.add('hidden');$('planView').classList.remove('hidden');await refreshPlan(p)}else{$('createPlan').classList.remove('hidden');$('planView').classList.add('hidden')}}catch(e){$('status').innerHTML='<span class="bad">'+e.message+'</span>'}}
async function startPlan(){if(!acct||!fxRate)return;const p={start_equity:planningIdr(),target_equity:Number($('target').value),start_date:today(),target_date:addMonths(today(),$('months').value)};localStorage.setItem('ctc_plan',JSON.stringify(p));localStorage.setItem('ctc_peak_equity',planningUsdt());await refreshAll()}
async function refreshPlan(p){const current=planningIdr();lastPlanSnapshot=await fetchJson('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,current_equity:current})});const dd=updatePeak();$('mCurrent').textContent=fmtI(current);$('mTarget').textContent=fmtI(p.target_equity);$('mReq').textContent=pct(lastPlanSnapshot.current_monthly_return);$('mPressure').textContent=Number(lastPlanSnapshot.target_pressure).toFixed(2)+'×';$('mDD').textContent=pct(dd);$('mOpenRisk').textContent=pct(acct.open_risk_pct);$('pStart').textContent=fmtI(p.start_equity);$('pStartDate').textContent=p.start_date;$('pTargetDate').textContent=p.target_date}
async function parseAndSize(){try{const p=planData();if(!p)throw new Error('Start Plan dulu.');const signal=await fetchJson('/api/parse-signal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:$('signalText').value})});$('parsed').textContent=signal.symbol+' '+signal.side+' · Entry '+signal.entry+(signal.entry_low!==signal.entry_high?' ('+signal.entry_low+'-'+signal.entry_high+')':'')+' · SL '+signal.stop_loss+' · '+signal.targets.length+' TP · '+signal.leverage+'x '+signal.leverage_source;const dd=updatePeak();const result=await fetchJson('/api/size',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,reporting_equity:planningIdr(),trading_equity:acct.equity,drawdown_pct:dd,open_risk_pct:acct.open_risk_pct,signal})});$('tradeResult').classList.remove('hidden');$('rEff').textContent=pct(result.effective_risk_pct);$('maxLoss').textContent=fmtU(result.max_planned_loss);$('notional').textContent=fmtU(result.recommended_notional);$('margin').textContent=fmtU(result.required_margin);$('vol').textContent=result.volatility.regime.toUpperCase()+(result.volatility.atr_pct?' · ATR '+pct(result.volatility.atr_pct):'');$('stopDist').textContent=pct(result.stop_distance_pct);$('partialProfile').textContent='Profile: '+result.partial.profile+' · Target pressure '+Number(result.target_pressure).toFixed(2)+'× · Weighted listed-TP R '+Number(result.partial.weighted_r).toFixed(2)+'R';$('tpRows').innerHTML=result.partial.targets.map(x=>'<div class="tp"><b>'+x.name+' · '+Number(x.price).toLocaleString('en-US')+'</b><span>'+Number(x.r_multiple).toFixed(2)+'R</span><b>'+Math.round(x.fraction*100)+'%</b></div>').join('');$('runner').textContent=Math.round(result.partial.runner_fraction*100)+'%'}catch(e){$('parsed').innerHTML='<span class="bad">'+e.message+'</span>'}}
function resetPlan(){localStorage.removeItem('ctc_plan');localStorage.removeItem('ctc_peak_equity');refreshAll()}function showTab(id,btn){document.querySelectorAll('.tabpane').forEach(x=>x.classList.add('hidden'));document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));$(id).classList.remove('hidden');btn.classList.add('active')}refreshAll();
</script></body></html>'''


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8501, debug=False)
