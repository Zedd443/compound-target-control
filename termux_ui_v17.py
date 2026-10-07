from __future__ import annotations

import termux_ui_v16 as base

appmod = base.appmod

extra_style = r'''
<style>
/* v17 fix: v14 set #mission{display:block}, which overrode .hidden and kept
   Mission visible when Trade was selected. Restore true tab behavior. */
#mission.hidden,#trade.hidden,#plan.hidden{display:none!important}

/* Trade should look like the original calculator: tabs -> calculator -> result. */
body.trade-mode .wrap > #status,
body.trade-mode .wrap > .grid,
body.trade-mode #ctcCopyBalanceCard{display:none!important}
body.trade-mode #trade{display:block!important}
body.trade-mode #trade .trade-shell{display:none!important}
body.trade-mode #trade>.card:first-of-type{margin-top:0}
body.trade-mode #trade>.card:first-of-type:before,
body.trade-mode #trade>.card:first-of-type:after{display:none!important}
body.trade-mode #trade #signalText{min-height:170px}
body.trade-mode #tradeResult>.grid{margin-top:14px}
</style>
'''
appmod.HTML = appmod.HTML.replace("</head>", extra_style + "</head>")

extra_script = r'''
<script>
function ctcV17ApplyTabState(id){
  ['mission','trade','plan'].forEach(function(name){
    const el=document.getElementById(name);
    if(!el)return;
    el.classList.toggle('hidden',name!==id);
  });
  document.body.classList.toggle('trade-mode',id==='trade');
}
const ctcV17PrevShowTab=showTab;
showTab=function(id,btn){
  ctcV17PrevShowTab(id,btn);
  ctcV17ApplyTabState(id);
  if(id==='trade'){
    const text=document.getElementById('signalText');
    if(text)setTimeout(function(){text.scrollIntoView({block:'start',behavior:'instant'})},0);
  }
};
document.addEventListener('DOMContentLoaded',function(){
  const active=document.querySelector('.tab.active');
  if(active){
    const onclick=active.getAttribute('onclick')||'';
    const m=onclick.match(/showTab\('([^']+)'/);
    if(m)ctcV17ApplyTabState(m[1]);
  }
});
</script>
'''
appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
