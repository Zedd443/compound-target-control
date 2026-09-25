from __future__ import annotations

import termux_ui_v6 as base

appmod = base.appmod

# Clarify the metric: it is the amount by which today's actual PnL has beaten/missed today's required target.
appmod.HTML = appmod.HTML.replace("Original Daily", "Today's % Target")
appmod.HTML = appmod.HTML.replace(
    "Today's % Target = benchmark compound harian dari plan awal.",
    "Today's % Target = selisih PnL hari ini terhadap target % hari ini. Positif berarti target hari ini sudah terlampaui; negatif berarti masih kurang.",
)

extra_script = r'''
<script>
function utc8DateKeyFromTs(ts){
  const d=new Date(new Date(ts).getTime()+8*3600000);
  return d.toISOString().slice(0,10);
}

function dayDiffUtc8(dateA,dateB){
  const a=new Date(dateA+'T00:00:00+08:00').getTime();
  const b=new Date(dateB+'T00:00:00+08:00').getTime();
  return Math.max(Math.round((b-a)/86400000),0);
}

function computeTodayTargetProgress(p, rows){
  if(!p||!lastPlanSnapshot)return null;
  const today=typeof utc8Day==='function'?utc8Day():new Date(Date.now()+8*3600000).toISOString().slice(0,10);
  const valid=(rows||[]).filter(x=>Number(x.planning_usdt)>0);
  const previousDayRows=valid.filter(x=>String(x.local_date||utc8DateKeyFromTs(x.ts))<today);
  const todayRows=valid.filter(x=>String(x.local_date||utc8DateKeyFromTs(x.ts))===today);

  let dayStartEquity;
  let targetRate;

  if(previousDayRows.length){
    dayStartEquity=Number(previousDayRows[previousDayRows.length-1].planning_usdt);
    const daysRemaining=Math.max(dayDiffUtc8(today,p.target_date),1);
    if(dayStartEquity>0 && Number(p.target_equity)>0){
      targetRate=Math.pow(Number(p.target_equity)/dayStartEquity,1/daysRemaining)-1;
    }
  }

  // First day / no prior close: use the plan's original daily requirement.
  if(!(dayStartEquity>0)){
    dayStartEquity=Number(p.start_equity||planningUsdt());
  }
  if(!Number.isFinite(targetRate)){
    targetRate=Number(lastPlanSnapshot.original_daily_return||0);
  }

  const current=planningUsdt();
  const todayPnlPct=dayStartEquity>0?(current/dayStartEquity)-1:0;
  const progress=todayPnlPct-targetRate;
  return {progress,targetRate,todayPnlPct,dayStartEquity};
}

async function refreshTodayTargetMetric(){
  const p=planData();
  if(!p||!$('mOrigDaily'))return;
  let rows=window.__ctcHistory||[];
  if(!rows.length){
    try{const h=await fetchJson('/api/history');rows=h.rows||[];window.__ctcHistory=rows}catch(e){}
  }
  const x=computeTodayTargetProgress(p,rows);
  if(!x)return;
  const sign=x.progress>=0?'+':'';
  $('mOrigDaily').innerHTML=sign+(x.progress*100).toFixed(2)+'%<span class="subvalue">target '+(x.targetRate*100).toFixed(2)+'% · PnL '+(x.todayPnlPct>=0?'+':'')+(x.todayPnlPct*100).toFixed(2)+'%</span>';
  toneCard('mOrigDaily',x.progress>=0?'pos':'neg');
}

const refreshPlanV7=refreshPlan;
refreshPlan=async function(p){
  await refreshPlanV7(p);
  await refreshTodayTargetMetric();
};

const loadHistoryV7=loadHistory;
loadHistory=async function(){
  const rows=await loadHistoryV7();
  await refreshTodayTargetMetric();
  return rows;
};

setInterval(()=>{if(document.visibilityState==='visible')refreshTodayTargetMetric()},15000);
</script>
'''

appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
