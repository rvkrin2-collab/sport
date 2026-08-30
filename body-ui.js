// v0.5 Body screen: private photos on VPS + simple visual comparison.
(function(){
  const viewNames={front:'спереди',side:'сбоку',back:'сзади'};
  let photos=[];
  let summary=null;

  function apiUrl(path){ return typeof apiPath==='function' ? apiPath(path) : `api/${path}`; }
  function esc(s){ return typeof escapeHtml==='function' ? escapeHtml(s) : String(s??'').replace(/[&<>"']/g,''); }
  function fmt(v,suffix=''){ return v===null||v===undefined?'—':`${Number(v).toFixed(1)}${suffix}`; }
  function delta(v,suffix=''){
    if(v===null||v===undefined) return '—';
    const n=Number(v); return `${n>0?'+':''}${n.toFixed(1)}${suffix}`;
  }

  function inject(){
    const panel=document.querySelector('#metrics');
    if(!panel || document.querySelector('#bodyPhotoManager')) return;
    const tab=document.querySelector('.tab[data-tab="metrics"]');
    if(tab) tab.textContent='Тело';

    const oldBaseline=panel.querySelector('.baseline');
    if(oldBaseline) oldBaseline.style.display='none';

    const wrap=document.createElement('div');
    wrap.id='bodyPhotoManager';
    wrap.innerHTML=`
      <div class="body-summary" id="bodySummary">
        <div class="body-kpi"><b id="bodyWeight">—</b><span>текущий вес</span></div>
        <div class="body-kpi"><b id="bodyWaist">—</b><span>текущая талия</span></div>
        <div class="body-kpi"><b id="bodyWeightDelta">—</b><span>вес от старта</span></div>
        <div class="body-kpi"><b id="bodyWaistDelta">—</b><span>талия от старта</span></div>
      </div>
      <article class="card body-photo-card">
        <div class="section-head"><div><div class="eyebrow">Фото прогресса</div><h2>Добавить фото тела</h2></div><div class="badge" id="bodyPhotoCount">0 фото</div></div>
        <div class="body-upload-grid">
          <label class="body-file"><input id="bodyPhotoFile" type="file" accept="image/*" capture="environment"><span><strong>Камера / фото</strong><br><small id="bodyFileName">выбрать изображение</small></span></label>
          <label>Дата<input id="bodyPhotoDate" type="date"></label>
          <label>Ракурс<select id="bodyPhotoView"><option value="front">Спереди</option><option value="side">Сбоку</option><option value="back">Сзади</option></select></label>
          <button id="bodyUploadButton" class="primary">Загрузить</button>
        </div>
        <p class="body-photo-help">Для сравнения: одинаковое расстояние, освещение, высота камеры и расслабленная поза. Фото сохраняются только в <b>data/body_photos</b> на VPS; при загрузке EXIF удаляется, размер уменьшается.</p>
        <div id="bodyUploadMessage" class="tiny"></div>
        <div id="bodyGallery" class="body-gallery"></div>
      </article>
      <article class="card body-photo-card">
        <div class="section-head"><div><div class="eyebrow">До / после</div><h2>Сравнить фотографии</h2></div></div>
        <div class="body-compare-controls"><select id="bodyCompareA"></select><select id="bodyCompareB"></select></div>
        <div id="bodyCompareEmpty" class="body-empty">Загрузи хотя бы две фотографии одного ракурса.</div>
        <div id="bodyCompareWrap" style="display:none">
          <div class="body-compare"><img id="bodyCompareBottom"><img id="bodyCompareTop" class="body-compare__top"><div class="body-compare__labels"><span id="bodyCompareLabelA"></span><span id="bodyCompareLabelB"></span></div></div>
          <input id="bodyCompareSlider" class="body-slider" type="range" min="0" max="100" value="50">
        </div>
      </article>`;
    panel.insertBefore(wrap,panel.firstChild);
    document.querySelector('#bodyPhotoDate').value=new Date().toISOString().slice(0,10);
    bind();
  }

  function bind(){
    const file=document.querySelector('#bodyPhotoFile');
    file?.addEventListener('change',()=>{
      document.querySelector('#bodyFileName').textContent=file.files?.[0]?.name || 'выбрать изображение';
    });
    document.querySelector('#bodyUploadButton')?.addEventListener('click',upload);
    document.querySelector('#bodyCompareA')?.addEventListener('change',renderCompare);
    document.querySelector('#bodyCompareB')?.addEventListener('change',renderCompare);
    document.querySelector('#bodyCompareSlider')?.addEventListener('input',e=>{
      const top=document.querySelector('#bodyCompareTop');
      if(top) top.style.clipPath=`inset(0 ${100-Number(e.target.value)}% 0 0)`;
    });
    document.querySelector('.tab[data-tab="metrics"]')?.addEventListener('click',()=>setTimeout(load,80));
  }

  async function upload(){
    if(typeof apiOnline!=='undefined' && !apiOnline){ showMessage('Сервер недоступен — фото нельзя сохранить локально.',true); return; }
    const input=document.querySelector('#bodyPhotoFile');
    const photo=input?.files?.[0];
    if(!photo){showMessage('Выбери фото.',true);return}
    const fd=new FormData();
    fd.append('photo',photo);
    fd.append('photo_date',document.querySelector('#bodyPhotoDate').value);
    fd.append('view',document.querySelector('#bodyPhotoView').value);
    fd.append('note','');
    const btn=document.querySelector('#bodyUploadButton');
    btn.disabled=true; btn.textContent='Загружаю…'; document.querySelector('#bodyPhotoManager').classList.add('photo-loading');
    try{
      const r=await fetch(apiUrl('body/photos'),{method:'POST',body:fd,cache:'no-store'});
      let data={}; try{data=await r.json()}catch{}
      if(!r.ok) throw new Error(data.detail || `Ошибка ${r.status}`);
      input.value='';document.querySelector('#bodyFileName').textContent='выбрать изображение';
      showMessage('Фото сохранено на VPS.');
      await load();
    }catch(e){showMessage(e.message,true)}finally{
      btn.disabled=false;btn.textContent='Загрузить';document.querySelector('#bodyPhotoManager').classList.remove('photo-loading');
    }
  }

  function showMessage(text,error=false){const m=document.querySelector('#bodyUploadMessage');if(m){m.textContent=text;m.className=`tiny ${error?'error-text':'ok-text'}`}}

  function renderSummary(){
    if(!summary)return;
    document.querySelector('#bodyWeight').textContent=fmt(summary.latest?.weight,' кг');
    document.querySelector('#bodyWaist').textContent=fmt(summary.latest?.waist,' см');
    document.querySelector('#bodyWeightDelta').textContent=delta(summary.weight_delta,' кг');
    document.querySelector('#bodyWaistDelta').textContent=delta(summary.waist_delta,' см');
    document.querySelector('#bodyPhotoCount').textContent=`${summary.photo_count||0} фото`;
  }

  function renderGallery(){
    const box=document.querySelector('#bodyGallery'); if(!box)return;
    if(!photos.length){box.innerHTML='<div class="body-empty" style="grid-column:1/-1">Пока нет фото. Для первой точки достаточно спереди и сбоку.</div>';return}
    box.innerHTML=photos.map(p=>`<div class="body-shot"><img loading="lazy" src="${esc(p.url)}?v=${encodeURIComponent(p.created_at)}" alt="Фото ${esc(viewNames[p.view])}"><div class="body-shot__meta"><div><strong>${esc(p.date)}</strong><br><small>${esc(viewNames[p.view]||p.view)}</small></div><button class="body-shot__delete" data-delete-photo="${esc(p.id)}" title="Удалить">Удалить</button></div></div>`).join('');
    box.querySelectorAll('[data-delete-photo]').forEach(btn=>btn.addEventListener('click',()=>remove(btn.dataset.deletePhoto)));
  }

  async function remove(id){
    if(!confirm('Удалить это фото с VPS?'))return;
    try{const r=await fetch(apiUrl(`body/photos/${id}`),{method:'DELETE',cache:'no-store'});if(!r.ok)throw new Error('Не удалось удалить фото');await load()}catch(e){showMessage(e.message,true)}
  }

  function fillCompare(){
    const a=document.querySelector('#bodyCompareA'),b=document.querySelector('#bodyCompareB');if(!a||!b)return;
    const opts=photos.map(p=>`<option value="${esc(p.id)}">${esc(p.date)} · ${esc(viewNames[p.view]||p.view)}</option>`).join('');
    a.innerHTML=opts;b.innerHTML=opts;
    if(photos.length>=2){a.value=photos[photos.length-1].id;b.value=photos[0].id}
    renderCompare();
  }

  function renderCompare(){
    const a=photos.find(p=>p.id===document.querySelector('#bodyCompareA')?.value);
    const b=photos.find(p=>p.id===document.querySelector('#bodyCompareB')?.value);
    const empty=document.querySelector('#bodyCompareEmpty'),wrap=document.querySelector('#bodyCompareWrap');
    if(!a||!b||a.id===b.id||a.view!==b.view){empty.style.display='block';wrap.style.display='none';empty.textContent=a&&b&&a.view!==b.view?'Выбери две фотографии одного ракурса.':'Загрузи хотя бы две фотографии одного ракурса.';return}
    empty.style.display='none';wrap.style.display='block';
    document.querySelector('#bodyCompareBottom').src=b.url+`?v=${encodeURIComponent(b.created_at)}`;
    document.querySelector('#bodyCompareTop').src=a.url+`?v=${encodeURIComponent(a.created_at)}`;
    document.querySelector('#bodyCompareLabelA').textContent=a.date;
    document.querySelector('#bodyCompareLabelB').textContent=b.date;
    const slider=document.querySelector('#bodyCompareSlider');slider.value=50;document.querySelector('#bodyCompareTop').style.clipPath='inset(0 50% 0 0)';
  }

  async function load(){
    inject();
    if(typeof apiOnline!=='undefined' && !apiOnline)return;
    try{
      const [s,p]=await Promise.all([api('body/summary'),api('body/photos')]);
      summary=s;photos=p;renderSummary();renderGallery();fillCompare();
    }catch(e){showMessage(`Не удалось загрузить раздел «Тело»: ${e.message}`,true)}
  }

  inject();
  let attempts=0;
  const timer=setInterval(()=>{attempts++;if(typeof apiOnline!=='undefined'&&apiOnline){clearInterval(timer);load()}else if(attempts>30)clearInterval(timer)},400);
})();
