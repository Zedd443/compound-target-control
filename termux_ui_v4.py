from __future__ import annotations

import termux_ui_v3 as base

appmod = base.appmod

# Remove planning jargon. This value is simply the total account equity used by the goal engine.
appmod.HTML = appmod.HTML.replace("Planning Equity", "Total Equity")
appmod.HTML = appmod.HTML.replace("Current Equity", "Current Balance")
appmod.HTML = appmod.HTML.replace(
    "Today's Target = equity yang seharusnya dicapai hari ini menurut kurva compound. Ahead / Behind = selisih equity saat ini terhadap target hari ini.",
    "Today's Target = saldo USDT yang seharusnya dicapai hari ini menurut kurva compound. Ahead / Behind = selisih saldo saat ini terhadap target hari ini.",
)

# Stronger visual states: text + tinted card background + border, so the status is obvious on mobile.
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
  const el=$(id); if(!el)return;
  const card=el.closest('.metric'); if(!card)return;
  card.classList.remove('state-pos','state-neg','state-warn','state-info');
  if(tone)card.classList.add('state-'+tone);
  setTone(id,tone);
}

const refreshPlanV3=refreshPlan;
refreshPlan=async function(p){
  await refreshPlanV3(p);
  if(!lastPlanSnapshot)return;
  const current=planningUsdt();
  const targetToday=lastPlanSnapshot.baseline_equity/fxRate;
  const gap=current-targetToday;
  const dd=updatePeak();
  const pressure=Number(lastPlanSnapshot.target_pressure);

  toneCard('mGap',gap>=0?'pos':'neg');
  toneCard('mDD',dd===0?'pos':dd<0.05?'warn':'neg');
  toneCard('mOpenRisk',acct.open_risk_pct<=0.0075?'pos':acct.open_risk_pct<=0.015?'warn':'neg');
  toneCard('mPressure',pressure<=1?'pos':pressure<=1.10?'warn':'neg');
  toneCard('mDaily','info');
  toneCard('mReq','info');
  toneCard('mOrigDaily','info');
  toneCard('mProgress','info');
  toneCard('mToday','info');
  toneCard('mCurrent',gap>=0?'pos':'warn');

  if($('mDailyPnl')){
    const txt=$('mDailyPnl').textContent.trim();
    toneCard('mDailyPnl',txt.startsWith('+')?'pos':txt.startsWith('-')?'neg':'info');
  }
  if($('mLastMove')){
    const txt=$('mLastMove').textContent.trim();
    toneCard('mLastMove',txt.startsWith('+')&&!txt.startsWith('+0.00')?'pos':txt.startsWith('-')?'neg':'info');
  }
};

const refreshAllV3=refreshAll;
refreshAll=async function(){
  await refreshAllV3();
  if($('planningEq')){
    // Total Equity is the account balance used for goal tracking: Overview when supplied,
    // otherwise the combined wallets that the API can detect.
    $('planningEq').title='Total saldo yang dipakai engine untuk tracking target.';
  }
};

// Make trade output visually distinct too.
const tradeToneObserver=new MutationObserver(()=>{
  if($('rEff'))toneCard('rEff','info');
  if($('maxLoss'))toneCard('maxLoss','neg');
  if($('notional'))toneCard('notional','info');
  if($('margin'))toneCard('margin','info');
  if($('stopDist'))toneCard('stopDist','info');
  if($('vol')){
    const t=$('vol').textContent.toUpperCase();
    toneCard('vol',t.includes('EXTREME')?'neg':t.includes('HIGH')?'warn':'pos');
  }
});
tradeToneObserver.observe(document.body,{subtree:true,childList:true,characterData:true});

setTimeout(()=>refreshAll(),120);
</script>
'''

appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
