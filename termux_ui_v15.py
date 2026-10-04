from __future__ import annotations

import termux_ui_v14 as base

appmod = base.appmod

# Analytics v15: custom date range, daily aggregation, clickable PnL bars,
# and richer period diagnostics. No trading/risk calculations are changed.
extra_style = r'''
<style>
.analytics-toolbar{display:grid;grid-template-columns:minmax(120px,1fr) minmax(0,1fr);gap:8px;align-items:end}
.analytics-toolbar .field{margin:0}
.analytics-toolbar label{display:block;color:var(--muted);font-size:10px;margin:0 0 5px}
.analytics-toolbar select,.analytics-toolbar input{width:100%;min-height:40px;padding:8px 10px;font-size:13px}
.analytics-custom{display:none;grid-column:1/-1;grid-template-columns:1fr 1fr auto;gap:8px;align-items:end}
.analytics-custom.show{display:grid}
.analytics-custom .btn{min-height:40px;padding:8px 12px}
.analytics-stats-v15{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px}
.analytics-stat-v15{padding:10px;border-radius:12px;border:1px solid var(--line);background:#0b121a;min-width:0}
.analytics-stat-v15 small{display:block;color:var(--muted);font-size:10px;line-height:1.25}
.analytics-stat-v15 b{display:block;margin-top:4px;font-size:14px;line-height:1.2;overflow-wrap:anywhere}
.analytics-detail{margin-top:10px;padding:11px;border:1px solid #2a3950;border-radius:12px;background:#0b121a;display:none}
.analytics-detail.show{display:block}
.analytics-detail-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.analytics-detail-title{font-weight:800;font-size:14px}
.analytics-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:9px}
.analytics-detail-grid div{font-size:11px;color:var(--muted)}
.analytics-detail-grid b{display:block;color:var(--text);font-size:13px;margin-top:2px}
.analytics-hint{font-size:10px;color:var(--muted);margin-top:6px;line-height:1.45}
canvas.analytics-chart{touch-action:manipulation;cursor:pointer}
@media(max-width:560px){
  .analytics-toolbar{grid-template-columns:1fr}
  .analytics-custom{grid-template-columns:1fr 1fr}
  .analytics-custom .btn{grid-column:1/-1}
  .analytics-stats-v15{grid-template-columns:repeat(2,minmax(0,1fr))}
}
</style>
'''
appmod.HTML = appmod.HTML.replace("</head>", extra_style + "</head>")

