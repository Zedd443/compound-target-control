from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import jsonify, request

import termux_launcher as base

appmod = base.appmod
UTC8 = timezone(timedelta(hours=8))


def _asset_to_usdt(asset: str, amount: float) -> float | None:
    asset = asset.upper()
    if amount <= 0:
        return 0.0
    if asset == "USDT":
        return amount
    # Common dollar stables are normally close enough for planning, but prefer live pairs.
    try:
        return amount * appmod.client.spot_ticker_price(f"{asset}USDT")
    except Exception:
        pass
    # Bridge unusual assets through BTC when a direct USDT pair is unavailable.
    try:
        asset_btc = appmod.client.spot_ticker_price(f"{asset}BTC")
        btc_usdt = appmod.client.spot_ticker_price("BTCUSDT")
        return amount * asset_btc * btc_usdt
    except Exception:
        return None


def _spot_value_usdt() -> tuple[float, int]:
    account = appmod.client.spot_account()
    total = 0.0
    unpriced = 0
    for row in account.get("balances", []):
        amount = float(row.get("free", 0) or 0) + float(row.get("locked", 0) or 0)
        if amount <= 0:
            continue
        value = _asset_to_usdt(str(row.get("asset", "")), amount)
        if value is None:
            unpriced += 1
        else:
            total += value
    return total, unpriced


def _funding_value_usdt() -> tuple[float, int]:
    rows = appmod.client.funding_assets()
    total = 0.0
    unpriced = 0
    for row in rows:
        amount = sum(
            float(row.get(key, 0) or 0)
            for key in ("free", "locked", "freeze", "withdrawing")
        )
        if amount <= 0:
            continue
        value = _asset_to_usdt(str(row.get("asset", "")), amount)
        if value is None:
            unpriced += 1
        else:
            total += value
    return total, unpriced


def api_wallet_summary():
    # Spot/Funding details stay backend-only. UI gets only the combined known-wallet total.
    errors: list[str] = []
    futures = 0.0
    spot = 0.0
    funding = 0.0
    unpriced = 0
    try:
        account = appmod.client.account()
        futures = float(account.get("totalMarginBalance", account.get("totalWalletBalance", 0)) or 0)
    except Exception as exc:
        errors.append(f"futures: {exc}")
    try:
        spot, n = _spot_value_usdt()
        unpriced += n
    except Exception as exc:
        errors.append(f"spot: {exc}")
    try:
        funding, n = _funding_value_usdt()
        unpriced += n
    except Exception as exc:
        errors.append(f"funding: {exc}")
    return jsonify({
        "ok": True,
        "known_total_usdt": futures + spot + funding,
        "unpriced_assets": unpriced,
        "partial": bool(errors),
        "warning": " | ".join(errors[:2]),
    })


def api_history_v3():
    if request.method == "GET":
        rows = base._load_history()
        return jsonify({"ok": True, "rows": rows[-90:]})

    try:
        data = request.get_json(force=True)
        now_local = datetime.now(UTC8)
        local_date = now_local.date().isoformat()
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "local_date": local_date,
            "futures_equity": float(data.get("futures_equity", 0)),
            "overview_balance": float(data.get("overview_balance", 0)),
            "known_wallet_usdt": float(data.get("known_wallet_usdt", 0)),
            "estimated_untracked_usdt": float(data.get("estimated_untracked_usdt", 0)),
            "planning_usdt": float(data.get("planning_usdt", 0)),
            "fx_rate": float(data.get("fx_rate", 0)),
            "planning_idr": float(data.get("planning_idr", 0)),
            "reason": str(data.get("reason", "refresh")),
        }
        rows = base._load_history()
        last = rows[-1] if rows else None
        should_append = True
        if last and row["reason"] == "refresh":
            same_values = (
                abs(float(last.get("planning_usdt", 0)) - row["planning_usdt"]) < 0.01
                and abs(float(last.get("fx_rate", 0)) - row["fx_rate"]) < 1
            )
            if same_values:
                should_append = False
        if should_append:
            rows.append(row)
            base._save_history(rows)
        return jsonify({"ok": True, "saved": should_append, "local_date": local_date})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"History error: {exc}"}), 400


appmod.app.view_functions["api_history"] = api_history_v3
appmod.app.add_url_rule("/api/wallet-summary", "api_wallet_summary", api_wallet_summary, methods=["GET"])

# Keep Spot/Funding reconciliation behind the scenes. The user only enters the Binance Overview total.
appmod.HTML = appmod.HTML.replace(
    "Copy Trading balance (USDT, manual karena standard Futures API tidak membacanya)",
    "Binance Overview balance (USDT)",
)
appmod.HTML = appmod.HTML.replace("Save copy balance", "Save overview balance")
appmod.HTML = appmod.HTML.replace(
    '<div id="accountNote" class="notice"></div>',
    '<div id="accountNote" class="notice"></div><div id="untrackedNote" class="notice"></div>',
)

