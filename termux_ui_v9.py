from __future__ import annotations

from datetime import datetime, timezone

from flask import jsonify

import ctc_store
import termux_ui_v8 as base

appmod = base.appmod
ctc_store.init_db()


def _ms(iso_text: str) -> int:
    dt = datetime.fromisoformat(str(iso_text).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _reconcile_one(trade: dict) -> dict:
    symbol = str(trade["symbol"]).upper()
    side = str(trade["side"]).upper()
    entry_side = "BUY" if side == "LONG" else "SELL"
    exit_side = "SELL" if side == "LONG" else "BUY"
    created_ms = _ms(trade["created_at"])
    start_ms = max(created_ms - 120_000, 0)

    fills = appmod.client.user_trades(symbol, start_time=start_ms, limit=1000)
    fills = sorted(fills, key=lambda x: (int(x.get("time", 0)), int(x.get("id", 0))))

    low = float(trade.get("entry_low") or trade["entry"])
    high = float(trade.get("entry_high") or trade["entry"])
    tolerance = max((high - low) * 0.5, float(trade["entry"]) * 0.01)
    min_entry = low - tolerance
    max_entry = high + tolerance

    first_idx = None
    for i, fill in enumerate(fills):
        if str(fill.get("side", "")).upper() != entry_side:
            continue
        price = float(fill.get("price", 0) or 0)
        if min_entry <= price <= max_entry:
            first_idx = i
            break

    if first_idx is None:
        ctc_store.update_trade_reconciliation(
            trade["id"],
            {"reconcile_status": "pending", "match_note": "Belum menemukan fill entry Binance yang cocok."},
        )
        return {"trade_id": trade["id"], "status": "pending"}

    relevant = []
    open_qty = 0.0
    max_open_qty = 0.0
    closed = False
    ambiguous = False
    eps = 1e-12

    for fill in fills[first_idx:]:
        fill_side = str(fill.get("side", "")).upper()
        qty = abs(float(fill.get("qty", 0) or 0))
        if qty <= 0 or fill_side not in {entry_side, exit_side}:
            continue
        relevant.append(fill)
        if fill_side == entry_side:
            open_qty += qty
            max_open_qty = max(max_open_qty, open_qty)
        else:
            open_qty -= qty
            if open_qty < -max(max_open_qty * 1e-6, eps):
                ambiguous = True
                break
            if max_open_qty > 0 and open_qty <= max(max_open_qty * 1e-6, eps):
                open_qty = 0.0
                closed = True
                break

    if not relevant:
        return {"trade_id": trade["id"], "status": "pending"}

    entry_fills = [f for f in relevant if str(f.get("side", "")).upper() == entry_side]
    exit_fills = [f for f in relevant if str(f.get("side", "")).upper() == exit_side]
    entry_qty = sum(abs(float(f.get("qty", 0) or 0)) for f in entry_fills)
    exit_qty = sum(abs(float(f.get("qty", 0) or 0)) for f in exit_fills)
    actual_entry = (
        sum(float(f.get("price", 0) or 0) * abs(float(f.get("qty", 0) or 0)) for f in entry_fills) / entry_qty
        if entry_qty > 0 else None
    )
    actual_exit = (
        sum(float(f.get("price", 0) or 0) * abs(float(f.get("qty", 0) or 0)) for f in exit_fills) / exit_qty
        if exit_qty > 0 else None
    )
    gross = sum(float(f.get("realizedPnl", 0) or 0) for f in relevant)
    commission = sum(
        float(f.get("commission", 0) or 0)
        for f in relevant
        if str(f.get("commissionAsset", "USDT")).upper() == "USDT"
    )
    first_time = int(relevant[0].get("time", created_ms))
    last_time = int(relevant[-1].get("time", first_time))

    funding = 0.0
    if closed:
        try:
            incomes = appmod.client.income_history(
                symbol=symbol,
                income_type="FUNDING_FEE",
                start_time=first_time,
                end_time=last_time + 1,
                limit=1000,
            )
            funding = sum(float(x.get("income", 0) or 0) for x in incomes)
        except Exception:
            funding = 0.0

    net = gross - commission + funding
    planned_loss = float(trade.get("max_planned_loss", 0) or 0)
    realized_r = net / planned_loss if planned_loss > 0 else None

    highest_tp = 0
    if exit_fills:
        if side == "LONG":
            best_exit = max(float(f.get("price", 0) or 0) for f in exit_fills)
            highest_tp = max([int(t["target_no"]) for t in trade.get("targets", []) if best_exit >= float(t["price"])] or [0])
        else:
            best_exit = min(float(f.get("price", 0) or 0) for f in exit_fills)
            highest_tp = max([int(t["target_no"]) for t in trade.get("targets", []) if best_exit <= float(t["price"])] or [0])

    if ambiguous:
        status = "needs_review"
        trade_status = "open"
        note = "Fill berbalik melewati quantity entry; kemungkinan re-entry/position flip. Perlu review."
    elif closed:
        status = "closed"
        trade_status = "closed"
        note = "Matched otomatis dari Binance Futures fills."
    else:
        status = "matched"
        trade_status = "open"
        note = "Entry Binance sudah cocok; posisi belum tertutup penuh."

    values = {
        "status": trade_status,
        "reconcile_status": status,
        "matched_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": datetime.fromtimestamp(last_time / 1000, tz=timezone.utc).isoformat() if closed else None,
        "actual_entry": actual_entry,
        "actual_exit": actual_exit,
        "actual_qty": max_open_qty,
        "gross_realized_pnl": gross,
        "commission": commission,
        "funding": funding,
        "net_pnl": net,
        "realized_r": realized_r,
        "highest_tp_hit": highest_tp,
        "duration_seconds": max(int((last_time - first_time) / 1000), 0),
        "match_note": note,
        "binance_first_trade_id": str(relevant[0].get("id", "")),
        "binance_last_trade_id": str(relevant[-1].get("id", "")),
    }
    ctc_store.update_trade_reconciliation(trade["id"], values)
    return {"trade_id": trade["id"], "status": status, "net_pnl": net, "realized_r": realized_r}


def api_reconcile_trades():
    results = []
    errors = []
    for trade in ctc_store.list_reconcilable_trades(100):
        try:
            results.append(_reconcile_one(trade))
        except Exception as exc:
            errors.append({"trade_id": trade.get("id"), "error": str(exc)})
    return jsonify({"ok": not errors, "results": results, "errors": errors})


appmod.app.add_url_rule("/api/trades/reconcile", "api_reconcile_trades_v9", api_reconcile_trades, methods=["POST"])

# Add one explicit sync control. A light auto-sync also runs while the page is visible.
needle = '<button id="saveTradeBtn" class="btn wide hidden" onclick="saveTrade()">Save Trade</button><div id="saveTradeNote" class="notice hidden"></div>'
replacement = needle + '<button class="btn wide" style="margin-top:8px" onclick="syncTradeResults(false)">Sync Binance Results</button><div id="syncTradeNote" class="notice"></div>'
appmod.HTML = appmod.HTML.replace(needle, replacement)

extra_script = r'''
<script>
async function syncTradeResults(silent=true){
  try{
    if(!silent&&$('syncTradeNote'))$('syncTradeNote').textContent='Syncing Binance Futures...';
    const r=await fetchJson('/api/trades/reconcile',{method:'POST'});
    const rows=r.results||[],closed=rows.filter(x=>x.status==='closed').length,matched=rows.filter(x=>x.status==='matched').length,review=rows.filter(x=>x.status==='needs_review').length;
    if($('syncTradeNote')){
      if(!silent||closed||review)$('syncTradeNote').innerHTML='<span class="good">Sync: '+closed+' closed · '+matched+' active</span>'+(review?' · <span class="warn">'+review+' review</span>':'');
    }
  }catch(e){
    if(!silent&&$('syncTradeNote'))$('syncTradeNote').innerHTML='<span class="bad">'+e.message+'</span>';
  }
}

setTimeout(()=>syncTradeResults(true),5000);
setInterval(()=>{if(document.visibilityState==='visible')syncTradeResults(true)},60000);
</script>
'''
appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