extra_script = r'''
<script>
function a15DateKey(row){
  if(row&&row.local_date)return String(row.local_date);
  const t=new Date(row.ts).getTime()+8*3600000;
  return new Date(t).toISOString().slice(0,10);
}
function a15FmtSigned(n,d=2){n=Number(n||0);return (n>=0?'+':'')+n.toFixed(d)}
function a15TodayKey(){return new Date(Date.now()+8*3600000).toISOString().slice(0,10)}
function a15DateMinus(days){
  const d=new Date(a15TodayKey()+'T00:00:00+08:00');
  d.setUTCDate(d.getUTCDate()-days);
  return new Date(d.getTime()).toISOString().slice(0,10);
}
function a15EnsureUi(){
  const card=$('analyticsCard');
  if(!card||card.dataset.v15==='1')return;
  card.dataset.v15='1';
  card.innerHTML=
    '<div class="analytics-head"><h3>Performance Analytics</h3></div>'+
    '<div class="analytics-toolbar">'+
      '<div class="field"><label>Range</label><select id="rollingWindow"><option value="24h">24H</option><option value="7d" selected>7D</option><option value="30d">30D</option><option value="all">ALL</option><option value="custom">CUSTOM DATE</option></select></div>'+
      '<div class="field"><label>View</label><select id="analyticsView"><option value="daily" selected>Daily PnL</option><option value="snapshot">Snapshot PnL</option></select></div>'+
      '<div class="analytics-custom" id="analyticsCustom">'+
        '<div class="field"><label>From</label><input id="analyticsFrom" type="date"></div>'+
        '<div class="field"><label>To</label><input id="analyticsTo" type="date"></div>'+
        '<button class="btn" id="analyticsApply" type="button">Apply</button>'+
      '</div>'+
    '</div>'+
    '<div class="analytics-stats-v15">'+
      '<div class="analytics-stat-v15"><small>Period PnL</small><b id="aPnl">—</b></div>'+
      '<div class="analytics-stat-v15"><small>Return</small><b id="aReturn">—</b></div>'+
      '<div class="analytics-stat-v15"><small>Max Drawdown</small><b id="aMaxDD">—</b></div>'+
      '<div class="analytics-stat-v15"><small>Win / Loss Days</small><b id="aWinLoss">—</b></div>'+
      '<div class="analytics-stat-v15"><small>Best / Worst Day</small><b id="aBestWorst">—</b></div>'+
      '<div class="analytics-stat-v15"><small>Avg Daily PnL</small><b id="aAvgDaily">—</b></div>'+
      '<div class="analytics-stat-v15"><small>High / Low Equity</small><b id="aRange">—</b></div>'+
      '<div class="analytics-stat-v15"><small>Daily Win Rate</small><b id="aWinRate">—</b></div>'+
      '<div class="analytics-stat-v15"><small>Daily Volatility</small><b id="aVolatility">—</b></div>'+
    '</div>'+
    '<div class="chart-wrap"><div class="chart-title">Wallet Equity</div><canvas id="equityChart" class="analytics-chart" width="640" height="180"></canvas></div>'+
    '<div class="chart-wrap"><div class="chart-title" id="pnlChartTitle">Daily PnL · tap a bar for detail</div><canvas id="pnlChart" class="analytics-chart" width="640" height="180"></canvas><div class="analytics-detail" id="pnlBarDetail"></div></div>'+
    '<div class="analytics-hint">PnL dihitung dari perubahan Planning Equity. Deposit, withdrawal, atau perubahan balance manual ikut terbaca sebagai perubahan equity, jadi tandai itu saat interpretasi.</div>';

  $('analyticsFrom').value=a15DateMinus(6);
  $('analyticsTo').value=a15TodayKey();
  $('rollingWindow').addEventListener('change',function(){
    $('analyticsCustom').classList.toggle('show',$('rollingWindow').value==='custom');
    renderAnalytics(window.__ctcHistory||[]);
  });
  $('analyticsView').addEventListener('change',function(){renderAnalytics(window.__ctcHistory||[])});
  $('analyticsApply').addEventListener('click',function(){renderAnalytics(window.__ctcHistory||[])});
  $('pnlChart').addEventListener('click',a15PnlClick);
}
function a15RangeBounds(){
  const mode=$('rollingWindow')?$('rollingWindow').value:'7d';
  if(mode==='all')return {mode:mode,start:null,end:null};
  if(mode==='custom')return {mode:mode,start:$('analyticsFrom')&&$('analyticsFrom').value||null,end:$('analyticsTo')&&$('analyticsTo').value||null};
  const days=mode==='24h'?1:mode==='7d'?7:30;
  return {mode:mode,start:a15DateMinus(days-1),end:a15TodayKey()};
}
function filterWindow(rows){
  a15EnsureUi();
  const b=a15RangeBounds();
  const valid=(rows||[]).filter(function(x){return Number(x.planning_usdt)>0}).sort(function(a,b){return new Date(a.ts)-new Date(b.ts)});
  if(b.mode==='all')return valid;
  return valid.filter(function(x){const k=a15DateKey(x);return (!b.start||k>=b.start)&&(!b.end||k<=b.end)});
}
function a15RowsWithAnchor(allRows,filtered){
  if(!filtered.length)return filtered;
  const firstTs=new Date(filtered[0].ts).getTime();
  const earlier=(allRows||[]).filter(function(x){return Number(x.planning_usdt)>0&&new Date(x.ts).getTime()<firstTs});
  if(!earlier.length)return filtered;
  return [earlier[earlier.length-1]].concat(filtered);
}
function a15Daily(rows){
  const map=new Map();
  rows.forEach(function(r){const k=a15DateKey(r);if(!map.has(k))map.set(k,[]);map.get(k).push(r)});
  const keys=Array.from(map.keys()).sort(),out=[];let previousClose=null;
  keys.forEach(function(k){
    const rs=map.get(k).slice().sort(function(a,b){return new Date(a.ts)-new Date(b.ts)});
    const vals=rs.map(function(x){return Number(x.planning_usdt)});
    const open=previousClose!==null?previousClose:vals[0],close=vals[vals.length-1],pnl=close-open,ret=open>0?pnl/open:0;
    out.push({date:k,open:open,close:close,pnl:pnl,ret:ret,high:Math.max.apply(null,vals.concat([open])),low:Math.min.apply(null,vals.concat([open])),snapshots:rs.length,rows:rs});
    previousClose=close;
  });
  return out;
}
function a15Std(values){
  if(values.length<2)return 0;
  const avg=values.reduce(function(a,b){return a+b},0)/values.length;
  return Math.sqrt(values.reduce(function(s,x){return s+(x-avg)*(x-avg)},0)/(values.length-1));
}
function a15DrawEquity(rows){
  const c=setupCanvas($('equityChart'));if(!c)return;
  const ctx=c.ctx,w=c.w,h=c.h;ctx.clearRect(0,0,w,h);
  if(rows.length<2){ctx.fillStyle=cssVar('--muted','#8993a1');ctx.font='12px system-ui';ctx.fillText('Butuh minimal 2 snapshot saldo.',12,24);return}
  const vals=rows.map(function(x){return Number(x.planning_usdt)}),min=Math.min.apply(null,vals),max=Math.max.apply(null,vals),pad=(max-min)||1;
  ctx.strokeStyle=cssVar('--accent','#5aa7ff');ctx.lineWidth=2;ctx.beginPath();
  rows.forEach(function(x,i){const px=12+i*(w-24)/(rows.length-1),py=14+(max-Number(x.planning_usdt))/pad*(h-30);if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py)});
  ctx.stroke();ctx.fillStyle=cssVar('--muted','#8993a1');ctx.font='10px system-ui';ctx.fillText(max.toFixed(2),10,11);ctx.fillText(min.toFixed(2),10,h-5);
}
window.__a15Bars=[];
function a15DrawPnl(rows,daily){
  const c=setupCanvas($('pnlChart'));if(!c)return;
  const ctx=c.ctx,w=c.w,h=c.h;ctx.clearRect(0,0,w,h);
  const mode=$('analyticsView')?$('analyticsView').value:'daily';
  const items=mode==='snapshot'
    ? rows.slice(1).map(function(x,i){const p=Number(x.planning_usdt)-Number(rows[i].planning_usdt),o=Number(rows[i].planning_usdt),cl=Number(x.planning_usdt);return {label:new Date(x.ts).toLocaleString('id-ID'),pnl:p,ret:o>0?p/o:0,open:o,close:cl,high:Math.max(o,cl),low:Math.min(o,cl),snapshots:1,date:a15DateKey(x)}})
    : daily.map(function(x){return Object.assign({label:x.date},x)});
  window.__a15Bars=[];
  if(!items.length){ctx.fillStyle=cssVar('--muted','#8993a1');ctx.font='12px system-ui';ctx.fillText('Belum ada perubahan saldo di range ini.',12,24);return}
  const mx=Math.max.apply(null,items.map(function(x){return Math.abs(x.pnl)}).concat([.01])),mid=h/2,slot=(w-24)/items.length,bw=Math.max(Math.min(slot*.68,24),3);
  ctx.strokeStyle=cssVar('--line','#202938');ctx.beginPath();ctx.moveTo(8,mid);ctx.lineTo(w-8,mid);ctx.stroke();
  items.forEach(function(d,i){const bh=Math.max(Math.abs(d.pnl)/mx*(h/2-18),d.pnl===0?1:2),cx=12+i*slot+slot/2,x=cx-bw/2,y=d.pnl>=0?mid-bh:mid;ctx.fillStyle=d.pnl>=0?cssVar('--ok','#4cc38a'):cssVar('--bad','#ff7272');ctx.fillRect(x,y,bw,bh);window.__a15Bars.push({x1:x-5,x2:x+bw+5,y1:Math.min(y,mid)-6,y2:Math.max(y+bh,mid)+6,data:d})});
}
function a15PnlClick(ev){
  const canvas=$('pnlChart'),detail=$('pnlBarDetail');if(!canvas||!detail)return;
  const rect=canvas.getBoundingClientRect(),sx=(canvas.clientWidth||rect.width)/rect.width,sy=(canvas.clientHeight||rect.height)/rect.height,x=(ev.clientX-rect.left)*sx,y=(ev.clientY-rect.top)*sy;
  let hit=(window.__a15Bars||[]).find(function(b){return x>=b.x1&&x<=b.x2&&y>=b.y1&&y<=b.y2});
  if(!hit&&window.__a15Bars&&window.__a15Bars.length){hit=window.__a15Bars.reduce(function(best,b){return Math.abs(x-(b.x1+b.x2)/2)<Math.abs(x-(best.x1+best.x2)/2)?b:best})}
  if(!hit)return;
  const d=hit.data,good=d.pnl>=0;
  detail.innerHTML='<div class="analytics-detail-head"><div><div class="analytics-detail-title">'+d.label+'</div><div class="'+(good?'good':'bad')+'" style="font-size:18px;font-weight:850;margin-top:3px">'+a15FmtSigned(d.pnl)+' USDT · '+a15FmtSigned(d.ret*100)+'%</div></div><button class="btn" style="min-height:34px;padding:6px 9px" onclick="document.getElementById(\'pnlBarDetail\').classList.remove(\'show\')">×</button></div>'+
    '<div class="analytics-detail-grid"><div>Open<b>'+d.open.toFixed(2)+' USDT</b></div><div>Close<b>'+d.close.toFixed(2)+' USDT</b></div><div>High<b>'+d.high.toFixed(2)+' USDT</b></div><div>Low<b>'+d.low.toFixed(2)+' USDT</b></div><div>Snapshots<b>'+d.snapshots+'</b></div><div>Range<b>'+(d.high-d.low).toFixed(2)+' USDT</b></div></div>';
  detail.classList.add('show');
}
function renderAnalytics(allRows){
  a15EnsureUi();
  const raw=(allRows||[]).filter(function(x){return Number(x.planning_usdt)>0}).sort(function(a,b){return new Date(a.ts)-new Date(b.ts)});
  const filtered=filterWindow(raw),rows=a15RowsWithAnchor(raw,filtered),visibleRows=filtered;
  if(!visibleRows.length){
    ['aPnl','aReturn','aRange','aMaxDD','aWinLoss','aBestWorst','aAvgDaily','aWinRate','aVolatility'].forEach(function(id){if($(id))$(id).textContent='—'});
    a15DrawEquity([]);a15DrawPnl([],[]);return;
  }
  const dailyAll=a15Daily(rows),visibleDates=new Set(visibleRows.map(a15DateKey)),daily=dailyAll.filter(function(x){return visibleDates.has(x.date)});
  const startEquity=rows.length>visibleRows.length?Number(rows[0].planning_usdt):Number(visibleRows[0].planning_usdt),endEquity=Number(visibleRows[visibleRows.length-1].planning_usdt),pnl=endEquity-startEquity,ret=startEquity>0?pnl/startEquity:0;
  const vals=visibleRows.map(function(x){return Number(x.planning_usdt)});let peak=startEquity,mdd=0;vals.forEach(function(v){peak=Math.max(peak,v);if(peak>0)mdd=Math.max(mdd,(peak-v)/peak)});
  const activeDays=daily.filter(function(x){return Math.abs(x.pnl)>=.005}),wins=activeDays.filter(function(x){return x.pnl>0}),losses=activeDays.filter(function(x){return x.pnl<0});
  const best=activeDays.length?activeDays.reduce(function(a,b){return b.pnl>a.pnl?b:a}):null,worst=activeDays.length?activeDays.reduce(function(a,b){return b.pnl<a.pnl?b:a}):null;
  const avg=activeDays.length?activeDays.reduce(function(s,x){return s+x.pnl},0)/activeDays.length:0,winRate=activeDays.length?wins.length/activeDays.length:0,vol=a15Std(activeDays.map(function(x){return x.ret}));
  $('aPnl').textContent=a15FmtSigned(pnl)+' USDT';$('aPnl').style.color=pnl>=0?cssVar('--ok','#4cc38a'):cssVar('--bad','#ff7272');
  $('aReturn').textContent=a15FmtSigned(ret*100)+'%';$('aReturn').style.color=ret>=0?cssVar('--ok','#4cc38a'):cssVar('--bad','#ff7272');
  $('aMaxDD').textContent=(mdd*100).toFixed(2)+'%';$('aMaxDD').style.color=mdd>=.15?cssVar('--bad','#ff7272'):mdd>=.08?'#f4c95d':cssVar('--ok','#4cc38a');
  $('aWinLoss').textContent=wins.length+' / '+losses.length;
  $('aBestWorst').innerHTML=best?(a15FmtSigned(best.pnl)+' / '+a15FmtSigned(worst.pnl)+'<span class="subvalue">'+best.date+' / '+worst.date+'</span>'):'—';
  $('aAvgDaily').textContent=(avg>=0?'+':'')+avg.toFixed(2)+' USDT';$('aRange').textContent=Math.max.apply(null,vals).toFixed(2)+' / '+Math.min.apply(null,vals).toFixed(2);
  $('aWinRate').textContent=activeDays.length?(winRate*100).toFixed(1)+'%':'—';$('aVolatility').textContent=activeDays.length>1?(vol*100).toFixed(2)+'%':'—';
  if($('pnlChartTitle'))$('pnlChartTitle').textContent=($('analyticsView').value==='snapshot'?'Snapshot PnL':'Daily PnL')+' · tap a bar for detail';
  a15DrawEquity(visibleRows);a15DrawPnl(rows,daily);
}
const a15LoadHistory=loadHistory;
loadHistory=async function(){const rows=await a15LoadHistory();a15EnsureUi();renderAnalytics(window.__ctcHistory||rows||[]);return rows};
document.addEventListener('DOMContentLoaded',function(){a15EnsureUi();setTimeout(function(){renderAnalytics(window.__ctcHistory||[])},250)});
if(document.readyState!=='loading'){a15EnsureUi();setTimeout(function(){renderAnalytics(window.__ctcHistory||[])},250)}
</script>
'''
appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
