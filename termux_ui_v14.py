from __future__ import annotations

import termux_ui_v13 as base

appmod = base.appmod

# UI-only refinement: improve spacing, hierarchy, mobile readability and group
# Mission Control metrics without changing any calculations or data sources.
extra_style = r'''
<style>
:root{
  --bg:#0a0f16;
  --card:#111923;
  --card2:#0e151e;
  --line:#223044;
  --muted:#8793a5;
  --text:#f5f8fc;
  --accent:#6aaeff;
  --ok:#4fd19a;
  --bad:#ff7d86;
}
html{-webkit-text-size-adjust:100%}
body{background:linear-gradient(180deg,#091019 0,#0a0f16 260px);color:var(--text)}
.wrap{max-width:860px;padding:18px 14px 52px}
.head{align-items:flex-start;margin-bottom:12px}
.title{font-size:24px;line-height:1.08;letter-spacing:-.35px}
.sub{margin-top:5px;line-height:1.4}
.btn{min-height:44px;border-radius:13px;padding:11px 14px}
.status{margin:12px 0 14px;padding:11px 13px;border-radius:13px;background:rgba(17,25,35,.88)}
.card{border-radius:17px;background:linear-gradient(180deg,var(--card),var(--card2));box-shadow:0 5px 18px rgba(0,0,0,.12)}
.grid{gap:12px;grid-template-columns:repeat(2,minmax(0,1fr))}
.metric{min-width:0;padding:14px}
.metric small{font-size:11px;line-height:1.3;margin-bottom:7px;letter-spacing:.02em}
.metric b{display:block;min-width:0;font-size:18px;line-height:1.16;letter-spacing:-.2px;overflow-wrap:anywhere;word-break:normal}
.subvalue{font-size:10px!important;line-height:1.35;margin-top:5px!important}
.section{margin-top:16px}
.tabs{position:sticky;top:0;z-index:5;margin:16px -4px;padding:7px 4px;background:rgba(10,15,22,.92);backdrop-filter:blur(10px);border-radius:15px}
.tab{min-height:42px;padding:9px 8px;font-size:13px}
.tab.active{background:#263c57}
.field{margin-bottom:13px}
input,textarea,select{border-radius:13px;background:#0b121a;border-color:#26354a}
textarea{min-height:150px}
.notice{line-height:1.55}

/* Mission Control: separate the information into readable groups. */
#mission{display:block}
.mission-block{margin-top:16px}
.mission-block:first-child{margin-top:0}
.mission-label{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 2px 8px;color:#b8c3d1;font-size:11px;font-weight:750;letter-spacing:.08em;text-transform:uppercase}
.mission-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.mission-grid .card{margin:0}
.metric-hero{grid-column:span 2;padding:17px 16px}
.metric-hero small{font-size:11px}
.metric-hero b{font-size:25px;letter-spacing:-.55px}
.metric-key b{font-size:20px}
.metric-soft{background:linear-gradient(180deg,#101823,#0c141d)}
.metric-risk{background:linear-gradient(180deg,#15191f,#10151c)}

/* Top account overview is intentionally compact so Mission remains the focus. */
body>.wrap>.grid .metric{padding:12px 13px}
body>.wrap>.grid .metric b{font-size:16px}

#analyticsCard{padding:14px}
.analytics-stats{gap:8px!important}
.analytics-stat{padding:9px!important}
canvas.analytics-chart{height:128px!important}

@media(max-width:560px){
  .wrap{padding:14px 11px 44px}
  .head{gap:9px}
  .title{font-size:21px}
  .head>.btn{padding:9px 11px;min-height:40px}
  .grid{gap:8px}
  .card{border-radius:15px}
  .metric{padding:12px 11px}
  .metric small{font-size:10px;margin-bottom:6px}
  .metric b{font-size:16px}
  .mission-grid{gap:8px}
  .metric-hero{padding:15px 13px}
  .metric-hero b{font-size:22px}
  .metric-key b{font-size:17px}
  .tabs{margin:13px -2px;padding:5px 2px}
  .tab{font-size:12px;padding:8px 5px}
  .section{margin-top:13px}
  .analytics-stats{grid-template-columns:repeat(2,minmax(0,1fr))!important}
}

@media(max-width:360px){
  .mission-grid{grid-template-columns:1fr}
  .metric-hero{grid-column:auto}
  body>.wrap>.grid{grid-template-columns:1fr 1fr}
  .metric b{font-size:15px}
}
</style>
'''
appmod.HTML = appmod.HTML.replace("</head>", extra_style + "</head>")

extra_script = r'''
<script>
function ctcCardByMetric(id){
  const el=document.getElementById(id);
  return el?el.closest('.card.metric'):null;
}

function ctcBuildMetricGroup(title, ids, classMap){
  const block=document.createElement('section');
  block.className='mission-block';
  const label=document.createElement('div');
  label.className='mission-label';
  label.textContent=title;
  const grid=document.createElement('div');
  grid.className='mission-grid';
  ids.forEach(id=>{
    const card=ctcCardByMetric(id);
    if(!card)return;
    card.classList.remove('metric-hero','metric-key','metric-soft','metric-risk');
    const cls=(classMap&&classMap[id])||'';
    if(cls)cls.split(' ').forEach(x=>x&&card.classList.add(x));
    grid.appendChild(card);
  });
  block.appendChild(label);
  block.appendChild(grid);
  return block;
}

function ctcPolishMission(){
  const mission=document.getElementById('mission');
  if(!mission||mission.dataset.polished==='1')return;
  const source=mission.querySelector(':scope > .grid');
  if(!source)return;

  const overview=ctcBuildMetricGroup('Today',
    ['mCurrent','mToday','mAdjusted','mGap'],
    {mCurrent:'metric-hero',mToday:'metric-key',mAdjusted:'metric-key',mGap:'metric-hero'}
  );
  const pace=ctcBuildMetricGroup('Pace',
    ['mDaily','mReq','mPressure','mProgress','mDays','mTarget','mOrigDaily'],
    {mDaily:'metric-key',mReq:'metric-key',mTarget:'metric-soft'}
  );
  const risk=ctcBuildMetricGroup('Risk',
    ['mDD','mOpenRisk'],
    {mDD:'metric-risk metric-key',mOpenRisk:'metric-risk metric-key'}
  );

  mission.insertBefore(overview,source);
  mission.insertBefore(pace,source);
  mission.insertBefore(risk,source);
  source.remove();
  mission.dataset.polished='1';
}

document.addEventListener('DOMContentLoaded',ctcPolishMission);
if(document.readyState!=='loading')ctcPolishMission();
</script>
'''
appmod.HTML = appmod.HTML.replace("</body></html>", extra_script + "</body></html>")

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
