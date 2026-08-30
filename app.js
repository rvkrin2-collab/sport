const START = new Date('2026-08-30T00:00:00');
const END = new Date('2026-11-22T23:59:59');
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

const store = {
  get(key, fallback){ try{return JSON.parse(localStorage.getItem(key)) ?? fallback}catch{return fallback}},
  set(key, val){localStorage.setItem(key, JSON.stringify(val))}
};

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

$$('.tab').forEach(btn=>btn.addEventListener('click',()=>{
  $$('.tab').forEach(x=>x.classList.remove('is-active'));
  $$('.panel').forEach(x=>x.classList.remove('is-active'));
  btn.classList.add('is-active');
  $('#'+btn.dataset.tab).classList.add('is-active');
}));

function renderWeek(){
  const data = store.get('week', {});
  $$('[data-week]').forEach(ch=>{
    ch.checked = !!data[ch.dataset.week];
    ch.onchange = ()=>{
      data[ch.dataset.week] = ch.checked;
      store.set('week', data);
      renderWeek();
    };
  });
  let score = 0;
  ['run1','run2','run3','run4','food','measure'].forEach(k=>score += data[k]?1:0);
  ['strength1','strength2'].forEach(k=>score += data[k]?2:0);
  $('#weekScore').textContent = score;
  $('#weekVerdict').textContent = score>=8?'Отличная неделя':score>=6?'Нормальная неделя':score>0?'В процессе':'Начинаем';
}
$('#resetWeek').onclick=()=>{store.set('week',{});renderWeek()};

function renderStrength(){
  const done = store.get('strengthDone', []);
  const grid = $('#strengthGrid'); grid.innerHTML='';
  for(let i=1;i<=24;i++){
    const b=document.createElement('button');
    b.className='level '+(done.includes(i)?'is-done':'');
    b.textContent=i;
    b.title=done.includes(i)?'Отметить как невыполненную':'Отметить выполненной';
    b.onclick=()=>{
      let arr=store.get('strengthDone',[]);
      arr=arr.includes(i)?arr.filter(x=>x!==i):[...arr,i].sort((a,b)=>a-b);
      store.set('strengthDone',arr); renderStrength();
    };
    grid.appendChild(b);
  }
  const count=done.length;
  $('#strengthBadge').textContent=`${count} / 24`;
  $('#strengthDone').textContent=`${count}/24 силовых`;
  $('#nextStrength').textContent = count<24 ? `№${Math.min(24, count+1)}` : 'Готово';
}

function renderExercises(){
  const log=store.get('exerciseLog',[]);
  const box=$('#exerciseLog'); box.innerHTML='';
  log.slice().reverse().forEach((x)=>{
    const d=document.createElement('div'); d.className='log-item';
    d.innerHTML=`<div><strong>${escapeHtml(x.name)}</strong><br><small>${escapeHtml(x.date)}</small></div><div>${escapeHtml(x.result)}</div>`;
    box.appendChild(d);
  });
}
$('#addExercise').onclick=()=>{
  const name=$('#exerciseName').value.trim(), result=$('#exerciseResult').value.trim();
  if(!name||!result)return;
  const log=store.get('exerciseLog',[]);
  log.push({name,result,date:new Date().toLocaleDateString('ru-RU')});
  store.set('exerciseLog',log); $('#exerciseName').value=''; $('#exerciseResult').value=''; renderExercises();
};

function escapeHtml(s){return s.replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}

function renderMetrics(){
  const rows=store.get('metrics',[]).sort((a,b)=>a.date.localeCompare(b.date));
  const table=$('#metricTable');
  table.innerHTML = rows.length ? '<div class="metric-row"><strong>Дата</strong><strong>Вес</strong><strong>Талия</strong><strong>Сон</strong><strong>Пульс</strong><strong>Энергия</strong></div>' : '<p class="muted">Пока нет замеров.</p>';
  rows.slice().reverse().forEach(x=>{
    const r=document.createElement('div'); r.className='metric-row';
    r.innerHTML=`<span>${x.date}</span><span>${x.weight||'—'}</span><span>${x.waist||'—'}</span><span>${x.sleep||'—'}</span><span>${x.pulse||'—'}</span><span>${x.energy||'—'}</span>`;
    table.appendChild(r);
  });
  drawChart(rows);
}
$('#metricDate').value = new Date().toISOString().slice(0,10);
$('#addMetric').onclick=()=>{
  const row={
    date:$('#metricDate').value,
    weight:$('#metricWeight').value,
    waist:$('#metricWaist').value,
    sleep:$('#metricSleep').value,
    pulse:$('#metricPulse').value,
    energy:$('#metricEnergy').value
  };
  if(!row.date)return;
  const rows=store.get('metrics',[]);
  const existing=rows.findIndex(x=>x.date===row.date);
  if(existing>=0) rows[existing]=row; else rows.push(row);
  store.set('metrics',rows);
  renderMetrics();
};

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

$('#exportData').onclick=()=>{
  const data={
    week:store.get('week',{}),
    strengthDone:store.get('strengthDone',[]),
    exerciseLog:store.get('exerciseLog',[]),
    metrics:store.get('metrics',[])
  };
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='stronger-drier-data.json';a.click();URL.revokeObjectURL(a.href);
};
$('#clearAll').onclick=()=>{
  if(confirm('Удалить все локальные данные проекта?')){localStorage.clear();location.reload()}
};

window.addEventListener('resize',()=>renderMetrics());
projectInfo(); renderWeek(); renderStrength(); renderExercises(); renderMetrics();
