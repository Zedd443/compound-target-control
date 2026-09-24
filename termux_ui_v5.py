from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from flask import jsonify, request

import termux_launcher as store
import termux_ui_v4 as ui4

appmod = ui4.appmod
UTC8 = timezone(timedelta(hours=8))


def api_history_v5():
    if request.method == "GET":
        rows = [
            r for r in store._load_history()
            if float(r.get("planning_usdt", 0) or 0) > 0
        ]
        # Remove duplicate/noise rows for display/analytics.
        cleaned: list[dict] = []
        for row in rows:
            if not cleaned:
                cleaned.append(row)
                continue
            prev = cleaned[-1]
            if abs(float(row.get("planning_usdt", 0)) - float(prev.get("planning_usdt", 0))) < 0.01:
                continue
            cleaned.append(row)
        return jsonify({"ok": True, "rows": cleaned[-500:]})

    try:
        data = request.get_json(force=True)
        planning = float(data.get("planning_usdt", 0) or 0)
        fx_rate = float(data.get("fx_rate", 0) or 0)
        if not math.isfinite(planning) or planning <= 0:
            return jsonify({"ok": True, "saved": False, "ignored": "zero_or_invalid_balance"})

        now_local = datetime.now(UTC8)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "local_date": now_local.date().isoformat(),
            "futures_equity": float(data.get("futures_equity", 0) or 0),
            "overview_balance": float(data.get("overview_balance", 0) or 0),
            "known_wallet_usdt": float(data.get("known_wallet_usdt", 0) or 0),
            "estimated_untracked_usdt": float(data.get("estimated_untracked_usdt", 0) or 0),
            "planning_usdt": planning,
            "fx_rate": fx_rate if math.isfinite(fx_rate) else 0.0,
            "planning_idr": float(data.get("planning_idr", 0) or 0),
            "reason": str(data.get("reason", "refresh")),
            "plan_id": str(data.get("plan_id", "")),
        }
        rows = store._load_history()
        last = rows[-1] if rows else None

        # History is for wallet/PnL movement, not FX ticks. Do not save 0.00 changes.
        should_append = last is None or abs(float(last.get("planning_usdt", 0)) - planning) >= 0.01
        if row["reason"] == "plan_start" and not rows:
            should_append = True

        if should_append:
            rows.append(row)
            store._save_history(rows)
        return jsonify({"ok": True, "saved": should_append, "local_date": row["local_date"]})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"History error: {exc}"}), 400


def api_history_reset():
    try:
        store._save_history([])
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"History reset error: {exc}"}), 500


appmod.app.view_functions["api_history"] = api_history_v5
appmod.app.add_url_rule("/api/history/reset", "api_history_reset_v5", api_history_reset, methods=["POST"])

# Extra visual/analytics styles.
appmod.HTML = appmod.HTML.replace(
    "</style></head>",
    r'''
.subvalue{display:block;font-size:11px;font-weight:600;opacity:.72;margin-top:3px}
.analytics-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px}
.analytics-head h3{margin:0}.analytics-head select{width:auto;min-width:110px;padding:8px 10px;font-size:13px}
.chart-wrap{margin-top:12px}.chart-title{font-size:12px;color:var(--muted);margin:0 0 6px}
canvas.analytics-chart{width:100%;height:140px;display:block;border:1px solid var(--line);border-radius:12px;background:#0d131b}
.analytics-stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px}
.analytics-stat{padding:10px;border-radius:12px;border:1px solid var(--line);background:#0d131b}.analytics-stat small{display:block;color:var(--muted);font-size:11px}.analytics-stat b{display:block;margin-top:3px;font-size:15px}
</style></head>''',
)

tracking_card = '<div class="card section"><h3>Recent Tracking</h3><div id="historyRows" class="notice">Belum ada snapshot.</div></div>'
analytics_card = tracking_card + '''<div class="card section" id="analyticsCard"><div class="analytics-head"><h3>Rolling Analytics</h3><select id="rollingWindow" onchange="renderAnalytics(window.__ctcHistory||[])"><option value="24h">24H</option><option value="7d" selected>7D</option><option value="30d">30D</option><option value="all">ALL</option></select></div><div class="analytics-stats"><div class="analytics-stat"><small>Window PnL</small><b id="aPnl">—</b></div><div class="analytics-stat"><small>Return</small><b id="aReturn">—</b></div><div class="analytics-stat"><small>High / Low</small><b id="aRange">—</b></div><div class="analytics-stat"><small>Max Drawdown</small><b id="aMaxDD">—</b></div></div><div class="chart-wrap"><div class="chart-title">Wallet Equity</div><canvas id="equityChart" class="analytics-chart" width="640" height="180"></canvas></div><div class="chart-wrap"><div class="chart-title">PnL per Snapshot</div><canvas id="pnlChart" class="analytics-chart" width="640" height="180"></canvas></div><div class="notice">Rolling window memakai snapshot saldo yang benar-benar berubah. Refresh tanpa perubahan saldo tidak dihitung.</div></div>'''
appmod.HTML = appmod.HTML.replace(tracking_card, analytics_card)

