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
  if(!r.ok) throw new Error(`${r.status} ${r.statusText}`);
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

function injectV02(){
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

  const metricForm = $('.form-grid--metrics');
  if(metricForm && !$('#metricPain')){
    const pain = document.createElement('input');
    pain.id='metricPain'; pain.type='number'; pain.min='0'; pain.max='10'; pain.step='1'; pain.placeholder='Боль, 0–10';
    const save=$('#addMetric'); metricForm.insertBefore(pain, save);
  }

  const metricHeading = $('#metrics .card h2');
  if(metricHeading && !$('#syncHint')){
    const p=document.createElement('p'); p.id='syncHint'; p.className='sync-hint'; p.textContent='После запуска v0.2 данные синхронизируются через сервер и будут одинаковыми на телефоне и компьютере.';
    metricHeading.insertAdjacentElement('afterend',p);
  }
}

$$('.tab').forEach(btn=>btn.addEventListener('click',()=>{
  $$('.tab').forEach(x=>x.classList.remove('is-active'));
  $$('.panel').forEach(x=>x.classList.remove('is-active'));
  btn.classList.add('is-active');
  $('#'+btn.dataset.tab).classList.add('is-active');
}));

function renderWeek(){
  const data = state.week || {};
  $$('[data-week]').forEach(ch=>{
    ch.checked = !!data[ch.dataset.week];
    ch.onchange = async ()=>{
      data[ch.dataset.week] = ch.checked;
      state.week=data; persistLocal(); renderWeek();
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
    b.className='level '+(done.includes(i)?'is-done':'');
    b.textContent=i;
    b.title=done.includes(i)?'Отметить как невыполненную':'Отметить выполненной';
    b.onclick=async()=>{
      let arr=state.strengthDone || [];
      arr=arr.includes(i)?arr.filter(x=>x!==i):[...arr,i].sort((a,b)=>a-b);
      state.strengthDone=arr; persistLocal(); renderStrength();
      if(apiOnline){
        try{ await api('strength/toggle',{method:'POST',body:JSON.stringify({number:i})}); }
        catch(e){ console.warn(e); }
      }
    };
    grid.appendChild(b);
  }
  const count=done.length;
  $('#strengthBadge').textContent=`${count} / 24`;
  $('#strengthDone').textContent=`${count}/24 силовых`;
  $('#nextStrength').textContent = count<24 ? `№${Math.min(24, count+1)}` : 'Готово';
}

function renderExercises(){
  const log=state.exerciseLog || [];
  const box=$('#exerciseLog'); box.innerHTML='';
  log.slice().reverse().forEach(x=>{
    const d=document.createElement('div'); d.className='log-item';
    d.innerHTML=`<div><strong>${escapeHtml(x.name)}</strong><br><small>${escapeHtml(prettyDate(x.date))}</small></div><div>${escapeHtml(x.result)}</div>`;
    box.appendChild(d);
  });
}
$('#addExercise').onclick=async()=>{
  const name=$('#exerciseName').value.trim(), result=$('#exerciseResult').value.trim();
  if(!name||!result)return;
  const row={name,result,date:new Date().toISOString().slice(0,10)};
  state.exerciseLog.push(row); persistLocal(); renderExercises();
  $('#exerciseName').value=''; $('#exerciseResult').value='';
  if(apiOnline){ try{await api('exercises',{method:'POST',body:JSON.stringify(row)});}catch(e){console.warn(e)} }
};

function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
function prettyDate(s){
  if(!s) return '';
  if(/^\d{4}-\d{2}-\d{2}$/.test(s)) return new Date(`${s}T12:00:00`).toLocaleDateString('ru-RU');
  return s;
}

function renderMetrics(){
  const rows=(state.metrics || []).slice().sort((a,b)=>a.date.localeCompare(b.date));
  const table=$('#metricTable');
  table.innerHTML = rows.length ? '<div class="metric-row metric-row--7"><strong>Дата</strong><strong>Вес</strong><strong>Талия</strong><strong>Сон</strong><strong>Пульс</strong><strong>Энергия</strong><strong>Боль</strong></div>' : '<p class="muted">Пока нет замеров.</p>';
  rows.slice().reverse().forEach(x=>{
    const r=document.createElement('div'); r.className='metric-row metric-row--7';
    r.innerHTML=`<span>${prettyDate(x.date)}</span><span>${x.weight||'—'}</span><span>${x.waist||'—'}</span><span>${x.sleep||'—'}</span><span>${x.pulse||'—'}</span><span>${x.energy||'—'}</span><span>${x.pain??'—'}</span>`;
    table.appendChild(r);
  });
  drawChart(rows);
}
$('#metricDate').value = new Date().toISOString().slice(0,10);
$('#addMetric').onclick=async()=>{
  const val=id=>$(id)?.value || '';
  const row={
    date:val('#metricDate'), weight:numOrNull(val('#metricWeight')), waist:numOrNull(val('#metricWaist')),
    sleep:numOrNull(val('#metricSleep')), pulse:intOrNull(val('#metricPulse')), energy:intOrNull(val('#metricEnergy')),
    pain:intOrNull(val('#metricPain'))
  };
  if(!row.date)return;
  const rows=state.metrics || [];
  const existing=rows.findIndex(x=>x.date===row.date);
  if(existing>=0) rows[existing]=row; else rows.push(row);
  state.metrics=rows; persistLocal(); renderMetrics();
  if(apiOnline){
    try{ await api('metrics',{method:'POST',body:JSON.stringify(row)}); await loadReadiness(); }
    catch(e){ console.warn(e); }
  }
};
function numOrNull(v){return v===''?null:Number(v)}
function intOrNull(v){return v===''?null:parseInt(v,10)}

function drawChart(rows){
  const c=$('#metricChart'), dpr=window.devicePixelRatio||1;
  const rect=c.getBoundingClientRect();
  c.width=Math.max(600, rect.width*dpr); c.height=280*dpr;
  const ctx=c.getContext('2d'); ctx.scale(dpr,dpr);
  const W=c.width/dpr,H=c.height/dpr;
  ctx.clearRect(0,0,W,H);
  ctx.strokeStyle='#2b323d';ctx.lineWidth=1;
  for(let i=1;i<5;i++){const y=H*i/5;ctx.beginPath();ctx.moveTo(40,y);ctx.lineTo(W-20,y);ctx.stroke()}
  const series = rows.filter(r=>r.waist).map(r=>({date:r.date,val:+r.waist}));
  if(series.length<2){
    ctx.fillStyle='#9ca6b5';ctx.font='14px system-ui';ctx.fillText('Добавь минимум два замера талии — здесь появится график.',40,H/2);
    return;
  }
  const vals=series.map(x=>x.val), min=Math.min(...vals)-1, max=Math.max(...vals)+1;
  const x=(i)=>40+(W-60)*(i/(series.length-1));
  const y=(v)=>20+(H-50)*(1-(v-min)/(max-min||1));
  ctx.strokeStyle='#e7ff72';ctx.lineWidth=3;ctx.beginPath();
  series.forEach((p,i)=>i?ctx.lineTo(x(i),y(p.val)):ctx.moveTo(x(i),y(p.val)));ctx.stroke();
  ctx.fillStyle='#e7ff72';
  series.forEach((p,i)=>{ctx.beginPath();ctx.arc(x(i),y(p.val),4,0,Math.PI*2);ctx.fill()});
  ctx.fillStyle='#9ca6b5';ctx.font='12px system-ui';
  series.forEach((p,i)=>{ctx.fillText(p.val+' см',x(i)-16,y(p.val)-10)});
}

async function loadReadiness(){
  const card=$('#readinessCard');
  if(!card)return;
  if(!apiOnline){
    card.className='card readiness readiness--unknown';
    $('#readinessTitle').textContent='Локальный режим';
    $('#readinessMessage').textContent='После запуска серверной версии появятся синхронизация и рекомендации по восстановлению.';
    $('#readinessReasons').innerHTML='';
    return;
  }
  try{
    const data=await api('today'); const r=data.readiness;
    card.className=`card readiness readiness--${r.level}`;
    $('#readinessTitle').textContent=r.title;
    $('#readinessMessage').textContent=r.message;
    $('#readinessReasons').innerHTML=(r.reasons||[]).map(x=>`<span>${escapeHtml(x)}</span>`).join('');
  }catch(e){console.warn(e)}
}

async function connectBackend(){
  try{
    await api('health'); apiOnline=true;
    $('#storageMode').textContent='сервер'; $('#storageMode').classList.add('storage-badge--online');

    const serverState=await api('state');
    const serverEmpty=(serverState.metrics||[]).length===0 && (serverState.exerciseLog||[]).length===0 && (serverState.strengthDone||[]).length===0;
    const localHasData=(state.metrics||[]).length || (state.exerciseLog||[]).length || (state.strengthDone||[]).length || Object.keys(state.week||{}).length;
    if(serverEmpty && localHasData){
      try{
        await api('migrate',{method:'POST',body:JSON.stringify({
          week:state.week,strengthDone:state.strengthDone,exerciseLog:state.exerciseLog,metrics:state.metrics
        })});
      }catch(e){console.warn('migration',e)}
    }
    state=await api('state'); persistLocal(); renderAll();
  }catch(e){
    apiOnline=false;
    if($('#storageMode')) $('#storageMode').textContent='локально';
    loadReadiness();
  }
}

$('#exportData').onclick=()=>{
  if(apiOnline){ window.open(apiPath('export'),'_blank'); return; }
  const blob=new Blob([JSON.stringify(state,null,2)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='stronger-drier-data.json';a.click();URL.revokeObjectURL(a.href);
};
$('#clearAll').onclick=()=>{
  if(apiOnline){ alert('Серверные данные не удаляются одной кнопкой — это защита от случайного удаления.'); return; }
  if(confirm('Удалить все локальные данные проекта?')){localStorage.clear();location.reload()}
};

function renderAll(){ projectInfo(); renderWeek(); renderStrength(); renderExercises(); renderMetrics(); loadReadiness(); }
window.addEventListener('resize',()=>renderMetrics());
injectV02(); renderAll(); connectBackend();
