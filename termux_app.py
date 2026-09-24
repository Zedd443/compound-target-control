from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

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
    if not isinstance(account, dict):
        raise BinanceApiError(f"Unexpected Binance account response type: {type(account).__name__}")

    equity = account.get("totalMarginBalance")
    if equity is None:
        equity = account.get("totalWalletBalance")
    available = account.get("availableBalance")
    unrealized = account.get("totalUnrealizedProfit", 0)

    if equity is None or available is None:
        keys = ", ".join(sorted(account.keys())[:20])
        raise BinanceApiError(f"Unexpected Binance account schema. Keys: {keys}")

    return {
        "equity": float(equity),
        "available": float(available),
        "unrealized": float(unrealized),
    }


@app.get("/api/account")
def api_account():
    try:
        return jsonify({"ok": True, **account_state()})
    except BinanceApiError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"Backend error: {type(exc).__name__}: {exc}",
        }), 500


@app.post("/api/plan")
def api_plan():
    try:
        data = request.get_json(force=True)
        goal = Goal(
            start_equity=float(data["start_equity"]),
            target_equity=float(data["target_equity"]),
            start_date=date.fromisoformat(data["start_date"]),
            target_date=date.fromisoformat(data["target_date"]),
            reporting_currency="IDR",
        )
        snapshot = build_goal_snapshot(goal, float(data["current_equity"]), date.today())
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
        return jsonify({"ok": False, "error": f"Plan error: {type(exc).__name__}: {exc}"}), 400


