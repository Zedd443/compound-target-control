from __future__ import annotations

from datetime import datetime, timezone

from flask import jsonify, request

import termux_launcher as base

appmod = base.appmod


def api_history_v3():
    if request.method == "GET":
        rows = base._load_history()
        return jsonify({"ok": True, "rows": rows[-60:]})

    try:
        data = request.get_json(force=True)
        local_date = str(data.get("local_date", ""))
        try:
            local_hour = int(data.get("local_hour", -1))
        except (TypeError, ValueError):
            local_hour = -1

        rows = base._load_history()
        already_closed = any(
            str(x.get("local_date", "")) == local_date and bool(x.get("daily_close"))
            for x in rows
        ) if local_date else False
        daily_close = bool(local_date and local_hour >= 21 and not already_closed)

        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "local_date": local_date,
            "local_hour": local_hour,
            "daily_close": daily_close,
            "futures_equity": float(data.get("futures_equity", 0)),
            "copy_balance": float(data.get("copy_balance", 0)),
            "planning_usdt": float(data.get("planning_usdt", 0)),
            "fx_rate": float(data.get("fx_rate", 0)),
            "planning_idr": float(data.get("planning_idr", 0)),
            "reason": "daily_close" if daily_close else str(data.get("reason", "refresh")),
        }

        last = rows[-1] if rows else None
        should_append = True
        if last and row["reason"] == "refresh":
            same_values = (
                abs(float(last.get("planning_usdt", 0)) - row["planning_usdt"]) < 0.01
                and abs(float(last.get("fx_rate", 0)) - row["fx_rate"]) < 1
            )
            if same_values:
                should_append = False

        if daily_close:
            should_append = True

        if should_append:
            rows.append(row)
            base._save_history(rows)

        return jsonify({"ok": True, "saved": should_append, "daily_close": daily_close})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"History error: {exc}"}), 400


appmod.app.view_functions["api_history"] = api_history_v3

# Visual hierarchy: positive/negative states should be readable at a glance.
appmod.HTML = appmod.HTML.replace(
    "</style></head>",
    """
.pos{color:var(--ok)!important}.neg{color:var(--bad)!important}.warn{color:#f4c95d!important}.info{color:var(--accent)!important}
#rEff,#notional,#margin,#stopDist{color:var(--accent)}#maxLoss{color:var(--bad)}
.tp span{color:var(--ok)}.history-up{color:var(--ok)}.history-down{color:var(--bad)}.history-flat{color:var(--muted)}
</style></head>""",
)

appmod.HTML = appmod.HTML.replace("Target Today", "Pace Equity Today")
appmod.HTML = appmod.HTML.replace("Gap vs Target Today", "Ahead / Behind Pace")
appmod.HTML = appmod.HTML.replace(
    '<div class="card metric"><small>Open Risk</small><b id="mOpenRisk">—</b></div>',
    '<div class="card metric"><small>Open Risk</small><b id="mOpenRisk">—</b></div>'
    '<div class="card metric"><small>Daily PnL vs Last Close</small><b id="mDailyPnl">—</b></div>'
    '<div class="card metric"><small>Since Last Snapshot</small><b id="mLastMove">—</b></div>',
)
appmod.HTML = appmod.HTML.replace(
    'Target Pressure = required monthly sekarang ÷ required monthly awal. 1.00× berarti sesuai pace awal; di atas 1× berarti pace yang dibutuhkan meningkat.',
    'Pace Equity Today = equity ideal pada kurva compound hari ini. Ahead / Behind menunjukkan selisih equity sekarang terhadap pace tersebut, bukan profit harian. Daily close memakai snapshot pertama pada/ setelah 21:00 waktu HP. Target Pressure = required monthly sekarang ÷ required monthly awal.',
)