# Simpler mission labels and visual hierarchy.
appmod.HTML = appmod.HTML.replace("Pace Equity Today", "Today's Target")
appmod.HTML = appmod.HTML.replace("Ahead / Behind Pace", "Ahead / Behind")
appmod.HTML = appmod.HTML.replace("Target Today", "Today's Target")
appmod.HTML = appmod.HTML.replace("Gap vs Target Today", "Ahead / Behind")
appmod.HTML = appmod.HTML.replace(
    '<div class="card metric"><small>Open Risk</small><b id="mOpenRisk">—</b></div>',
    '<div class="card metric"><small>Open Risk</small><b id="mOpenRisk">—</b></div>'
    '<div class="card metric"><small>Today PnL</small><b id="mDailyPnl">—</b></div>'
    '<div class="card metric"><small>Since Last Snapshot</small><b id="mLastMove">—</b></div>',
)
appmod.HTML = appmod.HTML.replace(
    "</style></head>",
    """
.pos{color:var(--ok)!important}.neg{color:var(--bad)!important}.warn{color:#f4c95d!important}.info{color:var(--accent)!important}
#rEff,#notional,#margin,#stopDist{color:var(--accent)}#maxLoss{color:var(--bad)}
.tp span{color:var(--ok)}.history-up{color:var(--ok)}.history-down{color:var(--bad)}.history-flat{color:var(--muted)}
</style></head>""",
)
appmod.HTML = appmod.HTML.replace(
    'Target Pressure = required monthly sekarang ÷ required monthly awal. 1.00× berarti sesuai pace awal; di atas 1× berarti pace yang dibutuhkan meningkat.',
    "Today's Target = equity yang seharusnya dicapai hari ini menurut kurva compound. Ahead / Behind = selisih equity saat ini terhadap target hari ini. Today PnL reset setiap 00:00 UTC+8 berdasarkan snapshot terakhir sebelum hari baru. Target Pressure = required monthly sekarang ÷ required monthly awal.",
)