@app.post("/api/size")
def api_size():
    try:
        data = request.get_json(force=True)
        goal = Goal(
            start_equity=float(data["start_equity"]),
            target_equity=float(data["target_equity"]),
            start_date=date.fromisoformat(data["start_date"]),
            target_date=date.fromisoformat(data["target_date"]),
            reporting_currency="IDR",
        )
        setup = TradeSetup(
            symbol=str(data["symbol"]).upper(),
            side=str(data["side"]).upper(),
            entry=float(data["entry"]),
            stop_loss=float(data["stop_loss"]),
            leverage=float(data["leverage"]),
        )
        result = planner.plan_trade(
            goal=goal,
            reporting_equity=float(data["reporting_equity"]),
            trading_equity=float(data["trading_equity"]),
            as_of=date.today(),
            drawdown_pct=float(data.get("drawdown_pct", 0.0)),
            volatility_regime=VolatilityRegime(str(data.get("volatility_regime", "normal"))),
            open_risk_pct=float(data.get("open_risk_pct", 0.0)),
            setup=setup,
        )
        return jsonify({
            "ok": True,
            "effective_risk_pct": result.risk.effective_risk_pct,
            "risk_budget": result.position.risk_budget,
            "recommended_notional": result.position.recommended_notional,
            "required_margin": result.position.required_margin,
            "stop_distance_pct": result.position.stop_distance_pct,
            "estimated_loss_at_stop": result.position.estimated_loss_at_stop,
            "account_risk_pct": result.position.account_risk_pct,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Sizing error: {type(exc).__name__}: {exc}"}), 400


@app.get("/")
def home():
    return HTML


HTML = r'''<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0f14">
<title>Compound Target Control</title>
<style>
:root{color-scheme:dark;--bg:#0b0f14;--card:#121821;--muted:#8993a1;--line:#202938;--accent:#5aa7ff;--ok:#4cc38a;--bad:#ff6b6b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#f4f7fb;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:760px;margin:auto;padding:18px 14px 40px}.head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:6px 0 18px}.title{font-size:28px;font-weight:800;line-height:1.05}.sub{color:var(--muted);font-size:13px;margin-top:6px}.btn{border:0;border-radius:12px;padding:12px 14px;background:#1b2635;color:#fff;font-weight:700}.btn.primary{background:var(--accent);color:#07101d}.btn.danger{background:#3a1d22;color:#ffb3b3}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px}.metric small{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}.metric b{font-size:20px}.section{margin-top:14px}.section h2{font-size:16px;margin:0 0 10px}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.field{margin-bottom:10px}.field label{display:block;font-size:12px;color:var(--muted);margin-bottom:6px}input,select{width:100%;padding:12px;border-radius:11px;border:1px solid var(--line);background:#0d131b;color:#fff;font-size:16px}.wide{width:100%}.hidden{display:none}.status{font-size:13px;padding:10px 12px;border-radius:12px;background:#111a25;color:var(--muted);margin-bottom:12px;overflow-wrap:anywhere}.good{color:var(--ok)}.bad{color:var(--bad)}.tabs{display:flex;gap:8px;margin:14px 0}.tab{flex:1}.tab.active{background:#263950}.mono{font-variant-numeric:tabular-nums}.footer{color:var(--muted);font-size:11px;margin-top:18px;text-align:center}@media(max-width:480px){.title{font-size:24px}.metric b{font-size:17px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="head"><div><div class="title">Compound Target Control</div><div class="sub">Termux local UI · Binance read-only</div></div><button class="btn" onclick="refreshAll()">Refresh</button></div>
  <div id="status" class="status">Menghubungkan ke Binance...</div>

  <div class="grid">
    <div class="card metric"><small>Futures Equity</small><b id="eq">—</b></div>
    <div class="card metric"><small>Available</small><b id="avail">—</b></div>
    <div class="card metric"><small>Approx. IDR</small><b id="idr">—</b></div>
    <div class="card metric"><small>Unrealized PnL</small><b id="upnl">—</b></div>
  </div>

  <div class="section card">
    <div class="field"><label>USDT → IDR</label><input id="fx" type="number" value="16500" step="100"></div>
  </div>

  <div id="createPlan" class="section card hidden">
    <h2>Buat Target</h2>
    <div class="field"><label>Target Equity (IDR)</label><input id="target" type="number" value="10000000000"></div>
    <div class="field"><label>Horizon (bulan)</label><input id="months" type="number" min="1" max="240" value="24"></div>
    <button class="btn primary wide" onclick="startPlan()">Start Plan</button>
  </div>

  <div id="planView" class="hidden">
    <div class="tabs"><button class="btn tab active" onclick="showTab('mission',this)">Mission</button><button class="btn tab" onclick="showTab('trade',this)">Trade</button><button class="btn tab" onclick="showTab('plan',this)">Plan</button></div>

    <div id="mission" class="tabpane">
      <div class="grid">
        <div class="card metric"><small>Target</small><b id="mTarget">—</b></div>
        <div class="card metric"><small>Days Left</small><b id="mDays">—</b></div>
        <div class="card metric"><small>Required Monthly</small><b id="mReq">—</b></div>
        <div class="card metric"><small>Target Pressure</small><b id="mPressure">—</b></div>
        <div class="card metric"><small>Target Today</small><b id="mToday">—</b></div>
        <div class="card metric"><small>Status</small><b id="mStatus">—</b></div>
      </div>
    </div>

    <div id="trade" class="tabpane hidden">
      <div class="card">
        <div class="row"><div class="field"><label>Symbol</label><input id="symbol" value="BTCUSDT"></div><div class="field"><label>Side</label><select id="side"><option>LONG</option><option>SHORT</option></select></div></div>
        <div class="row"><div class="field"><label>Entry</label><input id="entry" type="number" value="100000"></div><div class="field"><label>Stop Loss</label><input id="sl" type="number" value="98000"></div></div>
        <div class="row"><div class="field"><label>Leverage</label><input id="lev" type="number" value="5"></div><div class="field"><label>Volatility</label><select id="vol"><option>low</option><option selected>normal</option><option>high</option><option>extreme</option></select></div></div>
        <div class="row"><div class="field"><label>Drawdown %</label><input id="dd" type="number" value="0" step="0.5"></div><div class="field"><label>Open Risk %</label><input id="openRisk" type="number" value="0" step="0.1"></div></div>
        <button class="btn primary wide" onclick="sizeTrade()">Calculate Size</button>
      </div>
      <div id="sizeResult" class="grid section hidden">
        <div class="card metric"><small>Effective R</small><b id="rEff">—</b></div>
        <div class="card metric"><small>Risk Budget</small><b id="riskBudget">—</b></div>
        <div class="card metric"><small>Notional</small><b id="notional">—</b></div>
        <div class="card metric"><small>Margin</small><b id="margin">—</b></div>
        <div class="card metric"><small>Stop Distance</small><b id="stopDist">—</b></div>
        <div class="card metric"><small>Loss @ SL</small><b id="lossSL">—</b></div>
      </div>
    </div>

    <div id="plan" class="tabpane hidden">
      <div class="card">
        <div class="metric"><small>Start Equity</small><b id="pStart">—</b></div><br>
        <div class="metric"><small>Start Date</small><b id="pStartDate">—</b></div><br>
        <div class="metric"><small>Target Date</small><b id="pTargetDate">—</b></div><br>
        <button class="btn danger wide" onclick="resetPlan()">Reset Plan</button>
      </div>
    </div>
  </div>

  <div class="footer">API key disimpan hanya di file .env Termux. UI ini berjalan di localhost.</div>
</div>
<script>
let acct=null;
const $=id=>document.getElementById(id);
const fmtUSDT=n=>Number(n).toLocaleString('en-US',{maximumFractionDigits:2})+' USDT';
const fmtIDR=n=>'Rp'+Math.round(Number(n)).toLocaleString('id-ID');
const pct=n=>(Number(n)*100).toFixed(2)+'%';
function addMonths(dateStr,months){const d=new Date(dateStr+'T00:00:00');const day=d.getDate();d.setDate(1);d.setMonth(d.getMonth()+Number(months));const last=new Date(d.getFullYear(),d.getMonth()+1,0).getDate();d.setDate(Math.min(day,last));return d.toISOString().slice(0,10)}
function planData(){return JSON.parse(localStorage.getItem('ctc_plan')||'null')}
function savePlan(p){localStorage.setItem('ctc_plan',JSON.stringify(p))}
function today(){return new Date().toISOString().slice(0,10)}
async function fetchJson(url,options){const r=await fetch(url,options);const text=await r.text();let d;try{d=JSON.parse(text)}catch(e){const preview=text.replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim().slice(0,180);throw new Error('Backend returned non-JSON ('+r.status+'). '+(preview||'Check Termux log.'))}if(!d.ok)throw new Error(d.error||('Request failed '+r.status));return d}
async function getAccount(){const d=await fetchJson('/api/account');acct=d;renderAccount();return d}
function renderAccount(){const fx=Number($('fx').value||16500);$('eq').textContent=fmtUSDT(acct.equity);$('avail').textContent=fmtUSDT(acct.available);$('idr').textContent=fmtIDR(acct.equity*fx);$('upnl').textContent=fmtUSDT(acct.unrealized)}
async function refreshAll(){try{$('status').textContent='Refreshing...';await getAccount();$('status').innerHTML='<span class="good">Connected</span> · data Binance terbaru';const p=planData();if(p){$('createPlan').classList.add('hidden');$('planView').classList.remove('hidden');await refreshPlan(p)}else{$('createPlan').classList.remove('hidden');$('planView').classList.add('hidden')}}catch(e){$('status').innerHTML='<span class="bad">'+e.message+'</span>'}}
async function startPlan(){if(!acct)return;const fx=Number($('fx').value);const p={start_equity:acct.equity*fx,target_equity:Number($('target').value),start_date:today(),target_date:addMonths(today(),$('months').value)};savePlan(p);await refreshAll()}
async function refreshPlan(p){try{const fx=Number($('fx').value);const current=acct.equity*fx;const d=await fetchJson('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,current_equity:current})});$('mTarget').textContent=fmtIDR(p.target_equity);$('mDays').textContent=d.days_remaining;$('mReq').textContent=pct(d.current_monthly_return);$('mPressure').textContent=Number(d.target_pressure).toFixed(2)+'×';$('mToday').textContent=fmtIDR(d.baseline_equity);$('mStatus').textContent=d.status.replaceAll('_',' ');$('pStart').textContent=fmtIDR(p.start_equity);$('pStartDate').textContent=p.start_date;$('pTargetDate').textContent=p.target_date}catch(e){$('status').innerHTML='<span class="bad">'+e.message+'</span>'}}
async function sizeTrade(){const p=planData();if(!p||!acct)return;try{const fx=Number($('fx').value);const body={...p,reporting_equity:acct.equity*fx,trading_equity:acct.equity,symbol:$('symbol').value,side:$('side').value,entry:Number($('entry').value),stop_loss:Number($('sl').value),leverage:Number($('lev').value),drawdown_pct:Number($('dd').value)/100,open_risk_pct:Number($('openRisk').value)/100,volatility_regime:$('vol').value};const d=await fetchJson('/api/size',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});$('sizeResult').classList.remove('hidden');$('rEff').textContent=pct(d.effective_risk_pct);$('riskBudget').textContent=fmtUSDT(d.risk_budget);$('notional').textContent=fmtUSDT(d.recommended_notional);$('margin').textContent=fmtUSDT(d.required_margin);$('stopDist').textContent=pct(d.stop_distance_pct);$('lossSL').textContent=fmtUSDT(d.estimated_loss_at_stop)}catch(e){$('status').innerHTML='<span class="bad">'+e.message+'</span>'}}
function resetPlan(){localStorage.removeItem('ctc_plan');refreshAll()}
function showTab(id,btn){document.querySelectorAll('.tabpane').forEach(x=>x.classList.add('hidden'));document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));$(id).classList.remove('hidden');btn.classList.add('active')}
$('fx').addEventListener('change',()=>{if(acct){renderAccount();const p=planData();if(p)refreshPlan(p)}});refreshAll();
</script>
</body></html>'''


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8501, debug=False)
