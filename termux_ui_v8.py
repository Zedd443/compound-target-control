from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from flask import jsonify, request

import ctc_store
import termux_ui_v7 as base

appmod = base.appmod
UTC8 = timezone(timedelta(hours=8))
ctc_store.init_db()


def api_history_sqlite():
    if request.method == "GET":
        rows = [r for r in ctc_store.list_wallet_snapshots(500) if float(r.get("planning_usdt", 0) or 0) > 0]
        return jsonify({"ok": True, "rows": rows, "storage": "sqlite"})

    try:
        data = request.get_json(force=True)
        planning = float(data.get("planning_usdt", 0) or 0)
        if not math.isfinite(planning) or planning <= 0:
            return jsonify({"ok": True, "saved": False, "ignored": "zero_or_invalid_balance"})

        last = ctc_store.latest_wallet_snapshot()
        reason = str(data.get("reason", "refresh"))
        should_append = last is None or abs(float(last.get("planning_usdt", 0)) - planning) >= 0.01
        if reason == "plan_start" and last is None:
            should_append = True

        if not should_append:
            return jsonify({"ok": True, "saved": False, "storage": "sqlite"})

        now_local = datetime.now(UTC8)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "local_date": now_local.date().isoformat(),
            "futures_equity": float(data.get("futures_equity", 0) or 0),
            "overview_balance": float(data.get("overview_balance", 0) or 0),
            "known_wallet_usdt": float(data.get("known_wallet_usdt", 0) or 0),
            "estimated_untracked_usdt": float(data.get("estimated_untracked_usdt", 0) or 0),
            "planning_usdt": planning,
            "fx_rate": float(data.get("fx_rate", 0) or 0),
            "planning_idr": float(data.get("planning_idr", 0) or 0),
            "reason": reason,
            "plan_id": str(data.get("plan_id", "")),
        }
        row_id = ctc_store.insert_wallet_snapshot(row)
        return jsonify({"ok": True, "saved": True, "id": row_id, "storage": "sqlite"})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"History SQLite error: {exc}"}), 400


def api_history_reset_sqlite():
    try:
        ctc_store.clear_wallet_snapshots()
        return jsonify({"ok": True, "storage": "sqlite"})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"History reset error: {exc}"}), 500