extra_script = r'''
<script>
let walletSummary={known_total_usdt:0,partial:false,warning:''};
function setTone(id,tone){const el=$(id);if(!el)return;el.classList.remove('pos','neg','warn','info');if(tone)el.classList.add(tone)}
function utc8Day(){const d=new Date(Date.now()+8*3600000);return d.toISOString().slice(0,10)}
function overviewBalance(){return Number(localStorage.getItem('ctc_overview_balance')||0)}
function copyBalance(){return overviewBalance()}
function planningUsdt(){const ov=overviewBalance();return ov>0?ov:(walletSummary.known_total_usdt||((acct&&acct.equity)||0))}
function planningIdr(){return fxRate?planningUsdt()*fxRate:0}
function estimatedUntracked(){return Math.max(planningUsdt()-Number(walletSummary.known_total_usdt||0),0)}

async function recordSnapshot(reason='refresh'){
  if(!acct||!fxRate)return;
  try{await fetchJson('/api/history',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    futures_equity:acct.equity,overview_balance:overviewBalance(),known_wallet_usdt:Number(walletSummary.known_total_usdt||0),
    estimated_untracked_usdt:estimatedUntracked(),planning_usdt:planningUsdt(),fx_rate:fxRate,planning_idr:planningIdr(),reason
  })})}catch(e){}
}

async function saveCopyBalance(){
  localStorage.setItem('ctc_overview_balance',Number($('copyBalance').value||0));
  await refreshAll();await recordSnapshot('overview_update');await loadHistory();
}

async function refreshAll(){
  try{
    $('status').textContent='Refreshing...';
    acct=await fetchJson('/api/account');
    const f=await fetchJson('/api/fx');fxRate=f.rate;fxSource=f.source;
    try{walletSummary=await fetchJson('/api/wallet-summary')}catch(e){walletSummary={known_total_usdt:acct.equity,partial:true,warning:e.message}}
    $('copyBalance').value=overviewBalance()||'';
    $('eq').textContent=fmtU(acct.equity);$('avail').textContent=fmtU(acct.available);
    $('planningEq').textContent=fmtU(planningUsdt())+' · '+fmtI(planningIdr());$('fx').textContent='Rp'+Math.round(fxRate).toLocaleString('id-ID');
    $('accountNote').textContent='FX: '+fxSource+(acct.missing_stop_symbols.length?' · posisi tanpa SL: '+acct.missing_stop_symbols.join(', '):'');
    $('untrackedNote').textContent=overviewBalance()>0?'Estimated Copy/Untracked: '+fmtU(estimatedUntracked())+(walletSummary.partial?' · wallet scan partial':''):'Masukkan total Binance Overview untuk estimasi Copy/Untracked otomatis.';
    $('status').innerHTML='<span class="good">Connected</span> · live Binance';
    const p=planData();
    if(p){$('createPlan').classList.add('hidden');$('planView').classList.remove('hidden');await refreshPlan(p);await recordSnapshot('refresh')}
    else{$('createPlan').classList.remove('hidden');$('planView').classList.add('hidden')}
  }catch(e){$('status').innerHTML='<span class="bad">'+e.message+'</span>'}
}

async function startPlan(){
  if(!acct||!fxRate)return;
  const p={start_equity:planningIdr(),target_equity:Number($('target').value),start_date:today(),target_date:addMonths(today(),$('months').value)};
  localStorage.setItem('ctc_plan',JSON.stringify(p));localStorage.setItem('ctc_peak_equity',planningUsdt());
  await recordSnapshot('plan_start');await refreshAll();
}

async function loadHistory(){
  try{
    const h=await fetchJson('/api/history'),rows=h.rows||[];
    if($('historyRows')){
      if(!rows.length){$('historyRows').textContent='Belum ada snapshot.'}
      else $('historyRows').innerHTML=rows.slice(-8).reverse().map((x)=>{
        const idx=rows.indexOf(x),prev=idx>0?rows[idx-1]:null,delta=prev?Number(x.planning_usdt)-Number(prev.planning_usdt):0;
        const cls=delta>0?'history-up':delta<0?'history-down':'history-flat',ds=prev?((delta>=0?'+':'')+delta.toFixed(2)+' USDT'):'start';
        return '<div style="padding:7px 0;border-bottom:1px solid var(--line)"><b>'+new Date(x.ts).toLocaleString('id-ID')+'</b> · '+fmtU(x.planning_usdt)+' · <span class="'+cls+'">'+ds+'</span></div>'
      }).join('');
    }
    return rows;
  }catch(e){return []}
}

async function refreshPlan(p){
  const currentIdr=planningIdr(),currentUsdt=planningUsdt();
  lastPlanSnapshot=await fetchJson('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,current_equity:currentIdr})});
  const dd=updatePeak(),targetTodayUsdt=lastPlanSnapshot.baseline_equity/fxRate,gapUsdt=currentUsdt-targetTodayUsdt;
  $('mCurrent').textContent=fmtU(currentUsdt);$('mTarget').textContent=fmtI(p.target_equity);$('mToday').textContent=fmtU(targetTodayUsdt);
  $('mGap').textContent=(gapUsdt>=0?'+':'')+gapUsdt.toFixed(2)+' USDT';$('mDaily').textContent=pct(lastPlanSnapshot.current_daily_return);
  $('mReq').textContent=pct(lastPlanSnapshot.current_monthly_return);$('mOrigDaily').textContent=pct(lastPlanSnapshot.original_daily_return);
  $('mPressure').textContent=Number(lastPlanSnapshot.target_pressure).toFixed(2)+'×';$('mProgress').textContent=pct(lastPlanSnapshot.progress_pct);
  $('mDays').textContent=lastPlanSnapshot.days_remaining+' hari';$('mDD').textContent=pct(dd);$('mOpenRisk').textContent=pct(acct.open_risk_pct);
  $('pStart').textContent=fmtI(p.start_equity);$('pStartDate').textContent=p.start_date;$('pTargetDate').textContent=p.target_date;
  setTone('mGap',gapUsdt>=0?'pos':'neg');setTone('mDD',dd===0?'pos':dd<0.05?'warn':'neg');setTone('mOpenRisk',acct.open_risk_pct<=0.0075?'pos':acct.open_risk_pct<=0.015?'warn':'neg');
  setTone('mPressure',lastPlanSnapshot.target_pressure<=1?'pos':lastPlanSnapshot.target_pressure<=1.10?'warn':'neg');setTone('mDaily','info');setTone('mReq','info');setTone('mOrigDaily','info');setTone('mProgress','info');

  const rows=await loadHistory(),day=utc8Day();
  const prior=[...rows].reverse().find(x=>x.local_date&&x.local_date<day),last=rows.length?rows[rows.length-1]:null;
  if($('mDailyPnl')){
    if(prior){const d=currentUsdt-Number(prior.planning_usdt),pc=Number(prior.planning_usdt)>0?d/Number(prior.planning_usdt):0;$('mDailyPnl').textContent=(d>=0?'+':'')+d.toFixed(2)+' USDT · '+(pc>=0?'+':'')+(pc*100).toFixed(2)+'%';setTone('mDailyPnl',d>=0?'pos':'neg')}
    else{$('mDailyPnl').textContent='No prior-day snapshot';setTone('mDailyPnl','info')}
  }
  if($('mLastMove')){
    if(last){const d=currentUsdt-Number(last.planning_usdt);$('mLastMove').textContent=(d>=0?'+':'')+d.toFixed(2)+' USDT';setTone('mLastMove',d>0?'pos':d<0?'neg':'info')}else $('mLastMove').textContent='—';
  }
}

const obs=new MutationObserver(()=>{
  if($('vol')){const t=$('vol').textContent.toUpperCase();setTone('vol',t.includes('EXTREME')?'neg':t.includes('HIGH')?'warn':'pos')}
  if($('rEff'))setTone('rEff','info');if($('maxLoss'))setTone('maxLoss','neg');if($('notional'))setTone('notional','info');if($('margin'))setTone('margin','info');
});
obs.observe(document.body,{subtree:true,childList:true,characterData:true});
setTimeout(()=>refreshAll(),80);
</script>
'''

appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")


if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