extra_script = r'''
<script>
function utc8NowParts(){
  const now=new Date();
  const shifted=new Date(now.getTime()+8*3600000);
  return {day:shifted.toISOString().slice(0,10),ms:now.getTime()};
}
function makePlanId(){return 'p_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,7)}
function targetTsForDate(dateStr){
  const now=new Date();
  const target=new Date(dateStr+'T00:00:00');
  target.setHours(now.getHours(),now.getMinutes(),now.getSeconds(),0);
  return target.getTime();
}
function ensureTimedPlan(p){
  if(!p)return p;
  let changed=false;
  if(!p.plan_id){p.plan_id=makePlanId();changed=true}
  if(!p.start_ts){
    const d=new Date(p.start_date+'T00:00:00');p.start_ts=d.getTime();changed=true;
  }
  if(!p.target_ts){p.target_ts=targetTsForDate(p.target_date);changed=true}
  if(changed)localStorage.setItem('ctc_plan',JSON.stringify(p));
  return p;
}
const v4PlanData=planData;
planData=function(){return ensureTimedPlan(v4PlanData())};

function liveTarget(p){
  p=ensureTimedPlan(p);
  const start=Number(p.start_equity),target=Number(p.target_equity),a=Number(p.start_ts),b=Number(p.target_ts),now=Date.now();
  if(!(start>0&&target>0&&b>a))return start||0;
  const fraction=Math.min(Math.max((now-a)/(b-a),0),1);
  return start*Math.exp(Math.log(target/start)*fraction);
}
function renderLiveTargetOnly(){
  const p=planData();if(!p||!fxRate||!$('mToday')||!$('mGap'))return;
  const targetNow=liveTarget(p),current=planningUsdt(),gap=current-targetNow;
  $('mToday').textContent=fmtU(targetNow);
  $('mGap').innerHTML=(gap>=0?'+':'')+gap.toFixed(2)+' USDT<span class="subvalue">≈ '+fmtI(Math.abs(gap)*fxRate)+(gap<0?' behind':'')+'</span>';
  toneCard('mGap',gap>=0?'pos':'neg');toneCard('mToday','info');toneCard('mCurrent',gap>=0?'pos':'warn');
}

startPlan=async function(){
  if(!acct||!fxRate)return;
  const targetIdr=Number($('target').value),startUsdt=planningUsdt(),targetDate=addMonths(today(),$('months').value),startTs=Date.now();
  const p={start_equity:startUsdt,target_equity:targetIdr/fxRate,target_equity_idr:targetIdr,start_fx:fxRate,plan_currency:'USDT',start_date:today(),target_date:targetDate,start_ts:startTs,target_ts:targetTsForDate(targetDate),plan_id:makePlanId()};
  localStorage.setItem('ctc_plan',JSON.stringify(p));localStorage.setItem('ctc_peak_equity',startUsdt);
  await fetchJson('/api/history/reset',{method:'POST'});
  await recordSnapshot('plan_start');await refreshAll();
};

resetPlan=async function(){
  try{await fetchJson('/api/history/reset',{method:'POST'})}catch(e){}
  localStorage.removeItem('ctc_plan');localStorage.removeItem('ctc_peak_equity');
  window.__ctcHistory=[];
  await refreshAll();
};

recordSnapshot=async function(reason='refresh'){
  if(!acct||!fxRate)return;
  const p=planData();
  try{await fetchJson('/api/history',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    futures_equity:acct.equity,overview_balance:overviewBalance(),known_wallet_usdt:Number(walletSummary.known_total_usdt||0),estimated_untracked_usdt:estimatedUntracked(),planning_usdt:planningUsdt(),fx_rate:fxRate,planning_idr:planningIdr(),reason,plan_id:p?p.plan_id:''
  })})}catch(e){}
};

const v4RefreshPlan=refreshPlan;
refreshPlan=async function(p){
  p=ensureTimedPlan(p);
  await v4RefreshPlan(p);
  renderLiveTargetOnly();
};

function filterWindow(rows){
  const mode=$('rollingWindow')?$('rollingWindow').value:'7d';
  if(mode==='all')return rows;
  const span=mode==='24h'?24*3600000:mode==='7d'?7*86400000:30*86400000,cut=Date.now()-span;
  return rows.filter(x=>new Date(x.ts).getTime()>=cut);
}
function cssVar(name,fallback){return getComputedStyle(document.documentElement).getPropertyValue(name).trim()||fallback}
function setupCanvas(canvas){
  if(!canvas)return null;const dpr=Math.max(window.devicePixelRatio||1,1),w=canvas.clientWidth||320,h=140;canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);return {ctx,w,h};
}
function drawEquity(rows){
  const c=setupCanvas($('equityChart'));if(!c)return;const {ctx,w,h}=c;ctx.clearRect(0,0,w,h);if(rows.length<2){ctx.fillStyle=cssVar('--muted','#8993a1');ctx.font='12px system-ui';ctx.fillText('Butuh minimal 2 snapshot saldo.',12,24);return}
  const vals=rows.map(x=>Number(x.planning_usdt)),min=Math.min(...vals),max=Math.max(...vals),pad=(max-min)||1;
  ctx.strokeStyle=cssVar('--accent','#5aa7ff');ctx.lineWidth=2;ctx.beginPath();rows.forEach((x,i)=>{const px=12+i*(w-24)/(rows.length-1),py=12+(max-Number(x.planning_usdt))/pad*(h-24);if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py)});ctx.stroke();
  ctx.fillStyle=cssVar('--muted','#8993a1');ctx.font='11px system-ui';ctx.fillText(max.toFixed(2)+' USDT',10,12);ctx.fillText(min.toFixed(2)+' USDT',10,h-5);
}
function drawPnl(rows){
  const c=setupCanvas($('pnlChart'));if(!c)return;const {ctx,w,h}=c;ctx.clearRect(0,0,w,h);if(rows.length<2){ctx.fillStyle=cssVar('--muted','#8993a1');ctx.font='12px system-ui';ctx.fillText('PnL muncul setelah saldo berubah.',12,24);return}
  const ds=rows.slice(1).map((x,i)=>Number(x.planning_usdt)-Number(rows[i].planning_usdt)),mx=Math.max(...ds.map(Math.abs),.01),mid=h/2,bw=Math.max((w-24)/ds.length-3,2);ctx.strokeStyle=cssVar('--line','#202938');ctx.beginPath();ctx.moveTo(8,mid);ctx.lineTo(w-8,mid);ctx.stroke();ds.forEach((d,i)=>{const bh=Math.abs(d)/mx*(h/2-14),x=12+i*(w-24)/ds.length,y=d>=0?mid-bh:mid;ctx.fillStyle=d>=0?cssVar('--ok','#4cc38a'):cssVar('--bad','#ff7272');ctx.fillRect(x,y,bw,bh)});
}
function renderAnalytics(allRows){
  const rows=filterWindow((allRows||[]).filter(x=>Number(x.planning_usdt)>0));
  if(!rows.length){['aPnl','aReturn','aRange','aMaxDD'].forEach(id=>{if($(id))$(id).textContent='—'});drawEquity([]);drawPnl([]);return}
  const first=Number(rows[0].planning_usdt),last=Number(rows[rows.length-1].planning_usdt),pnl=last-first,ret=first>0?pnl/first:0,vals=rows.map(x=>Number(x.planning_usdt));let peak=vals[0],mdd=0;for(const v of vals){peak=Math.max(peak,v);if(peak>0)mdd=Math.max(mdd,(peak-v)/peak)}
  $('aPnl').textContent=(pnl>=0?'+':'')+pnl.toFixed(2)+' USDT';$('aPnl').style.color=pnl>=0?cssVar('--ok','#4cc38a'):cssVar('--bad','#ff7272');
  $('aReturn').textContent=(ret>=0?'+':'')+(ret*100).toFixed(2)+'%';$('aReturn').style.color=ret>=0?cssVar('--ok','#4cc38a'):cssVar('--bad','#ff7272');
  $('aRange').textContent=Math.max(...vals).toFixed(2)+' / '+Math.min(...vals).toFixed(2);$('aMaxDD').textContent=(mdd*100).toFixed(2)+'%';$('aMaxDD').style.color=mdd>=.10?cssVar('--bad','#ff7272'):mdd>=.05?'#f4c95d':cssVar('--ok','#4cc38a');drawEquity(rows);drawPnl(rows);
}

loadHistory=async function(){
  try{
    const h=await fetchJson('/api/history'),rows=(h.rows||[]).filter(x=>Number(x.planning_usdt)>0);window.__ctcHistory=rows;
    if($('historyRows')){
      if(!rows.length)$('historyRows').textContent='Belum ada snapshot untuk plan ini.';
      else $('historyRows').innerHTML=rows.slice(-8).reverse().map(x=>{const idx=rows.indexOf(x),prev=idx>0?rows[idx-1]:null,delta=prev?Number(x.planning_usdt)-Number(prev.planning_usdt):null,cls=delta>0?'history-up':delta<0?'history-down':'history-flat',ds=delta===null?'start':((delta>=0?'+':'')+delta.toFixed(2)+' USDT');return '<div style="padding:7px 0;border-bottom:1px solid var(--line)"><b>'+new Date(x.ts).toLocaleString('id-ID')+'</b> · '+fmtU(x.planning_usdt)+' · <span class="'+cls+'">'+ds+'</span></div>'}).join('');
    }
    renderAnalytics(rows);return rows;
  }catch(e){return []}
};

setInterval(renderLiveTargetOnly,15000);
window.addEventListener('resize',()=>renderAnalytics(window.__ctcHistory||[]));
setTimeout(async()=>{await loadHistory();renderLiveTargetOnly()},180);
</script>
'''

appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
