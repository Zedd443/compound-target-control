from __future__ import annotations

import termux_ui_v10 as base

appmod = base.appmod

# Keep Today's Target fixed for the whole UTC+8 calendar day.
# The previous v5 implementation interpolated by milliseconds, so the target
# slowly increased during the same day (e.g. 1016 -> 1018).
extra_script = r'''
<script>
function ctcUtc8DateKey(){
  return new Date(Date.now()+8*3600000).toISOString().slice(0,10);
}

function ctcCalendarDays(a,b){
  const x=new Date(a+'T00:00:00+08:00').getTime();
  const y=new Date(b+'T00:00:00+08:00').getTime();
  return Math.round((y-x)/86400000);
}

function dailyTarget(p){
  if(!p)return 0;
  const start=Number(p.start_equity),target=Number(p.target_equity);
  if(!(start>0&&target>0))return start||0;
  const total=Math.max(ctcCalendarDays(p.start_date,p.target_date),1);
  const elapsed=Math.min(Math.max(ctcCalendarDays(p.start_date,ctcUtc8DateKey()),0),total);
  return start*Math.exp(Math.log(target/start)*(elapsed/total));
}

renderLiveTargetOnly=function(){
  const p=planData();if(!p||!fxRate||!$('mToday')||!$('mGap'))return;
  const targetToday=dailyTarget(p),current=planningUsdt(),gap=current-targetToday;
  $('mToday').textContent=fmtU(targetToday);
  $('mGap').innerHTML=(gap>=0?'+':'')+gap.toFixed(2)+' USDT<span class="subvalue">≈ '+fmtI(Math.abs(gap)*fxRate)+(gap<0?' behind':'')+'</span>';
  toneCard('mGap',gap>=0?'pos':'neg');toneCard('mToday','info');toneCard('mCurrent',gap>=0?'pos':'warn');
};

// Re-render periodically only to catch the UTC+8 date change. The value is
// otherwise constant throughout the day.
setInterval(()=>{if(document.visibilityState==='visible')renderLiveTargetOnly()},15000);
</script>
'''

appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
