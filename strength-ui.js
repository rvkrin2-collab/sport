// v0.5.3 adaptive strength coach: per-set loads, timed planks, editable history.
(function(){
  let editingNumber=null;
  let editingDate=null;

  function measureLabel(ex){ return ex.measure==='time'?'сек':'повт.'; }
  function targetLabel(ex){
    return ex.measure==='time'
      ? `${ex.sets}×${ex.rep_min}–${ex.rep_max} сек`
      : `${ex.sets}×${ex.rep_min}–${ex.rep_max}`;
  }
  function setSummary(prev,measure='reps'){
    if(!prev) return '';
    const values=prev.reps||[];
    if(measure==='time') return values.map(v=>`${v} сек`).join(' · ')+(prev.pain?` · боль ${prev.pain}/10`:'');
    const loads=(prev.loads&&prev.loads.length)?prev.loads:values.map(()=>prev.load);
    const sets=values.map((rep,i)=>loads[i]!==null&&loads[i]!==undefined?`${loads[i]}×${rep}`:`${rep}`).join(' · ');
    return `${sets}${prev.rir!==null&&prev.rir!==undefined?` · RIR ${prev.rir}`:''}${prev.pain?` · боль ${prev.pain}/10`:''}`;
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
    card.id='adaptiveStrength'; card.className='card strength-coach';
    card.innerHTML=`
      <div class="strength-coach__head">
        <div><div class="eyebrow">Следующая тренировка</div><h2 id="strengthPlanTitle">Загружаю план…</h2></div>
        <span id="strengthMode" class="integration-status">—</span>
      </div>
      <p id="strengthPhaseText" class="muted">План корректируется по прошлым силовым и текущей беговой нагрузке.</p>
      <div id="strengthFatigue" class="strength-alert" style="display:none"></div>
      <div id="strengthPrescription" class="strength-prescription"></div>
      <div class="strength-coach__footer">
        <div class="tiny">Рабочие подходы фиксируются отдельно. Для планок записывается только время — без веса и без «повторов».</div>
        <div class="strength-actions"><button id="cancelStrengthEdit" class="ghost" style="display:none">Отмена</button><button id="saveStrengthSession" class="primary" style="display:none">Завершить тренировку</button></div>
      </div>
      <div id="strengthSaveMessage" class="tiny"></div>`;
    first.insertAdjacentElement('beforebegin',card);

    const history=document.createElement('article');
    history.id='strengthHistoryCard'; history.className='card strength-history-card';
    history.innerHTML=`<div class="section-head"><div><div class="eyebrow">Журнал</div><h2>Прошлые силовые</h2></div></div><p class="muted">Можно открыть любую завершённую тренировку, исправить вес, повторы или время и сохранить заново.</p><div id="strengthHistory" class="strength-history"><div class="tiny">Загружаю историю…</div></div>`;
    card.insertAdjacentElement('afterend',history);
  }

  function renderSetRows(ex,disabled,saved){
    const actual=saved||{};
    const savedValues=actual.reps||[];
    const savedLoads=actual.loads||[];
    const setCount=Math.max(ex.sets||0,savedValues.length);
    return Array.from({length:setCount},(_,i)=>{
      const value=savedValues[i]??'';
      if(ex.measure==='time'){
        return `<div class="strength-set-row strength-set-row--time" data-set="${i}"><div class="strength-set-label">Подход ${i+1}</div><label>Время, сек<input class="s-reps" type="number" step="1" min="1" max="600" value="${value}" placeholder="${ex.rep_min}–${ex.rep_max}" ${disabled}></label></div>`;
      }
      const defaultLoad=savedLoads[i]??(ex.target_load!==null&&ex.target_load!==undefined?ex.target_load:'');
      return `<div class="strength-set-row" data-set="${i}"><div class="strength-set-label">Подход ${i+1}</div><label>Вес, кг<input class="s-load" type="number" step="0.5" min="0" value="${defaultLoad}" placeholder="—" ${disabled}></label><label>Повторы<input class="s-reps" type="number" step="1" min="1" max="100" value="${value}" placeholder="${ex.rep_min}–${ex.rep_max}" ${disabled}></label></div>`;
    }).join('');
  }

  function renderPlan(plan,saved={},isEdit=false){
    if(!plan){
      document.querySelector('#strengthPlanTitle').textContent='24/24 — цикл завершён';
      document.querySelector('#strengthPhaseText').textContent='Пора сравнить талию, фото, бег и силовые с точкой старта.';
      document.querySelector('#strengthPrescription').innerHTML='';
      document.querySelector('#saveStrengthSession').style.display='none';
      return;
    }
    window.__currentStrengthPlan=plan;
    document.querySelector('#strengthPlanTitle').textContent=isEdit?`Правка тренировки №${plan.number} · ${plan.type}`:`№${plan.number} · ${plan.type} · ${plan.phase.name}`;
    const mode=document.querySelector('#strengthMode');
    mode.textContent=isEdit?'редактирование':strengthModeLabel(plan);
    mode.className='integration-status '+(plan.fatigue_mode==='green'&&!isEdit?'is-on':'');
    document.querySelector('#strengthPhaseText').textContent=isEdit
      ? `Исправь фактические подходы и сохрани. Следующий план пересчитается с учётом исправлений.`
      : `${plan.phase.message} Цель по усилию: RIR ${plan.phase.rir}. Время: около ${plan.duration_min} минут.`;
    const alert=document.querySelector('#strengthFatigue');
    if(!isEdit && plan.fatigue_mode!=='green'){
      alert.style.display='block'; alert.className=`strength-alert strength-alert--${plan.fatigue_mode}`;
      alert.textContent=plan.fatigue_mode==='red'?`Сегодня лучше перенести силовую.`:`План облегчён автоматически.`;
    } else alert.style.display='none';

    document.querySelector('#strengthPrescription').innerHTML=plan.exercises.map((ex,i)=>{
      const old=saved[ex.key]||null;
      const prev=setSummary(ex.previous,ex.measure);
      const disabled=(!isEdit&&ex.sets===0)?'disabled':'';
      return `<div class="strength-exercise ${(!isEdit&&ex.sets===0)?'is-skipped':''}" data-exercise="${ex.key}" data-measure="${ex.measure||'reps'}">
        <div class="strength-exercise__number">${i+1}</div><div class="strength-exercise__body">
          <div class="strength-exercise__title"><strong>${escapeHtml(ex.name)}</strong><span>${ex.sets?targetLabel(ex):'пропустить'}</span></div>
          <div class="strength-target">${escapeHtml(ex.target_text||'')}</div>
          ${prev&&!isEdit?`<div class="strength-previous">Прошлый раз: ${escapeHtml(prev)}</div>`:''}
          <div class="strength-note">${escapeHtml(ex.notes||'')}</div>
          ${(ex.sets||old)?`<div class="strength-set-list">${renderSetRows(ex,disabled,old)}</div>
            <div class="strength-inputs strength-inputs--feedback">
              ${ex.measure==='time'?'':`<label>RIR после последнего подхода<input class="s-rir" type="number" step="0.5" min="0" max="5" value="${old?.rir??''}" placeholder="2" ${disabled}></label>`}
              <label>Боль 0–10<input class="s-pain" type="number" step="1" min="0" max="10" value="${old?.pain??0}" ${disabled}></label>
            </div>`:''}
        </div></div>`;
    }).join('');
    const save=document.querySelector('#saveStrengthSession');
    save.style.display=(!isEdit&&plan.fatigue_mode==='red')?'none':'inline-block';
    save.textContent=isEdit?'Сохранить изменения':'Завершить тренировку';
    document.querySelector('#cancelStrengthEdit').style.display=isEdit?'inline-block':'none';
  }

  async function loadStrengthPlan(){
    injectStrengthCoach();
    if(typeof apiOnline==='undefined'||!apiOnline) return;
    try{
      const data=await api('strength/current'); editingNumber=null; editingDate=null; renderPlan(data.next,{},false);
    }catch(e){ const t=document.querySelector('#strengthPlanTitle'); if(t)t.textContent='Не удалось загрузить силовой план'; const m=document.querySelector('#strengthSaveMessage'); if(m)m.textContent=e.message; }
  }

  function historyExerciseText(ex){
    if(ex.measure==='time') return `${escapeHtml(ex.name)}: ${(ex.reps||[]).map(x=>`${x} сек`).join(' · ')}`;
    const loads=ex.loads||[];
    const sets=(ex.reps||[]).map((r,i)=>loads[i]!==null&&loads[i]!==undefined?`${loads[i]}×${r}`:`${r}`).join(' · ');
    return `${escapeHtml(ex.name)}: ${sets}`;
  }
  async function loadStrengthHistory(){
    if(typeof apiOnline==='undefined'||!apiOnline) return;
    try{
      const rows=await api('strength/history');
      const box=document.querySelector('#strengthHistory'); if(!box)return;
      if(!rows.length){box.innerHTML='<div class="tiny">Завершённых силовых пока нет.</div>';return;}
      box.innerHTML=rows.map(s=>`<div class="strength-history-item"><div><strong>№${s.number} · ${escapeHtml(s.workout_type)} · ${escapeHtml(s.date)}</strong><div class="tiny strength-history-summary">${(s.exercises||[]).map(historyExerciseText).join('<br>')}</div></div><button class="ghost strength-edit-btn" data-edit-strength="${s.number}">Править</button></div>`).join('');
      box.querySelectorAll('[data-edit-strength]').forEach(btn=>btn.addEventListener('click',()=>editStrength(Number(btn.dataset.editStrength))));
    }catch(e){ const box=document.querySelector('#strengthHistory'); if(box)box.textContent='Не удалось загрузить историю: '+e.message; }
  }
  async function editStrength(number){
    try{
      const data=await api(`strength/record/${number}`); editingNumber=number; editingDate=data.log.date; renderPlan(data.plan,data.saved||{},true); document.querySelector('#adaptiveStrength').scrollIntoView({behavior:'smooth',block:'start'});
    }catch(e){ const m=document.querySelector('#strengthSaveMessage'); if(m){m.textContent=e.message;m.className='tiny error-text';} }
  }

  async function saveStrength(){
    const plan=window.__currentStrengthPlan; if(!plan)return;
    const exercises=[];
    document.querySelectorAll('#strengthPrescription .strength-exercise').forEach(row=>{
      const ex=plan.exercises.find(x=>x.key===row.dataset.exercise); if(!ex)return;
      if(!editingNumber&&ex.sets===0)return;
      const reps=[],loads=[];
      row.querySelectorAll('.strength-set-row').forEach(setRow=>{
        const raw=setRow.querySelector('.s-reps')?.value; if(raw==='')return;
        const value=Number(raw); if(!Number.isFinite(value)||value<=0)return;
        reps.push(Math.round(value));
        if((ex.measure||'reps')==='time') loads.push(null);
        else { const l=setRow.querySelector('.s-load')?.value; loads.push(l===''?null:Number(l)); }
      });
      if(!reps.length)return;
      const rr=row.querySelector('.s-rir')?.value, pp=row.querySelector('.s-pain')?.value;
      const lastLoad=[...loads].reverse().find(x=>x!==null&&Number.isFinite(x));
      exercises.push({exercise_key:ex.key,load:lastLoad===undefined?null:lastLoad,loads,reps,rir:rr===''||rr===undefined?null:Number(rr),pain:pp===''||pp===undefined?0:Number(pp),note:null});
    });
    if(exercises.length<3){const m=document.querySelector('#strengthSaveMessage');m.textContent='Заполни рабочие подходы хотя бы в трёх упражнениях.';m.className='tiny error-text';return;}
    const btn=document.querySelector('#saveStrengthSession'); btn.disabled=true; btn.textContent='Сохраняю…';
    try{
      const number=editingNumber||plan.number;
      const res=await api('strength/session',{method:'POST',body:JSON.stringify({number,date:editingDate||new Date().toISOString().slice(0,10),exercises})});
      const m=document.querySelector('#strengthSaveMessage'); m.textContent=editingNumber?`Тренировка №${number} исправлена. Следующий план пересчитан.`:(res.completed?'Сохранено. 24/24 — цикл завершён.':`Сохранено. План тренировки №${res.next.number} уже пересчитан.`); m.className='tiny ok-text';
      editingNumber=null; editingDate=null;
      if(typeof refreshServerState==='function') await refreshServerState(); await loadStrengthPlan(); await loadStrengthHistory();
    }catch(e){const m=document.querySelector('#strengthSaveMessage');m.textContent=e.message;m.className='tiny error-text';}
    finally{btn.disabled=false; btn.textContent=editingNumber?'Сохранить изменения':'Завершить тренировку';}
  }

  injectStrengthCoach();
  document.querySelector('#saveStrengthSession')?.addEventListener('click',saveStrength);
  document.querySelector('#cancelStrengthEdit')?.addEventListener('click',async()=>{editingNumber=null;editingDate=null;await loadStrengthPlan();});
  document.querySelector('.tab[data-tab="strength"]')?.addEventListener('click',()=>setTimeout(()=>{loadStrengthPlan();loadStrengthHistory();},80));
  let tries=0; const wait=setInterval(()=>{tries++;if(typeof apiOnline!=='undefined'&&apiOnline){clearInterval(wait);loadStrengthPlan();loadStrengthHistory();}if(tries>30)clearInterval(wait);},400);
})();
