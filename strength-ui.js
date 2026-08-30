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
    if(typeof apiOnline==='undefined' || !apiOnline) return;
    injectStrengthCoach();
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
  let tries=0;
  const wait=setInterval(()=>{
    tries++;
    if(typeof apiOnline!=='undefined' && apiOnline){clearInterval(wait);loadStrengthPlan();}
    if(tries>20) clearInterval(wait);
  },500);
})();