# Add a later script that overrides the first-generation UI functions.
extra_script = r'''
<script>
function setTone(id,tone){const el=$(id);if(!el)return;el.classList.remove('pos','neg','warn','info');if(tone)el.classList.add(tone)}
function localDateKey(){const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')}

async function recordSnapshot(reason='refresh'){
  if(!acct||!fxRate)return;
  try{
    const now=new Date();
    await fetchJson('/api/history',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      futures_equity:acct.equity,copy_balance:copyBalance(),planning_usdt:planningUsdt(),fx_rate:fxRate,planning_idr:planningIdr(),reason,
      local_date:localDateKey(),local_hour:now.getHours()
    })});
  }catch(e){}
}

async function saveCopyBalance(){
  localStorage.setItem('ctc_copy_balance',Number($('copyBalance').value||0));
  await refreshAll();
  await recordSnapshot('copy_balance');
  await loadHistory();
}

async function loadHistory(){
  try{
    const h=await fetchJson('/api/history'),rows=h.rows||[];
    if($('historyRows')){
      if(!rows.length){$('historyRows').textContent='Belum ada snapshot.'}
      else $('historyRows').innerHTML=rows.slice(-8).reverse().map((x,ri,rev)=>{
        const idx=rows.indexOf(x),prev=idx>0?rows[idx-1]:null,delta=prev?Number(x.planning_usdt)-Number(prev.planning_usdt):0;
        const cls=delta>0?'history-up':delta<0?'history-down':'history-flat';
        const ds=prev?((delta>=0?'+':'')+delta.toFixed(2)+' USDT'):'start';
        const close=x.daily_close?' · close 21:00+':'';
        return '<div style="padding:7px 0;border-bottom:1px solid var(--line)"><b>'+new Date(x.ts).toLocaleString('id-ID')+'</b> · '+fmtU(x.planning_usdt)+' · <span class="'+cls+'">'+ds+'</span>'+close+'</div>'
      }).join('');
    }
    return rows;
  }catch(e){return []}
}

async function refreshPlan(p){
  const currentIdr=planningIdr(),currentUsdt=planningUsdt();
  lastPlanSnapshot=await fetchJson('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,current_equity:currentIdr})});
  const dd=updatePeak(),paceUsdt=lastPlanSnapshot.baseline_equity/fxRate,gapUsdt=currentUsdt-paceUsdt;
  $('mCurrent').textContent=fmtU(currentUsdt);
  $('mTarget').textContent=fmtI(p.target_equity);
  $('mToday').textContent=fmtU(paceUsdt);
  $('mGap').textContent=(gapUsdt>=0?'+':'')+gapUsdt.toFixed(2)+' USDT';
  $('mDaily').textContent=pct(lastPlanSnapshot.current_daily_return);
  $('mReq').textContent=pct(lastPlanSnapshot.current_monthly_return);
  $('mOrigDaily').textContent=pct(lastPlanSnapshot.original_daily_return);
  $('mPressure').textContent=Number(lastPlanSnapshot.target_pressure).toFixed(2)+'×';
  $('mProgress').textContent=pct(lastPlanSnapshot.progress_pct);
  $('mDays').textContent=lastPlanSnapshot.days_remaining+' hari';
  $('mDD').textContent=pct(dd);
  $('mOpenRisk').textContent=pct(acct.open_risk_pct);
  $('pStart').textContent=fmtI(p.start_equity);$('pStartDate').textContent=p.start_date;$('pTargetDate').textContent=p.target_date;

  setTone('mGap',gapUsdt>=0?'pos':'neg');
  setTone('mDD',dd===0?'pos':dd<0.05?'warn':'neg');
  setTone('mOpenRisk',acct.open_risk_pct<=0.0075?'pos':acct.open_risk_pct<=0.015?'warn':'neg');
  setTone('mPressure',lastPlanSnapshot.target_pressure<=1?'pos':lastPlanSnapshot.target_pressure<=1.10?'warn':'neg');
  setTone('mDaily','info');setTone('mReq','info');setTone('mOrigDaily','info');setTone('mProgress','info');

  const rows=await loadHistory();
  const today=localDateKey();
  const prevClose=[...rows].reverse().find(x=>x.daily_close&&x.local_date&&x.local_date!==today);
  const last=rows.length?rows[rows.length-1]:null;
  if($('mDailyPnl')){
    if(prevClose){const d=currentUsdt-Number(prevClose.planning_usdt),pc=Number(prevClose.planning_usdt)>0?d/Number(prevClose.planning_usdt):0;$('mDailyPnl').textContent=(d>=0?'+':'')+d.toFixed(2)+' USDT · '+(pc>=0?'+':'')+(pc*100).toFixed(2)+'%';setTone('mDailyPnl',d>=0?'pos':'neg')}
    else{$('mDailyPnl').textContent='No prior close';setTone('mDailyPnl','info')}
  }
  if($('mLastMove')){
    if(last){const d=currentUsdt-Number(last.planning_usdt);$('mLastMove').textContent=(d>=0?'+':'')+d.toFixed(2)+' USDT';setTone('mLastMove',d>0?'pos':d<0?'neg':'info')}
    else{$('mLastMove').textContent='—'}
  }
}

const obs=new MutationObserver(()=>{
  if($('vol')){const t=$('vol').textContent.toUpperCase();setTone('vol',t.includes('EXTREME')?'neg':t.includes('HIGH')?'warn':'pos')}
  if($('rEff'))setTone('rEff','info');if($('maxLoss'))setTone('maxLoss','neg');if($('notional'))setTone('notional','info');if($('margin'))setTone('margin','info');
});
obs.observe(document.body,{subtree:true,childList:true,characterData:true});
setTimeout(()=>refreshAll(),50);
</script>
'''

appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")


if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