def api_trades_sqlite():
    if request.method == "GET":
        try:
            limit = int(request.args.get("limit", 100))
            return jsonify({"ok": True, "rows": ctc_store.list_trades(limit), "storage": "sqlite"})
        except Exception as exc:
            return jsonify({"ok": False, "error": f"Trade list error: {exc}"}), 400

    try:
        data = request.get_json(force=True)
        lead = str(data.get("lead", "")).strip()
        if not lead:
            raise ValueError("Lead / Analyst wajib diisi sebelum Save Trade.")
        if not isinstance(data.get("signal"), dict) or not isinstance(data.get("result"), dict):
            raise ValueError("Analyze signal dulu sebelum Save Trade.")
        payload = {
            **data,
            "lead": lead,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        trade_id = ctc_store.insert_trade(payload)
        return jsonify({"ok": True, "trade_id": trade_id, "storage": "sqlite"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


# Replace the JSON history handlers with SQLite. Old JSON is imported once on first startup.
appmod.app.view_functions["api_history"] = api_history_sqlite
if "api_history_reset_v5" in appmod.app.view_functions:
    appmod.app.view_functions["api_history_reset_v5"] = api_history_reset_sqlite
else:
    appmod.app.add_url_rule("/api/history/reset", "api_history_reset_sqlite", api_history_reset_sqlite, methods=["POST"])
appmod.app.add_url_rule("/api/trades", "api_trades_sqlite", api_trades_sqlite, methods=["GET", "POST"])

# Keep manual input deliberately small: lead + the original signal text containing entry/TP/SL.
trade_start = '<div id="trade" class="tabpane hidden"><div class="card"><div class="field"><label>Paste signal</label>'
trade_with_lead = '<div id="trade" class="tabpane hidden"><div class="card"><div class="field"><label>Lead / Analyst</label><input id="leadName" placeholder="ACAM / nama analyst"></div><div class="field"><label>Paste signal</label>'
appmod.HTML = appmod.HTML.replace(trade_start, trade_with_lead)

old_parse_area = '<button class="btn primary wide" onclick="parseAndSize()">Parse & Calculate</button><div id="parsed" class="notice"></div>'
new_parse_area = old_parse_area + '<button id="saveTradeBtn" class="btn wide hidden" onclick="saveTrade()">Save Trade</button><div id="saveTradeNote" class="notice hidden"></div>'
appmod.HTML = appmod.HTML.replace(old_parse_area, new_parse_area)

extra_script = r'''
<script>
window.__ctcLastSignal=null;
window.__ctcLastSizing=null;

parseAndSize=async function(){
  try{
    const p=planData();if(!p)throw new Error('Start Plan dulu.');
    const raw=$('signalText').value;
    const signal=await fetchJson('/api/parse-signal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:raw})});
    $('parsed').textContent=signal.symbol+' '+signal.side+' · Entry '+signal.entry+(signal.entry_low!==signal.entry_high?' ('+signal.entry_low+'-'+signal.entry_high+')':'')+' · SL '+signal.stop_loss+' · '+signal.targets.length+' TP · '+signal.leverage+'x '+signal.leverage_source;
    const dd=updatePeak();
    const result=await fetchJson('/api/size',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      start_equity:p.start_equity,target_equity:p.target_equity,start_date:p.start_date,target_date:p.target_date,
      reporting_equity:planningUsdt(),trading_equity:acct.equity,drawdown_pct:dd,open_risk_pct:acct.open_risk_pct,signal
    })});
    window.__ctcLastSignal=signal;
    window.__ctcLastSizing=result;
    $('tradeResult').classList.remove('hidden');
    $('rEff').textContent=pct(result.effective_risk_pct);$('maxLoss').textContent=fmtU(result.max_planned_loss);$('notional').textContent=fmtU(result.recommended_notional);$('margin').textContent=fmtU(result.required_margin);
    $('vol').textContent=result.volatility.regime.toUpperCase()+(result.volatility.atr_pct?' · ATR '+pct(result.volatility.atr_pct):'');$('stopDist').textContent=pct(result.stop_distance_pct);
    $('partialProfile').textContent='Profile: '+result.partial.profile+' · Target pressure '+Number(result.target_pressure).toFixed(2)+'× · Weighted listed-TP R '+Number(result.partial.weighted_r).toFixed(2)+'R';
    $('tpRows').innerHTML=result.partial.targets.map(x=>{const gain=(signal.side==='LONG'?(x.price-signal.entry):(signal.entry-x.price))/signal.entry;return '<div class="tp"><b>'+x.name+' · '+Number(x.price).toLocaleString('en-US')+'</b><span>'+Number(x.r_multiple).toFixed(2)+'R · '+(gain*100).toFixed(2)+'%</span><b>'+Math.round(x.fraction*100)+'%</b></div>'}).join('');
    $('runner').textContent=Math.round(result.partial.runner_fraction*100)+'%';
    $('saveTradeBtn').classList.remove('hidden');
    $('saveTradeNote').classList.add('hidden');
    toneCard('rEff','info');toneCard('maxLoss','neg');toneCard('notional','info');toneCard('margin','info');toneCard('stopDist','info');
    const vt=String(result.volatility.regime).toUpperCase();toneCard('vol',vt==='EXTREME'?'neg':vt==='HIGH'?'warn':'pos');
  }catch(e){
    window.__ctcLastSignal=null;window.__ctcLastSizing=null;
    if($('saveTradeBtn'))$('saveTradeBtn').classList.add('hidden');
    $('parsed').innerHTML='<span class="bad">'+e.message+'</span>';
  }
};

async function saveTrade(){
  try{
    const lead=String($('leadName').value||'').trim();
    if(!lead)throw new Error('Isi Lead / Analyst dulu.');
    if(!window.__ctcLastSignal||!window.__ctcLastSizing)throw new Error('Parse & Calculate dulu.');
    const p=planData(),dd=updatePeak();
    const saved=await fetchJson('/api/trades',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      lead,
      raw_signal:$('signalText').value,
      plan_id:p&&p.plan_id?p.plan_id:'',
      futures_equity:acct?acct.equity:0,
      overview_equity:planningUsdt(),
      drawdown_pct:dd,
      open_risk_pct:acct?acct.open_risk_pct:0,
      signal:window.__ctcLastSignal,
      result:window.__ctcLastSizing
    })});
    $('saveTradeNote').innerHTML='<span class="good">Saved · Trade #'+saved.trade_id+' · '+lead+'</span>';
    $('saveTradeNote').classList.remove('hidden');
    $('saveTradeBtn').classList.add('hidden');
  }catch(e){
    $('saveTradeNote').innerHTML='<span class="bad">'+e.message+'</span>';
    $('saveTradeNote').classList.remove('hidden');
  }
}
</script>
'''

appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
