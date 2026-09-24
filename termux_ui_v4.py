from __future__ import annotations

import termux_ui_v3 as base

appmod = base.appmod

# Remove planning jargon and keep operational metrics in USDT.
appmod.HTML = appmod.HTML.replace("Planning Equity", "Total Equity")
appmod.HTML = appmod.HTML.replace("Current Equity", "Current Balance")
appmod.HTML = appmod.HTML.replace("Gap vs Today's Target", "Ahead / Behind")
appmod.HTML = appmod.HTML.replace("Gap vs Target Today", "Ahead / Behind")
appmod.HTML = appmod.HTML.replace("Pace Equity Today", "Today's Target")
appmod.HTML = appmod.HTML.replace(
    "Today's Target = equity yang seharusnya dicapai hari ini menurut kurva compound. Ahead / Behind = selisih equity saat ini terhadap target hari ini.",
    "Today's Target = saldo USDT yang seharusnya dicapai hari ini menurut kurva compound. Ahead / Behind = selisih saldo saat ini terhadap target hari ini.",
)

# Strong visual states: text + tinted card background + border.
appmod.HTML = appmod.HTML.replace(
    "</style></head>",
    r'''
.metric.state-pos{background:rgba(76,195,138,.10);border-color:rgba(76,195,138,.45)}
.metric.state-neg{background:rgba(255,114,114,.10);border-color:rgba(255,114,114,.48)}
.metric.state-warn{background:rgba(244,201,93,.10);border-color:rgba(244,201,93,.45)}
.metric.state-info{background:rgba(90,167,255,.09);border-color:rgba(90,167,255,.38)}
.metric.state-pos b{color:var(--ok)!important}.metric.state-neg b{color:var(--bad)!important}
.metric.state-warn b{color:#f4c95d!important}.metric.state-info b{color:var(--accent)!important}
</style></head>''',
)

