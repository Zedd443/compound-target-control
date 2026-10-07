from __future__ import annotations

import termux_ui_v15 as base

appmod = base.appmod

extra_style = r'''
<style>
body.trade-mode #ctcWalletOverview,
body.trade-mode #ctcCopyBalanceCard,
body.trade-mode #status{display:none!important}
body.trade-mode .wrap{max-width:760px}
body.trade-mode .head{margin-bottom:6px}
.trade-shell{display:none}
body.trade-mode .trade-shell{display:block}
.trade-shell{margin-bottom:12px}
.trade-shell-title{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:7px}
.trade-context{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.trade-context-card{padding:10px 11px;border:1px solid var(--line);border-radius:13px;background:#0d141d;min-width:0}
.trade-context-card small{display:block;color:var(--muted);font-size:9px;margin-bottom:4px}
.trade-context-card b{display:block;font-size:14px;overflow-wrap:anywhere}
#trade>.card:first-child{padding:16px}
#trade>.card:first-child:before{content:'Trade Calculator';display:block;font-size:20px;font-weight:850;letter-spacing:-.35px;margin-bottom:3px}
#trade>.card:first-child:after{content:'Paste signal Axion, lalu sistem hitung R, VOLUME, MARGIN dan partial TP.';display:block;color:var(--muted);font-size:11px;line-height:1.45;margin-bottom:14px}
#trade .field label{font-size:11px}
#trade #signalText{min-height:210px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:14px;line-height:1.45}
#trade #parsed{padding:10px 11px;border:1px dashed #2a3950;border-radius:11px;background:#0b121a}
#tradeResult>.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
#tradeResult>.grid .metric{padding:13px}
#tradeResult>.grid .metric small{font-size:10px}
#tradeResult>.grid .metric b{font-size:18px}
#tradeResult>.grid .metric:nth-child(1),
#tradeResult>.grid .metric:nth-child(3){background:linear-gradient(180deg,#111d2a,#0d151f)}
#tradeResult>.grid .metric:nth-child(2){background:linear-gradient(180deg,#21151a,#151116)}
.trade-calc-hint{margin-top:9px;font-size:10px;color:var(--muted);line-height:1.45}
@media(max-width:560px){
  body.trade-mode .head .sub{display:none}
  .trade-context{grid-template-columns:repeat(3,minmax(0,1fr))}
  .trade-context-card{padding:9px 8px}
  .trade-context-card b{font-size:12px}
  #trade>.card:first-child{padding:13px}
  #trade>.card:first-child:before{font-size:18px}
  #trade #signalText{min-height:190px}
}
</style>
'''
appmod.HTML = appmod.HTML.replace("</head>", extra_style + "</head>")

extra_script = r'''
<script>
function ctcTradeModeSetup(){
  const wrap=document.querySelector('.wrap');
  if(!wrap||document.body.dataset.tradeModeReady==='1')return;
  document.body.dataset.tradeModeReady='1';

  const status=$('status');
  if(status){
    const wallet=status.nextElementSibling;
    if(wallet&&wallet.classList.contains('grid'))wallet.id='ctcWalletOverview';
    const copy=wallet&&wallet.nextElementSibling;
    if(copy&&copy.classList.contains('card'))copy.id='ctcCopyBalanceCard';
  }

  const trade=$('trade');
  if(trade&&!trade.querySelector('.trade-shell')){
    const shell=document.createElement('div');
    shell.className='trade-shell';
    shell.innerHTML=
      '<div class="trade-shell-title">Sizing Context</div>'+
      '<div class="trade-context">'+
        '<div class="trade-context-card"><small>Futures Equity</small><b id="tradeCtxEquity">—</b></div>'+
        '<div class="trade-context-card"><small>Available</small><b id="tradeCtxAvailable">—</b></div>'+
        '<div class="trade-context-card"><small>Open Risk</small><b id="tradeCtxRisk">—</b></div>'+
      '</div>';
    trade.insertBefore(shell,trade.firstChild);

    const calcCard=trade.querySelector('.card');
    if(calcCard){
      const hint=document.createElement('div');
      hint.className='trade-calc-hint';
      hint.textContent='Sizing memakai Futures Equity. Leverage mengubah MARGIN yang dibutuhkan, bukan nilai 1R.';
      calcCard.appendChild(hint);
    }
  }
  ctcRefreshTradeContext();
}
function ctcRefreshTradeContext(){
  if($('tradeCtxEquity'))$('tradeCtxEquity').textContent=acct?fmtU(acct.equity):'—';
  if($('tradeCtxAvailable'))$('tradeCtxAvailable').textContent=acct?fmtU(acct.available):'—';
  if($('tradeCtxRisk'))$('tradeCtxRisk').textContent=acct?pct(acct.open_risk_pct):'—';
}
function ctcSetPageMode(id){
  document.body.classList.toggle('trade-mode',id==='trade');
  if(id==='trade')ctcRefreshTradeContext();
  window.scrollTo({top:0,behavior:'instant'});
}
const ctcShowTabOriginal=showTab;
showTab=function(id,btn){
  ctcShowTabOriginal(id,btn);
  ctcSetPageMode(id);
};
const ctcRefreshAllV16=refreshAll;
refreshAll=async function(){
  const out=await ctcRefreshAllV16();
  ctcRefreshTradeContext();
  return out;
};
document.addEventListener('DOMContentLoaded',ctcTradeModeSetup);
if(document.readyState!=='loading')ctcTradeModeSetup();
</script>
'''
appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
