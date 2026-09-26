from __future__ import annotations

import termux_ui_v9 as base

appmod = base.appmod

# Use the user's trading terminology in the UI. Internally the backend keeps
# recommended_notional as the position value before leverage, but the screen
# calls that value VOLUME and keeps required_margin as MARGIN.
appmod.HTML = appmod.HTML.replace("Recommended Notional", "VOLUME")
appmod.HTML = appmod.HTML.replace("Recommended notional", "VOLUME")
appmod.HTML = appmod.HTML.replace("Notional", "VOLUME")
appmod.HTML = appmod.HTML.replace("Required Margin", "MARGIN")
appmod.HTML = appmod.HTML.replace("Required margin", "MARGIN")

# Default leverage is adaptive only when the signal does not explicitly specify leverage.
# Futures equity < $500 -> 30x default. Otherwise keep 10x default.
extra_script = r'''
<script>
parseAndSize=async function(){
  try{
    const p=planData();if(!p)throw new Error('Start Plan dulu.');
    const raw=$('signalText').value;
    const signal=await fetchJson('/api/parse-signal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:raw})});
    if(String(signal.leverage_source||'').toLowerCase()==='default'){
      signal.leverage=(acct&&Number(acct.equity)<500)?30:10;
      signal.leverage_source='auto';
    }
    $('parsed').textContent=signal.symbol+' '+signal.side+' · Entry '+signal.entry+(signal.entry_low!==signal.entry_high?' ('+signal.entry_low+'-'+signal.entry_high+')':'')+' · SL '+signal.stop_loss+' · '+signal.targets.length+' TP · '+signal.leverage+'x '+signal.leverage_source;
    const dd=updatePeak();
    const result=await fetchJson('/api/size',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      start_equity:p.start_equity,target_equity:p.target_equity,start_date:p.start_date,target_date:p.target_date,
      reporting_equity:planningUsdt(),trading_equity:acct.equity,drawdown_pct:dd,open_risk_pct:acct.open_risk_pct,signal
    })});
    window.__ctcLastSignal=signal;
    window.__ctcLastSizing=result;
    $('tradeResult').classList.remove('hidden');
    $('rEff').textContent=pct(result.effective_risk_pct);$('maxLoss').textContent=fmtU(result.max_planned_loss);$('notional').textContent=fmtU(result.recommended_notional);$('margin').textContent=fmtU(result.required_margin);
    $('vol').textContent=result.volatility.regime.toUpperCase()+(result.volatility.atr_pct?' · ATR '+pct(result.volatility.atr_pct):'');$('stopDist').textContent=pct(result.stop_distance_pct);
    $('partialProfile').textContent='Profile: '+result.partial.profile+' · Target pressure '+Number(result.target_pressure).toFixed(2)+'× · Weighted listed-TP R '+Number(result.partial.weighted_r).toFixed(2)+'R';
    $('tpRows').innerHTML=result.partial.targets.map(x=>{const gain=(signal.side==='LONG'?(x.price-signal.entry):(signal.entry-x.price))/signal.entry;return '<div class="tp"><b>'+x.name+' · '+Number(x.price).toLocaleString('en-US')+'</b><span>'+Number(x.r_multiple).toFixed(2)+'R · '+(gain*100).toFixed(2)+'%</span><b>'+Math.round(x.fraction*100)+'%</b></div>'}).join('');
    $('runner').textContent=Math.round(result.partial.runner_fraction*100)+'%';
    $('saveTradeBtn').classList.remove('hidden');
    $('saveTradeNote').classList.add('hidden');
    toneCard('rEff','info');toneCard('maxLoss','neg');toneCard('notional','info');toneCard('margin','info');toneCard('stopDist','info');
    const vt=String(result.volatility.regime).toUpperCase();toneCard('vol',vt==='EXTREME'?'neg':vt==='HIGH'?'warn':'pos');
  }catch(e){
    window.__ctcLastSignal=null;window.__ctcLastSizing=null;
    if($('saveTradeBtn'))$('saveTradeBtn').classList.add('hidden');
    $('parsed').innerHTML='<span class="bad">'+e.message+'</span>';
  }
};
</script>
'''

appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
