const START = new Date('2026-08-30T00:00:00');
const END = new Date('2026-11-22T23:59:59');
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

const local = {
  get(key, fallback){ try{return JSON.parse(localStorage.getItem(key)) ?? fallback}catch{return fallback}},
  set(key, val){ localStorage.setItem(key, JSON.stringify(val)); }
};

let state = {
  week: local.get('week', {}),
  strengthDone: local.get('strengthDone', []),
  exerciseLog: local.get('exerciseLog', []),
  metrics: local.get('metrics', []),
  workouts: []
};
let apiOnline = false;

function apiPath(path){ return `api/${path}`; }
async function api(path, options={}){
  const r = await fetch(apiPath(path), {
    headers:{'Content-Type':'application/json', ...(options.headers||{})},
    cache:'no-store',
    ...options
  });
  if(!r.ok){
    let detail='';
    try{ detail=(await r.json()).detail || ''; }catch{}
    throw new Error(detail || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

function persistLocal(){
  local.set('week', state.week);
  local.set('strengthDone', state.strengthDone);
  local.set('exerciseLog', state.exerciseLog);
  local.set('metrics', state.metrics);
}

function projectInfo(){
  const now = new Date();
  const total = END - START;
  const elapsed = Math.min(Math.max(now - START,0),total);
  const pct = Math.round(elapsed/total*100);
  const days = Math.max(0, Math.ceil((END-now)/(1000*60*60*24)));
  const week = Math.min(12, Math.max(1, Math.floor((now-START)/(7*86400000))+1));
  $('#projectPct').textContent = pct+'%';
  $('#projectBar').style.width = pct+'%';
  $('#daysLeft').textContent = days ? `${days} дн. до финиша` : 'Финиш';
  $('#weekNumber').textContent = week;
}

function injectStylesV03(){
  if($('#v03styles')) return;
  const style=document.createElement('style'); style.id='v03styles';
  style.textContent=`
    .auto-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
    .integration-head,.run-week,.coach-head{display:flex;justify-content:space-between;gap:16px;align-items:center}
    .integration-status{font-size:12px;font-weight:800;padding:7px 10px;border-radius:999px;background:#2a3038;color:#aeb7c4}
    .integration-status.is-on{background:rgba(231,255,114,.13);color:#e7ff72;border:1px solid rgba(231,255,114,.35)}
    .token-box{display:grid;grid-template-columns:1fr auto;gap:10px;margin-top:16px}
    .tiny{font-size:12px;color:#808a98;line-height:1.45}.error-text{color:#ff9d9d}.ok-text{color:#e7ff72}
    .run-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}
    .run-kpi{background:#11151a;border:1px solid #2b323d;border-radius:15px;padding:15px}
    .run-kpi b{display:block;font-size:26px;letter-spacing:-.04em}.run-kpi span{color:#9ca6b5;font-size:12px}
    .run-list{display:grid;gap:8px}.run-row{display:grid;grid-template-columns:92px 1fr auto;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #2b323d}
    .run-row:last-child{border-bottom:none}.run-row__meta{color:#9ca6b5;font-size:13px}.pace{white-space:nowrap;color:#e7ff72;font-weight:800}
    .coach-notes{display:grid;gap:9px;margin-top:16px}.coach-note{padding:12px 14px;border-radius:14px;background:#11151a;border:1px solid #2b323d;line-height:1.45}
    .source-note{display:flex;gap:8px;align-items:center;color:#9ca6b5;font-size:12px;margin-top:14px}
    .source-dot{width:7px;height:7px;border-radius:50%;background:#e7ff72}
    .dashboard-run{margin-bottom:18px}.dashboard-run .run-kpis{margin-bottom:0}
    @media(max-width:820px){.auto-grid{grid-template-columns:1fr}.run-kpis{grid-template-columns:repeat(2,1fr)}.token-box{grid-template-columns:1fr}.run-row{grid-template-columns:78px 1fr}.run-row .pace{grid-column:2}}
  `;
  document.head.appendChild(style);
}

function injectV03(){
  injectStylesV03();
  const firstGrid = $('#dashboard .grid--3');
  if(firstGrid && !$('#readinessCard')){
    const card = document.createElement('article');
    card.id='readinessCard';
    card.className='card readiness readiness--unknown';
    card.innerHTML=`
      <div class="readiness__top"><span class="eyebrow">Сегодня</span><span id="storageMode" class="storage-badge">локально</span></div>
      <h2 id="readinessTitle">Проверяю восстановление…</h2>
      <p id="readinessMessage" class="muted">Добавь сегодняшние показатели, чтобы система начала давать рекомендации.</p>
      <div id="readinessReasons" class="reason-list"></div>`;
    firstGrid.insertAdjacentElement('afterend', card);
  }

  if(firstGrid && !$('#dashboardRun')){
    const run=document.createElement('article'); run.id='dashboardRun'; run.className='card dashboard-run';
    run.innerHTML=`<div class="integration-head"><div><div class="eyebrow">Бег</div><h2>Эта неделя</h2></div><span id="runSource" class="integration-status">нет данных</span></div><div id="dashboardRunKpis" class="run-kpis"></div>`;
    $('#readinessCard')?.insertAdjacentElement('afterend',run);
  }

  const metricForm = $('.form-grid--metrics');
  if(metricForm && !$('#metricPain')){
    const pain = document.createElement('input');
    pain.id='metricPain'; pain.type='number'; pain.min='0'; pain.max='10'; pain.step='1'; pain.placeholder='Боль, 0–10';
    const save=$('#addMetric'); metricForm.insertBefore(pain, save);
  }

  const metricHeading = $('#metrics .card h2');
  if(metricHeading && !$('#syncHint')){
    const p=document.createElement('p'); p.id='syncHint'; p.className='sync-hint'; p.textContent='Данные сохраняются на VPS и синхронизируются между телефоном и компьютером.';
    metricHeading.insertAdjacentElement('afterend',p);
  }

  if(!$('.tab[data-tab="auto"]')){
    const btn=document.createElement('button'); btn.className='tab'; btn.dataset.tab='auto'; btn.textContent='Авто';
    $('.tabs').appendChild(btn);
    const section=document.createElement('section'); section.id='auto'; section.className='panel';
    section.innerHTML=`
      <div class="auto-grid">
        <article class="card">
          <div class="integration-head"><div><div class="eyebrow">Garmin → Tredict → Sport</div><h2>Автоматические данные</h2></div><span id="tredictStatus" class="integration-status">проверяю</span></div>
          <p class="muted">Тренировки, сон, HRV и пульс покоя можно забирать напрямую из Tredict. Токен остаётся только на твоём VPS и не попадает в GitHub.</p>
          <div id="tokenBox" class="token-box"><input id="tredictToken" type="password" autocomplete="off" placeholder="Personal API token Tredict"><button id="saveTredictToken" class="primary">Подключить</button></div>
          <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap"><button id="syncTredict" class="ghost">Синхронизировать сейчас</button><button id="disconnectTredict" class="ghost" style="display:none">Отключить</button></div>
          <p id="tredictMessage" class="tiny">Токен создаётся в Tredict → Settings → Personal API / MCP.</p>
        </article>
        <article class="card">
          <div class="coach-head"><div><div class="eyebrow">Штаб</div><h2>Краткий разбор</h2></div><span class="integration-status is-on">авто</span></div>
          <div id="coachNotes" class="coach-notes"><div class="coach-note">Загружаю данные…</div></div>
        </article>
      </div>
      <article class="card">
        <div class="integration-head"><div><div class="eyebrow">Динамика</div><h2>Последние пробежки</h2></div><span id="runCompare" class="integration-status">—</span></div>
        <div id="runKpis" class="run-kpis"></div>
        <div id="runList" class="run-list"></div>
        <div class="source-note"><span class="source-dot"></span><span>Источник тренировок: Tredict, синхронизированный с Garmin.</span></div>
      </article>`;
    $('main').appendChild(section);
  }

  bindTabs();
  bindAutoActions();
}

function bindTabs(){
  $$('.tab').forEach(btn=>{
    btn.onclick=()=>{
      $$('.tab').forEach(x=>x.classList.remove('is-active'));
      $$('.panel').forEach(x=>x.classList.remove('is-active'));
      btn.classList.add('is-active');
      $('#'+btn.dataset.tab)?.classList.add('is-active');
      if(btn.dataset.tab==='auto' && apiOnline) loadAutoPanel();
    };
  });
}

function bindAutoActions(){
  const save=$('#saveTredictToken'), sync=$('#syncTredict'), disconnect=$('#disconnectTredict');
  if(save) save.onclick=async()=>{
    const token=$('#tredictToken').value.trim();
    if(!token){ setTredictMessage('Вставь токен Tredict.',true); return; }
    save.disabled=true; save.textContent='Подключаю…';
    try{
      const r=await api('integrations/tredict/token',{method:'POST',body:JSON.stringify({token})});
      $('#tredictToken').value=''; setTredictMessage(`Подключено. Загружено тренировок: ${r.sync.activities}.`); await loadAutoPanel(); await refreshServerState();
    }catch(e){setTredictMessage(e.message,true)}
    finally{save.disabled=false; save.textContent='Подключить'}
  };
  if(sync) sync.onclick=async()=>{
    sync.disabled=true; sync.textContent='Синхронизация…';
    try{ const r=await api('integrations/tredict/sync',{method:'POST'}); setTredictMessage(`Готово: ${r.activities} тренировок, ${r.bodyvalues} записей тела.`); await loadAutoPanel(); await refreshServerState(); }
    catch(e){setTredictMessage(e.message,true)}
    finally{sync.disabled=false; sync.textContent='Синхронизировать сейчас'}
  };
  if(disconnect) disconnect.onclick=async()=>{
    if(!confirm('Отключить Tredict? Уже загруженные данные останутся.')) return;
    await api('integrations/tredict/token',{method:'DELETE'}); await loadAutoPanel();
  };
}

function setTredictMessage(text,isError=false){
  const el=$('#tredictMessage'); if(!el)return; el.textContent=text; el.className='tiny '+(isError?'error-text':'ok-text');
}

function formatPace(sec){
  if(sec===null || sec===undefined || !Number.isFinite(Number(sec))) return '—';
  const s=Math.round(Number(sec)), m=Math.floor(s/60); return `${m}:${String(s%60).padStart(2,'0')}/км`;
}
function formatDuration(min){
  if(min===null || min===undefined) return '—';
  const n=Math.round(Number(min)); return n>=60?`${Math.floor(n/60)}ч ${n%60}м`:`${n} мин`;
}
function kpiHtml(run){
  return `<div class="run-kpi"><b>${run.runs}</b><span>пробежки</span></div><div class="run-kpi"><b>${Number(run.km||0).toFixed(1)}</b><span>км</span></div><div class="run-kpi"><b>${formatDuration(run.minutes)}</b><span>время</span></div><div class="run-kpi"><b>${run.avg_hr||'—'}</b><span>ср. пульс</span></div>`;
}

async function loadAutoPanel(){
  if(!apiOnline)return;
  try{
    const [status,run,coach]=await Promise.all([api('integrations/tredict'),api('summary/running'),api('coach')]);
    const st=$('#tredictStatus');
    if(st){ st.textContent=status.configured?'подключено':'не подключено'; st.className='integration-status '+(status.configured?'is-on':''); }
    if($('#disconnectTredict')) $('#disconnectTredict').style.display=status.configured?'inline-block':'none';
    if($('#tokenBox')) $('#tokenBox').style.display=status.configured?'none':'grid';
    if(status.configured){
      const when=status.last_sync?new Date(status.last_sync).toLocaleString('ru-RU'):'ещё не было';
      setTredictMessage(`Последняя синхронизация: ${when}. В базе Tredict: ${status.last_count} активностей.`);
    }else setTredictMessage('Токен создаётся в Tredict → Settings → Personal API / MCP. Нужны права activityRead и bodyvaluesRead.');

    $('#runKpis').innerHTML=kpiHtml(run.current);
    $('#dashboardRunKpis').innerHTML=kpiHtml(run.current);
    const hasTredict=(run.recent||[]).some(x=>x.source==='tredict');
    $('#runSource').textContent=hasTredict?'Tredict':'ручные данные'; $('#runSource').className='integration-status '+(hasTredict?'is-on':'');
    let comp='нет базы';
    if(run.previous.km>0){ const d=(run.current.km-run.previous.km)/run.previous.km*100; comp=`к прошлой неделе ${d>=0?'+':''}${d.toFixed(0)}% км`; }
    $('#runCompare').textContent=comp;
    $('#runList').innerHTML=(run.recent||[]).length?(run.recent||[]).map(x=>`<div class="run-row"><div><strong>${escapeHtml(prettyDate(x.date))}</strong></div><div><strong>${escapeHtml(x.title||'Бег')}</strong><div class="run-row__meta">${x.distance_km?Number(x.distance_km).toFixed(1)+' км · ':''}${formatDuration(x.duration_min)}${x.avg_hr?' · пульс '+x.avg_hr:''}</div></div><div class="pace">${formatPace(x.pace_sec_km)}</div></div>`).join(''):'<p class="muted">Пока нет автоматически загруженных пробежек.</p>';
    $('#coachNotes').innerHTML=(coach.notes||[]).map(n=>`<div class="coach-note">${escapeHtml(n)}</div>`).join('');
  }catch(e){ console.warn(e); setTredictMessage(e.message,true); }
}

function renderWeek(){
  const data = state.week || {};
  $$('[data-week]').forEach(ch=>{
    ch.checked = !!data[ch.dataset.week];
    ch.onchange = async ()=>{
      data[ch.dataset.week] = ch.checked; state.week=data; persistLocal(); renderWeek();
      if(apiOnline){ try{ await api('week',{method:'POST',body:JSON.stringify({data})}); }catch(e){ console.warn(e); } }
    };
  });
  let score = 0;
  ['run1','run2','run3','run4','food','measure'].forEach(k=>score += data[k]?1:0);
  ['strength1','strength2'].forEach(k=>score += data[k]?2:0);
  $('#weekScore').textContent = score;
  $('#weekVerdict').textContent = score>=8?'Отличная неделя':score>=6?'Нормальная неделя':score>0?'В процессе':'Начинаем';
}
$('#resetWeek').onclick=async()=>{
  state.week={}; persistLocal(); renderWeek();
  if(apiOnline){ try{await api('week',{method:'POST',body:JSON.stringify({data:{}})});}catch(e){console.warn(e)} }
};

function renderStrength(){
  const done = state.strengthDone || [];
  const grid = $('#strengthGrid'); grid.innerHTML='';
  for(let i=1;i<=24;i++){
    const b=document.createElement('button');
    b.className='level '+(done.includes(i)?'is-done':''); b.textContent=i;
    b.title=done.includes(i)?'Отметить как невыполненную':'Отметить выполненной';
    b.onclick=async()=>{
      let arr=state.strengthDone || [];
      arr=arr.includes(i)?arr.filter(x=>x!==i):[...arr,i].sort((a,b)=>a-b);
      state.strengthDone=arr; persistLocal(); renderStrength();
      if(apiOnline){ try{ await api('strength/toggle',{method:'POST',body:JSON.stringify({number:i})}); }catch(e){ console.warn(e); } }
    };
    grid.appendChild(b);
  }
  const count=done.length;
  $('#strengthBadge').textContent=`${count} / 24`; $('#strengthDone').textContent=`${count}/24 силовых`; $('#nextStrength').textContent=count<24?`№${Math.min(24,count+1)}`:'Готово';
}

function renderExercises(){
  const log=state.exerciseLog || []; const box=$('#exerciseLog'); box.innerHTML='';
  log.slice().reverse().forEach(x=>{ const d=document.createElement('div'); d.className='log-item'; d.innerHTML=`<div><strong>${escapeHtml(x.name)}</strong><br><small>${escapeHtml(prettyDate(x.date))}</small></div><div>${escapeHtml(x.result)}</div>`; box.appendChild(d); });
}
$('#addExercise').onclick=async()=>{
  const name=$('#exerciseName').value.trim(), result=$('#exerciseResult').value.trim(); if(!name||!result)return;
  const row={name,result,date:new Date().toISOString().slice(0,10)}; state.exerciseLog.push(row); persistLocal(); renderExercises(); $('#exerciseName').value=''; $('#exerciseResult').value='';
  if(apiOnline){ try{await api('exercises',{method:'POST',body:JSON.stringify(row)});}catch(e){console.warn(e)} }
};

function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
function prettyDate(s){ if(!s)return''; if(/^\d{4}-\d{2}-\d{2}$/.test(s))return new Date(`${s}T12:00:00`).toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit'}); return s; }

function renderMetrics(){
  const rows=(state.metrics || []).slice().sort((a,b)=>a.date.localeCompare(b.date)); const table=$('#metricTable');
  table.innerHTML=rows.length?'<div class="metric-row metric-row--7"><strong>Дата</strong><strong>Вес</strong><strong>Талия</strong><strong>Сон</strong><strong>Пульс</strong><strong>Энергия</strong><strong>Боль</strong></div>':'<p class="muted">Пока нет замеров.</p>';
  rows.slice().reverse().forEach(x=>{ const r=document.createElement('div'); r.className='metric-row metric-row--7'; r.innerHTML=`<span>${prettyDate(x.date)}</span><span>${x.weight||'—'}</span><span>${x.waist||'—'}</span><span>${x.sleep||'—'}</span><span>${x.pulse||'—'}</span><span>${x.energy||'—'}</span><span>${x.pain??'—'}</span>`; table.appendChild(r); });
  drawChart(rows);
}
$('#metricDate').value = new Date().toISOString().slice(0,10);
$('#addMetric').onclick=async()=>{
  const val=id=>$(id)?.value || '';
  const row={date:val('#metricDate'),weight:numOrNull(val('#metricWeight')),waist:numOrNull(val('#metricWaist')),sleep:numOrNull(val('#metricSleep')),pulse:intOrNull(val('#metricPulse')),energy:intOrNull(val('#metricEnergy')),pain:intOrNull(val('#metricPain'))};
  if(!row.date)return;
  const rows=state.metrics || []; const existing=rows.findIndex(x=>x.date===row.date); if(existing>=0)rows[existing]=row;else rows.push(row); state.metrics=rows; persistLocal(); renderMetrics();
  if(apiOnline){ try{ await api('metrics',{method:'POST',body:JSON.stringify(row)}); await loadReadiness(); await loadAutoPanel(); }catch(e){ console.warn(e); } }
};
function numOrNull(v){return v===''?null:Number(v)} function intOrNull(v){return v===''?null:parseInt(v,10)}

function drawChart(rows){
  const c=$('#metricChart'),dpr=window.devicePixelRatio||1,rect=c.getBoundingClientRect(); c.width=Math.max(600,rect.width*dpr); c.height=280*dpr;
  const ctx=c.getContext('2d');ctx.scale(dpr,dpr);const W=c.width/dpr,H=c.height/dpr;ctx.clearRect(0,0,W,H);ctx.strokeStyle='#2b323d';ctx.lineWidth=1;
  for(let i=1;i<5;i++){const y=H*i/5;ctx.beginPath();ctx.moveTo(40,y);ctx.lineTo(W-20,y);ctx.stroke()}
  const series=rows.filter(r=>r.waist).map(r=>({date:r.date,val:+r.waist}));
  if(series.length<2){ctx.fillStyle='#9ca6b5';ctx.font='14px system-ui';ctx.fillText('Добавь минимум два замера талии — здесь появится график.',40,H/2);return}
  const vals=series.map(x=>x.val),min=Math.min(...vals)-1,max=Math.max(...vals)+1,x=i=>40+(W-60)*(i/(series.length-1)),y=v=>20+(H-50)*(1-(v-min)/(max-min||1));
  ctx.strokeStyle='#e7ff72';ctx.lineWidth=3;ctx.beginPath();series.forEach((p,i)=>i?ctx.lineTo(x(i),y(p.val)):ctx.moveTo(x(i),y(p.val)));ctx.stroke();ctx.fillStyle='#e7ff72';series.forEach((p,i)=>{ctx.beginPath();ctx.arc(x(i),y(p.val),4,0,Math.PI*2);ctx.fill()});
}

async function loadReadiness(){
  const card=$('#readinessCard'); if(!card)return;
  if(!apiOnline){card.className='card readiness readiness--unknown';$('#readinessTitle').textContent='Локальный режим';$('#readinessMessage').textContent='Сервер недоступен.';$('#readinessReasons').innerHTML='';return}
  try{ const data=await api('today'),r=data.readiness; card.className=`card readiness readiness--${r.level}`; $('#readinessTitle').textContent=r.title; $('#readinessMessage').textContent=r.message; $('#readinessReasons').innerHTML=(r.reasons||[]).map(x=>`<span>${escapeHtml(x)}</span>`).join(''); }
  catch(e){console.warn(e)}
}

async function refreshServerState(){
  state=await api('state'); persistLocal(); renderAll(false);
}

async function connectBackend(){
  try{
    const health=await api('health'); apiOnline=true; $('#storageMode').textContent=`сервер v${health.version}`; $('#storageMode').classList.add('storage-badge--online');
    const serverState=await api('state');
    const serverEmpty=(serverState.metrics||[]).length===0&&(serverState.exerciseLog||[]).length===0&&(serverState.strengthDone||[]).length===0;
    const localHasData=(state.metrics||[]).length||(state.exerciseLog||[]).length||(state.strengthDone||[]).length||Object.keys(state.week||{}).length;
    if(serverEmpty&&localHasData){try{await api('migrate',{method:'POST',body:JSON.stringify({week:state.week,strengthDone:state.strengthDone,exerciseLog:state.exerciseLog,metrics:state.metrics})});}catch(e){console.warn('migration',e)}}
    state=await api('state'); persistLocal(); renderAll(false); await loadAutoPanel();
  }catch(e){apiOnline=false;if($('#storageMode'))$('#storageMode').textContent='локально';loadReadiness()}
}

$('#exportData').onclick=()=>{ if(apiOnline){window.open(apiPath('export'),'_blank');return} const blob=new Blob([JSON.stringify(state,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='stronger-drier-data.json';a.click();URL.revokeObjectURL(a.href); };
$('#clearAll').onclick=()=>{if(apiOnline){alert('Серверные данные не удаляются одной кнопкой — это защита от случайного удаления.');return}if(confirm('Удалить все локальные данные проекта?')){localStorage.clear();location.reload()}};

function renderAll(loadAuto=true){ projectInfo(); renderWeek(); renderStrength(); renderExercises(); renderMetrics(); loadReadiness(); if(loadAuto&&apiOnline)loadAutoPanel(); }
window.addEventListener('resize',()=>renderMetrics());
injectV03(); renderAll(); connectBackend();


// v0.4 adaptive strength coach UI. Appended to app.js by backend/app.py.
(function(){
  function repsText(prev){
    if(!prev) return '';
    const load=prev.load!==null&&prev.load!==undefined?`${prev.load} кг · `:'';
    return `${load}${(prev.reps||[]).join('/')}${prev.rir!==null&&prev.rir!==undefined?` · RIR ${prev.rir}`:''}${prev.pain?` · боль ${prev.pain}/10`:''}`;
  }

  function strengthModeLabel(plan){
    const labels={green:'обычная нагрузка',yellow:'с запасом',post_hard_run:'после тяжёлого бега',red:'восстановление'};
    return labels[plan.fatigue_mode]||plan.fatigue_mode;
  }

  function injectStrengthCoach(){
    const panel=document.querySelector('#strength');
    if(!panel || document.querySelector('#adaptiveStrength')) return;
    const first=panel.querySelector('.card');
    const card=document.createElement('article');
    card.id='adaptiveStrength';
    card.className='card strength-coach';
    card.innerHTML=`
      <div class="strength-coach__head">
        <div><div class="eyebrow">Следующая тренировка</div><h2 id="strengthPlanTitle">Загружаю план…</h2></div>
        <span id="strengthMode" class="integration-status">—</span>
      </div>
      <p id="strengthPhaseText" class="muted">План корректируется по твоим прошлым силовым и текущей беговой нагрузке.</p>
      <div id="strengthFatigue" class="strength-alert" style="display:none"></div>
      <div id="strengthPrescription" class="strength-prescription"></div>
      <div class="strength-coach__footer">
        <div class="tiny">Заполняй фактический вес, повторы и запас повторов. Следующая тренировка пересчитается автоматически.</div>
        <button id="saveStrengthSession" class="primary" style="display:none">Завершить тренировку</button>
      </div>
      <div id="strengthSaveMessage" class="tiny"></div>`;
    first.insertAdjacentElement('beforebegin',card);
  }

  function renderStrengthPlan(data){
    const plan=data.next;
    if(!plan){
      document.querySelector('#strengthPlanTitle').textContent='24/24 — цикл завершён';
      document.querySelector('#strengthPhaseText').textContent='Пора сравнить талию, фото, бег и силовые с точкой старта.';
      document.querySelector('#strengthPrescription').innerHTML='';
      document.querySelector('#saveStrengthSession').style.display='none';
      return;
    }
    window.__currentStrengthPlan=plan;
    document.querySelector('#strengthPlanTitle').textContent=`№${plan.number} · ${plan.type} · ${plan.phase.name}`;
    const mode=document.querySelector('#strengthMode');
    mode.textContent=strengthModeLabel(plan);
    mode.className='integration-status '+(plan.fatigue_mode==='green'?'is-on':'');
    document.querySelector('#strengthPhaseText').textContent=`${plan.phase.message} Цель по усилию: RIR ${plan.phase.rir}. Время: около ${plan.duration_min} минут.`;
    const alert=document.querySelector('#strengthFatigue');
    if(plan.fatigue_mode!=='green'){
      alert.style.display='block';
      alert.className=`strength-alert strength-alert--${plan.fatigue_mode}`;
      alert.textContent=plan.fatigue_mode==='red'
        ? `Сегодня лучше перенести силовую${plan.fatigue_reason?`: ${plan.fatigue_reason}`:''}.`
        : `План облегчен автоматически${plan.fatigue_reason?`: ${plan.fatigue_reason}`:''}.`;
    }else alert.style.display='none';

    const box=document.querySelector('#strengthPrescription');
    box.innerHTML=plan.exercises.map((ex,i)=>{
      const prev=repsText(ex.previous);
      const disabled=ex.sets===0?'disabled':'';
      const loadValue=ex.target_load!==null&&ex.target_load!==undefined?ex.target_load:(ex.previous?.load??'');
      return `<div class="strength-exercise ${ex.sets===0?'is-skipped':''}" data-exercise="${ex.key}">
        <div class="strength-exercise__number">${i+1}</div>
        <div class="strength-exercise__body">
          <div class="strength-exercise__title"><strong>${escapeHtml(ex.name)}</strong><span>${ex.sets?`${ex.sets}×${ex.rep_min}–${ex.rep_max}`:'пропустить'}</span></div>
          <div class="strength-target">${escapeHtml(ex.target_text)}</div>
          ${prev?`<div class="strength-previous">Прошлый раз: ${escapeHtml(prev)}</div>`:''}
          <div class="strength-note">${escapeHtml(ex.notes)}</div>
          ${ex.sets?`<div class="strength-inputs">
            <label>Вес<input class="s-load" type="number" step="0.5" min="0" value="${loadValue}" placeholder="кг" ${disabled}></label>
            <label>Повторы<input class="s-reps" type="text" inputmode="numeric" placeholder="10/10/9" ${disabled}></label>
            <label>RIR<input class="s-rir" type="number" step="0.5" min="0" max="5" placeholder="2" ${disabled}></label>
            <label>Боль<input class="s-pain" type="number" step="1" min="0" max="10" value="0" ${disabled}></label>
          </div>`:''}
        </div>
      </div>`;
    }).join('');
    document.querySelector('#saveStrengthSession').style.display=plan.fatigue_mode==='red'?'none':'inline-block';
  }

  async function loadStrengthPlan(){
    if(typeof api!=='function') return;
    injectStrengthCoach();
    const t=document.querySelector('#strengthPlanTitle');
    if(t && t.textContent==='Загружаю план…') t.textContent='Загружаю план…';
    try{
      const data=await api('strength/current');
      renderStrengthPlan(data);
    }catch(e){
      const t=document.querySelector('#strengthPlanTitle'); if(t)t.textContent='Не удалось загрузить силовой план';
      const m=document.querySelector('#strengthSaveMessage'); if(m){m.textContent=e.message;m.className='tiny error-text'}
    }
  }

  function parseReps(value){
    return String(value||'').split(/[\/ ,;]+/).map(x=>parseInt(x,10)).filter(x=>Number.isFinite(x)&&x>0);
  }

  async function saveStrength(){
    const plan=window.__currentStrengthPlan;
    if(!plan) return;
    const btn=document.querySelector('#saveStrengthSession');
    const exercises=[];
    document.querySelectorAll('#strengthPrescription .strength-exercise').forEach(row=>{
      const ex=plan.exercises.find(x=>x.key===row.dataset.exercise);
      if(!ex || ex.sets===0) return;
      const reps=parseReps(row.querySelector('.s-reps')?.value);
      if(!reps.length) return;
      const rawLoad=row.querySelector('.s-load')?.value;
      const rawRir=row.querySelector('.s-rir')?.value;
      const rawPain=row.querySelector('.s-pain')?.value;
      exercises.push({
        exercise_key:ex.key,
        load:rawLoad===''?null:Number(rawLoad),
        reps,
        rir:rawRir===''?null:Number(rawRir),
        pain:rawPain===''?0:Number(rawPain),
        note:null
      });
    });
    if(exercises.length<3){
      const m=document.querySelector('#strengthSaveMessage');m.textContent='Заполни повторы хотя бы в трёх упражнениях.';m.className='tiny error-text';return;
    }
    btn.disabled=true;btn.textContent='Сохраняю…';
    try{
      const res=await api('strength/session',{method:'POST',body:JSON.stringify({number:plan.number,date:new Date().toISOString().slice(0,10),exercises})});
      const m=document.querySelector('#strengthSaveMessage');
      m.textContent=res.completed?'Сохранено. 24/24 — цикл завершён.':`Сохранено. План тренировки №${res.next.number} уже пересчитан.`;
      m.className='tiny ok-text';
      if(typeof refreshServerState==='function') await refreshServerState();
      await loadStrengthPlan();
    }catch(e){
      const m=document.querySelector('#strengthSaveMessage');m.textContent=e.message;m.className='tiny error-text';
    }finally{btn.disabled=false;btn.textContent='Завершить тренировку'}
  }

  injectStrengthCoach();
  document.querySelector('#saveStrengthSession')?.addEventListener('click',saveStrength);
  document.querySelector('.tab[data-tab="strength"]')?.addEventListener('click',()=>setTimeout(loadStrengthPlan,80));
  // Load immediately; retry a few times because backend may be restarting after deploy.
  let tries=0;
  const loadWithRetry=async()=>{
    tries++;
    await loadStrengthPlan();
    if(tries<6 && document.querySelector('#strengthPlanTitle')?.textContent==='Не удалось загрузить силовой план')
      setTimeout(loadWithRetry,1500);
  };
  setTimeout(loadWithRetry,250);
})();

