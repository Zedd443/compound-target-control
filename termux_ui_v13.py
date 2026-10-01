from __future__ import annotations

import termux_ui_v12 as base

appmod = base.appmod

# Add a same-day stretch target without replacing the original compound-curve target.
# Once Today's Target is reached, Adjusted Target is calculated once from the
# actual balance and the then-current Required Daily rate, then stays fixed for
# the rest of that UTC+8 day. It resets automatically on the next calendar day.
needle = '<div class="card metric"><small>Today\'s Target</small><b id="mToday">—</b></div>'
replacement = needle + '<div class="card metric"><small>Adjusted Target</small><b id="mAdjusted">—</b></div>'
appmod.HTML = appmod.HTML.replace(needle, replacement)

extra_script = r'''
<script>
function adjustedTargetStorageKey(p){
  const day=(typeof ctcUtc8DateKey==='function')?ctcUtc8DateKey():new Date(Date.now()+8*3600000).toISOString().slice(0,10);
  return 'ctc_adjusted_target_'+String((p&&p.plan_id)||'plan')+'_'+day;
}

function adjustedTargetToday(p){
  if(!p)return null;
  const original=(typeof dailyTarget==='function')?Number(dailyTarget(p)):0;
  const current=Number(planningUsdt());
  if(!(original>0&&current>0))return null;

  const key=adjustedTargetStorageKey(p);
  const saved=Number(localStorage.getItem(key)||0);
  if(saved>0)return {target:saved,original,locked:true};

  // Before the original target is reached, Adjusted Target is simply waiting.
  if(current<original)return {target:original,original,locked:false};

  // Lock one stretch target for the rest of today. Required Daily is already
  // recalculated from current balance to the final target/deadline.
  const req=Math.max(Number((lastPlanSnapshot&&lastPlanSnapshot.current_daily_return)||0),0);
  const target=current*(1+req);
  if(target>0&&Number.isFinite(target))localStorage.setItem(key,String(target));
  return {target,original,locked:true};
}

function renderAdjustedTarget(){
  if(!$('mAdjusted'))return;
  const p=planData();
  if(!p){$('mAdjusted').textContent='—';return}
  const x=adjustedTargetToday(p);
  if(!x){$('mAdjusted').textContent='—';return}

  const current=Number(planningUsdt()),gap=current-x.target;
  $('mAdjusted').innerHTML=fmtU(x.target)+'<span class="subvalue">'+
    (x.locked?((gap>=0?'+':'')+gap.toFixed(2)+' USDT'):'unlock after Today\'s Target')+
    '</span>';
  if(!x.locked)toneCard('mAdjusted','info');
  else toneCard('mAdjusted',gap>=0?'pos':'warn');
}

const refreshPlanV13=refreshPlan;
refreshPlan=async function(p){
  await refreshPlanV13(p);
  renderAdjustedTarget();
};

const loadHistoryV13=loadHistory;
loadHistory=async function(){
  const rows=await loadHistoryV13();
  renderAdjustedTarget();
  return rows;
};

setInterval(()=>{if(document.visibilityState==='visible')renderAdjustedTarget()},15000);
</script>
'''

appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