extra_script = r'''
<script>
function toneCard(id,tone){
  const el=$(id);if(!el)return;
  const card=el.closest('.metric');if(!card)return;
  card.classList.remove('state-pos','state-neg','state-warn','state-info');
  if(tone)card.classList.add('state-'+tone);
  if(typeof setTone==='function')setTone(id,tone);
}

function normalizePlan(p){
  if(!p)return null;
  if(p.plan_currency==='USDT' && p.target_equity_idr)return p;
  // One-time migration from the older IDR-native plan. This prevents live FX
  // movement from making Today's Target drift immediately after plan start.
  const oldTargetIdr=Number(p.target_equity||0);
  const oldStartIdr=Number(p.start_equity||0);
  const rate=Number(p.start_fx||fxRate||1);
  const migrated={...p,
    start_equity:oldStartIdr/rate,
    target_equity:oldTargetIdr/rate,
    target_equity_idr:oldTargetIdr,
    start_fx:rate,
    plan_currency:'USDT'
  };
  localStorage.setItem('ctc_plan',JSON.stringify(migrated));
  return migrated;
}

const oldPlanData=planData;
planData=function(){return normalizePlan(oldPlanData())};

startPlan=async function(){
  if(!acct||!fxRate)return;
  const targetIdr=Number($('target').value);
  const startUsdt=planningUsdt();
  const p={
    start_equity:startUsdt,
    target_equity:targetIdr/fxRate,
    target_equity_idr:targetIdr,
    start_fx:fxRate,
    plan_currency:'USDT',
    start_date:today(),
    target_date:addMonths(today(),$('months').value)
  };
  localStorage.setItem('ctc_plan',JSON.stringify(p));
  localStorage.setItem('ctc_peak_equity',startUsdt);
  await recordSnapshot('plan_start');
  await refreshAll();
};

refreshPlan=async function(rawPlan){
  const p=normalizePlan(rawPlan),current=planningUsdt();
  lastPlanSnapshot=await fetchJson('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    start_equity:p.start_equity,target_equity:p.target_equity,start_date:p.start_date,target_date:p.target_date,current_equity:current
  })});
  const dd=updatePeak(),targetToday=Number(lastPlanSnapshot.baseline_equity),gap=current-targetToday,pressure=Number(lastPlanSnapshot.target_pressure);
  $('mCurrent').textContent=fmtU(current);
  $('mTarget').textContent=fmtI(p.target_equity_idr);
  $('mToday').textContent=fmtU(targetToday);
  $('mGap').textContent=(gap>=0?'+':'')+gap.toFixed(2)+' USDT';
  $('mDaily').textContent=pct(lastPlanSnapshot.current_daily_return);
  $('mReq').textContent=pct(lastPlanSnapshot.current_monthly_return);
  $('mOrigDaily').textContent=pct(lastPlanSnapshot.original_daily_return);
  $('mPressure').textContent=pressure.toFixed(2)+'×';
  $('mProgress').textContent=pct(lastPlanSnapshot.progress_pct);
  $('mDays').textContent=lastPlanSnapshot.days_remaining+' hari';
  $('mDD').textContent=pct(dd);
  $('mOpenRisk').textContent=pct(acct.open_risk_pct);
  $('pStart').textContent=fmtU(p.start_equity);
  $('pStartDate').textContent=p.start_date;
  $('pTargetDate').textContent=p.target_date;

  toneCard('mGap',gap>=0?'pos':'neg');
  toneCard('mDD',dd===0?'pos':dd<0.05?'warn':'neg');
  toneCard('mOpenRisk',acct.open_risk_pct<=0.0075?'pos':acct.open_risk_pct<=0.015?'warn':'neg');
  toneCard('mPressure',pressure<=1?'pos':pressure<=1.10?'warn':'neg');
  toneCard('mDaily','info');toneCard('mReq','info');toneCard('mOrigDaily','info');toneCard('mProgress','info');toneCard('mToday','info');toneCard('mCurrent',gap>=0?'pos':'warn');

  const rows=await loadHistory(),day=typeof utc8Day==='function'?utc8Day():today();
  const prior=[...rows].reverse().find(x=>x.local_date&&x.local_date<day),last=rows.length?rows[rows.length-1]:null;
  if($('mDailyPnl')){
    if(prior){const d=current-Number(prior.planning_usdt),pc=Number(prior.planning_usdt)>0?d/Number(prior.planning_usdt):0;$('mDailyPnl').textContent=(d>=0?'+':'')+d.toFixed(2)+' USDT · '+(pc>=0?'+':'')+(pc*100).toFixed(2)+'%';toneCard('mDailyPnl',d>=0?'pos':'neg')}
    else{$('mDailyPnl').textContent='No prior-day snapshot';toneCard('mDailyPnl','info')}
  }
  if($('mLastMove')){
    if(last){const d=current-Number(last.planning_usdt);$('mLastMove').textContent=(d>=0?'+':'')+d.toFixed(2)+' USDT';toneCard('mLastMove',d>0?'pos':d<0?'neg':'info')}
    else{$('mLastMove').textContent='—';toneCard('mLastMove','info')}
  }
};

parseAndSize=async function(){
  try{
    const p=planData();if(!p)throw new Error('Start Plan dulu.');
    const signal=await fetchJson('/api/parse-signal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:$('signalText').value})});
    $('parsed').textContent=signal.symbol+' '+signal.side+' · Entry '+signal.entry+(signal.entry_low!==signal.entry_high?' ('+signal.entry_low+'-'+signal.entry_high+')':'')+' · SL '+signal.stop_loss+' · '+signal.targets.length+' TP · '+signal.leverage+'x '+signal.leverage_source;
    const dd=updatePeak();
    const result=await fetchJson('/api/size',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      start_equity:p.start_equity,target_equity:p.target_equity,start_date:p.start_date,target_date:p.target_date,
      reporting_equity:planningUsdt(),trading_equity:acct.equity,drawdown_pct:dd,open_risk_pct:acct.open_risk_pct,signal
    })});
    $('tradeResult').classList.remove('hidden');
    $('rEff').textContent=pct(result.effective_risk_pct);$('maxLoss').textContent=fmtU(result.max_planned_loss);$('notional').textContent=fmtU(result.recommended_notional);$('margin').textContent=fmtU(result.required_margin);
    $('vol').textContent=result.volatility.regime.toUpperCase()+(result.volatility.atr_pct?' · ATR '+pct(result.volatility.atr_pct):'');$('stopDist').textContent=pct(result.stop_distance_pct);
    $('partialProfile').textContent='Profile: '+result.partial.profile+' · Target pressure '+Number(result.target_pressure).toFixed(2)+'× · Weighted listed-TP R '+Number(result.partial.weighted_r).toFixed(2)+'R';
    $('tpRows').innerHTML=result.partial.targets.map(x=>{const gain=(signal.side==='LONG'?(x.price-signal.entry):(signal.entry-x.price))/signal.entry;return '<div class="tp"><b>'+x.name+' · '+Number(x.price).toLocaleString('en-US')+'</b><span>'+Number(x.r_multiple).toFixed(2)+'R · '+(gain*100).toFixed(2)+'%</span><b>'+Math.round(x.fraction*100)+'%</b></div>'}).join('');
    $('runner').textContent=Math.round(result.partial.runner_fraction*100)+'%';
    toneCard('rEff','info');toneCard('maxLoss','neg');toneCard('notional','info');toneCard('margin','info');toneCard('stopDist','info');
    const vt=String(result.volatility.regime).toUpperCase();toneCard('vol',vt==='EXTREME'?'neg':vt==='HIGH'?'warn':'pos');
  }catch(e){$('parsed').innerHTML='<span class="bad">'+e.message+'</span>'}
};

const previousRefreshAll=refreshAll;
refreshAll=async function(){
  await previousRefreshAll();
  const p=oldPlanData();
  if(p)normalizePlan(p);
  if($('planningEq'))$('planningEq').title='Total saldo Binance Overview yang dipakai untuk tracking target.';
};

setTimeout(()=>refreshAll(),120);
</script>
'''

appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
