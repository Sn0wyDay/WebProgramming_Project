/* Home and lyric-writing module. UI reference: commit 87e9b7c.
   Team integration contract: REHome.configure({api,getUser}); renderHome(); renderSong(id).
   All mutations remain server-owned; this module uses no localStorage. */
window.REHome=(()=>{
 let api,getUser,current,comments=[],commentPage=0,commentPages=0,homePage=1,viewAll=false;
 let modalPage=1,modalQuery='',modalScope='catalog',candidates=[],pendingSongId=null,renderVersion=0,searchVersion=0,lyricsBusy=false,lyricsRetryAt=0,lyricsRetryTimer;
 const root=()=>document.getElementById('main'),dialog=()=>document.getElementById('modal');
 const action=(label,name,id='',className='button outline')=>`<button class="${className}" ${name==='close'?'aria-label="닫기"':''} data-home-action="${name}" data-id="${esc(id)}">${label}</button>`;
 const empty=(title,text,extra='')=>`<div class="empty">${icon('headphones')}<h3>${esc(title)}</h3><p>${esc(text)}</p>${extra}</div>`;
 const stars=(rating=0)=>Array.from({length:5},(_,i)=>`<span class="${i<rating?'filled':''}">${icon('star')}</span>`).join('');
 const cover=s=>typeof s.image==='string'&&(/^https?:\/\//.test(s.image)||/^\/api\/media\/artwork\/[0-9a-f]{64}\.img$/.test(s.image))?s.image:'assets/album-placeholder.svg';
 const resourcePolls=new Map();
 function progressMessage(job){return job.retry_after>1?`연결이 지연되어 ${job.retry_after}초 뒤에 자동으로 다시 확인해요.`:job.state==='queued'?'자료를 확인할 차례를 기다리는 중…':'자료를 불러오는 중…';}
 async function resource(sid,kind,data={},progress=()=>{}){
  let job=await api(kind==='catalog'?'/catalog/search-jobs':'/songs/'+sid+'/resources/'+kind,'POST',data);
  if(job.status==='pending'){
   let pending=resourcePolls.get(job.job_id);
   if(!pending){
    const listeners=new Set(),deadline=Date.now()+120000;
    pending={listeners,promise:(async()=>{
     while(job.status==='pending'){
      listeners.forEach(fn=>fn(job));
      if(Date.now()>deadline){const error=Error('자료 조회가 지연되고 있어요. 잠시 후 다시 열어 주세요.');error.retry_after=15;throw error;}
      await new Promise(resolve=>setTimeout(resolve,document.hidden?3000:Math.min(1800,job.poll_after_ms||900)));
      job=await api('/resource-jobs/'+job.job_id);
     }
     return job;
    })()};
    resourcePolls.set(job.job_id,pending);
    pending.promise.finally(()=>resourcePolls.delete(job.job_id)).catch(()=>{});
   }
   pending.listeners.add(progress);progress(job);
   try{job=await pending.promise;}finally{pending.listeners.delete(progress);}
  }
  if(job.status==='failed'){
   const result=job.result||{},error=Error(result.error||'자료를 불러오지 못했습니다.');
   error.code=result.code;error.retry_after=result.retry_after||15;throw error;
  }
  if(job.status!=='completed'||!job.result)throw Error('자료 조회 결과를 확인하지 못했습니다.');
  return job.result;
 }
 const artworkRequests=new Map();let artworkQueue=Promise.resolve();const imageTimers=new WeakMap();
 function coverImage(s,lazy=false){return `<img src="${esc(cover(s))}" alt="${s.image?esc(s.album||s.title)+' 앨범 표지':'앨범 이미지 없음'}" data-home-cover="${s.album_id||''}" data-cover-song="${Number.isInteger(s.id)?s.id:''}" data-real-cover="${!!s.image}" ${lazy?'loading="lazy"':''}>`;}
 function fallbackCover(img){clearTimeout(imageTimers.get(img));img.classList.remove('artwork-real');img.dataset.realCover='false';img.alt='앨범 이미지 없음';if(!img.getAttribute('src').endsWith('album-placeholder.svg'))img.src='assets/album-placeholder.svg';}
 function watchCover(img){
  if(img.dataset.realCover!=='true')return;
  if(img.complete){if(img.naturalWidth)img.classList.add('artwork-real');else fallbackCover(img);return;}
  clearTimeout(imageTimers.get(img));imageTimers.set(img,setTimeout(()=>{if(img.isConnected&&!img.complete)fallbackCover(img);},12000));
 }
 document.addEventListener('load',e=>{if(e.target.matches?.('img[data-home-cover]')){clearTimeout(imageTimers.get(e.target));e.target.classList.toggle('artwork-real',e.target.dataset.realCover==='true');}},true);
 document.addEventListener('error',e=>{if(e.target.matches?.('img[data-home-cover]'))fallbackCover(e.target);},true);
 function loadArtwork(container){
  const albums=new Map();
  container.querySelectorAll('img[data-home-cover]').forEach(img=>{watchCover(img);if(img.dataset.homeCover&&img.dataset.coverSong&&!img.getAttribute('src').startsWith('/api/media/artwork/'))albums.set(img.dataset.homeCover,img.dataset.coverSong);});
  for(const [albumId,songId] of albums){
   let entry=artworkRequests.get(albumId);
   if(!entry||entry.until<Date.now()){
    entry={until:Infinity};artworkRequests.set(albumId,entry);
    const run=artworkQueue.then(()=>container.isConnected?resource(songId,'artwork'):{status:'skipped',retry_after:0}).catch(()=>({status:'unavailable',retry_after:60}));
    entry.promise=run.then(data=>{entry.until=Date.now()+(data.local_cached?86400:data.retry_after||60)*1000;return data;});artworkQueue=entry.promise;
   }
   entry.promise.then(data=>{
    if(!data.image)return;
    document.querySelectorAll('img[data-home-cover="'+albumId+'"]').forEach(img=>{if(img.getAttribute('src')!==data.image){img.dataset.realCover='true';img.alt='앨범 표지';img.src=data.image;watchCover(img);}});
    if(current?.album_id===Number(albumId)){current.image=data.image;current.artwork_source=data.source_url;}
   });
  }
 }
 const reviewRequests=new Map();
 function reviewCards(items){return items.map(r=>{
  const selection=r.article_type==='selection',label=selection?'연말 선정 기사':r.kind==='song'?'곡 평론':r.kind==='album_track'?'이 곡이 수록된 앨범 평론':'앨범 평론';
  return `<article class="critic-item"><div class="critic-person"><div><strong>${esc(r.author)}</strong><small>${label}</small></div></div><h3>${esc(r.title)}</h3><${selection?'p':'blockquote'} class="review-excerpt">${esc(r.introduction||'')}</${selection?'p':'blockquote'}><span class="review-excerpt-label">${selection?'선정 정보':'짧은 발췌'}</span><a href="${/^https:\/\//.test(r.url)?esc(r.url):'#'}" target="_blank" rel="noopener">${selection?'선정 기사 읽기':'평론 원문 읽기'}</a></article>`;
 }).join('');}

 async function loadReviews(){
  const target=document.getElementById('home-reviews'),notice=document.getElementById('home-review-notice');if(!target||!notice||!current)return;
  if(current.reviews.length){target.innerHTML=reviewCards(current.reviews);return;}
  const sid=current.id;let entry=reviewRequests.get(sid);
  if(!entry||entry.until<Date.now()){
   entry={until:Infinity};reviewRequests.set(sid,entry);
   entry.promise=resource(sid,'reviews',{},job=>{if(target.isConnected&&current?.id===sid)target.textContent=progressMessage(job);}).catch(()=>({status:'unavailable',reviews:[],retry_after:60})).then(data=>{entry.until=Date.now()+(data.status==='available'?86400:data.retry_after||60)*1000;return data;});
  }
  target.innerHTML='<p class="loading" role="status">평론·선정글을 찾는 중…</p>';notice.innerHTML='';
  const result=await entry.promise;if(!target.isConnected||current?.id!==sid)return;
  if(result.status==='available'){
   current.reviews=result.reviews;target.innerHTML=reviewCards(result.reviews);notice.innerHTML=providerNotice(result)+(result.partial?'<p class="small-muted">일부 검색은 완료하지 못했지만, 확인된 자료를 표시합니다.</p>':'');return;
  }
  const failed=result.status==='unavailable',wait=Math.max(1,Math.ceil((entry.until-Date.now())/1000));
  target.innerHTML=empty(failed?'자료를 불러오지 못했어요':'등록된 평론·선정글 없음',failed?'일시적으로 연결이 원활하지 않아요. 잠시 후 다시 시도해 주세요.':'이 곡과 연결된 평론이나 선정 기사를 아직 찾지 못했어요.');
  notice.innerHTML=`<p class="small-muted">약 ${wait}초 뒤에 다시 찾을 수 있어요.</p>${action('평론 다시 찾기','reviews')}`;
  const button=notice.querySelector('button');button.disabled=true;
  setTimeout(()=>{if(button.isConnected){button.disabled=false;notice.querySelector('p')?.remove();}},wait*1000);
 }
 const date=value=>new Date(value).toLocaleString('ko-KR');
 function toast(text){const target=document.getElementById('toast');target.textContent=text;target.classList.add('visible');setTimeout(()=>target.classList.remove('visible'),3500);}
 function modal(title,body,buttons=''){
  document.getElementById('modal-content').innerHTML=`<div class="modal-heading"><h2 id="modal-title">${esc(title)}</h2>${action(icon('close'),'close','','close-button')}</div><div class="modal-body">${body}</div>${buttons?`<div class="modal-buttons">${buttons}</div>`:''}`;
  if(!dialog().open)dialog().showModal();
 }
 function providerNotice(data){
  const info=data?._provider_status;
  if(info?.mode==='stale')return `<p class="home-notice" role="status">${icon('info')} 제공처 연결이 원활하지 않아 이전에 받은 결과를 표시합니다. 최신 정보가 아닐 수 있습니다.</p>`;
  return info?.mode==='cache'?'<p class="small-muted">저장된 검색 결과를 사용했습니다.</p>':'';
 }
 function errorHtml(error,retry=''){
  return `<div class="home-notice" role="alert"><p>${esc(error.message)}</p>${error.retry_after?`<p>약 ${error.retry_after}초 뒤에 다시 시도해 주세요.</p>`:''}${retry}</div>`;
 }
 function bookmark(s,full=false){return `<button class="${full?'button outline':'bookmark'} ${s.saved?'saved':''}" data-home-action="bookmark" data-id="${s.id}" aria-label="${s.saved?'저장 취소':'곡 저장'}" aria-pressed="${!!s.saved}">${icon('bookmark')}${full?`<span>${s.saved?'저장한 곡':'곡 저장'}</span>`:''}</button>`;}
 function lyricBadge(s){
  const labels={available:'가사 저장됨',instrumental:'반주 버전 · 가사 없음',unqueried:'가사 조회 전',missing:'일치 가사 미확인',unmatched:'가사 후보 확인 필요',error:'가사 조회 일시 실패'};
  const key=s.instrumental?'instrumental':s.lyrics_status;
  return key?`<small class="home-lyrics-state">${esc(labels[key]||'가사 조회 전')}</small>`:'';
 }
 function lyricEmpty(){
  const status=current.lyrics_status;
  if(status==='instrumental')return empty('반주 버전이에요',current.lyrics_message||'가사가 없는 연주 버전입니다. 보컬 버전을 선택해 주세요.');
  if(status==='error')return empty('가사 조회를 완료하지 못했어요','일시적인 제공처 오류입니다. 가사가 없다는 뜻은 아닙니다. 잠시 후 다시 조회해 주세요.');
  if(status==='missing')return empty('일치하는 가사를 찾지 못했어요','가사 미등록 또는 한글·영문 제목 차이일 수 있습니다. 가사가 없는 곡이라고 확정한 것은 아닙니다.');
  if(status==='unmatched')return empty('가사 후보 확인이 필요해요','가사 불러오기를 누르고 같은 곡인지 확인해 주세요.');
  return empty('아직 가사를 조회하지 않았어요','가사 불러오기를 누르면 제공처에서 찾아봅니다.');
 }
 function syncLyricButtons(){
  const wait=Math.max(0,Math.ceil((lyricsRetryAt-Date.now())/1000));
  root().querySelectorAll('[data-home-action="lyrics"]').forEach(b=>{
   b.disabled=lyricsBusy||wait>0||current?.lyrics_status==='instrumental';
   b.textContent=lyricsBusy?'가사 조회 중…':wait?wait+'초 후 다시 조회':current?.lyrics_status==='instrumental'?'반주 버전 · 가사 없음':current?.passages.length?'가사 새로 확인':'가사 불러오기';
  });
  if(wait>0){clearTimeout(lyricsRetryTimer);lyricsRetryTimer=setTimeout(syncLyricButtons,1000);}
 }
 function card(s){return `<article class="song-card" data-song-card="${s.id}"><div class="cover-wrap"><a class="cover-link" href="#song/${s.id}" aria-label="${esc(s.title)} 가사와 기록 보기">${coverImage(s,true)}<span class="cover-album"><small>${esc(s.artist.toUpperCase())}</small>${esc(s.album||s.title)}</span></a>${bookmark(s)}</div><div class="song-info"><div><a class="song-title" href="#song/${s.id}">${esc(s.title)}</a><p class="song-artist">${esc(s.artist)}</p>${lyricBadge(s)}</div>${icon('chevron')}</div><div class="star-row" aria-label="내 별점 ${s.rating||0}점">${stars(s.rating)}<small>${s.comment_count||0}개의 코멘트</small></div></article>`;}
 function pages(page,total,prefix){return total>1?`<div class="home-pages">${page>1?action('이전',prefix+'-prev'):''}<span>${page} / ${total}</span>${page<total?action('다음',prefix+'-next'):''}</div>`:'';}
 async function renderHome(){
  const version=++renderVersion;root().dataset.homeView='home';root().classList.add('home-service');
  root().innerHTML='<div class="loading" role="status">음악 기록을 불러오는 중…</div>';
  try{
   const summary=await api('/home?page='+homePage);
   const result=viewAll?await api('/songs?page='+homePage):summary;
   if(version!==renderVersion)return;
   root().innerHTML=`<div class="page-heading"><div><div class="eyebrow">YOUR THOUGHTS BETWEEN THE LYRICS</div><h1>음악을 다시 듣고,<br>새롭게 남기는 이야기.</h1><p>좋아하는 구절에 머물고, 당신의 해석을 남겨 보세요.</p></div><div class="count-banner"><div><strong>${summary.total}</strong>기록한 음악</div><span class="divider"></span><div><strong>${summary.comment_count}</strong>남긴 코멘트</div></div></div><section><div class="home-toolbar"><h2>${viewAll?'모든 음악':'최근에 추가한 음악'}</h2><div class="toolbar-actions">${action(viewAll?'최근 기록 보기':'전체 목록 보기','view-all','','text-button')}${action(icon('plus')+' 추가','add','','button dark')}</div></div><div class="song-grid home-grid">${result.items.map(card).join('')}<button class="add-card" data-home-action="add"><span class="add-circle">${icon('plus')}</span><strong>새로운 음악 기록</strong><small>기억하고 싶은 곡을 추가해 보세요</small></button></div>${pages(homePage,result.pages,'home')}${!result.items.length?'<p class="small-muted home-empty-hint">추가 버튼에서 곡을 찾아 첫 음악 기록을 시작해 보세요.</p>':''}</section><div class="home-bottom"><div><p>오늘의 마음에 어울리는 음악이 궁금한가요?</p><small>당신의 기록을 바탕으로 새로운 곡을 발견해 보세요.</small></div><a href="#ai" class="button">${icon('spark')} AI 추천받기</a></div>`;
   loadArtwork(root());
  }catch(error){if(version===renderVersion)root().innerHTML=errorHtml(error,action('다시 불러오기','home-retry'));}
 }
 async function addModal(){
  modalPage=1;modalQuery='';searchVersion++;
  modal('기록을 추가할 음악 선택',`<form class="home-add-search" data-home-form="search"><div class="search-box add-search">${icon('search')}<input type="search" name="q" aria-label="음악 검색" maxlength="100" placeholder="곡 제목 또는 아티스트 검색" required><button class="button dark" type="submit">검색</button></div><label class="home-search-scope">검색 범위 <select name="scope" class="select"><option value="catalog">외부 음악</option><option value="local">저장된 음악·가사</option></select></label></form><div id="home-search-status" role="status"></div><div id="home-add-results" class="add-results"></div><p class="inline-warning">이미 추가한 음악은 인터넷 연결 없이 열 수 있습니다. 외부 검색은 검색 버튼을 눌렀을 때만 요청합니다.</p>`);
  const target=document.getElementById('home-add-results');
  try{const data=await api('/songs');if(target.isConnected)target.innerHTML=searchRows(data.items,false)||empty('첫 음악을 찾아보세요','곡 제목 또는 아티스트를 입력해 주세요.');}
  catch(error){if(target.isConnected)target.innerHTML=errorHtml(error);}
  loadArtwork(target);
  document.querySelector('[data-home-form="search"] input')?.focus();
 }
 function searchRows(items,external){return items.map(s=>`<button class="add-result" data-home-action="select-song" data-id="${esc(external?s.external_id:s.id)}" data-external="${external}">${coverImage(s,true)}<span><strong>${esc(s.title)}</strong><small>${esc(s.artist)}${s.album?' · '+esc(s.album):''}</small>${lyricBadge(s)}</span>${icon('plus')}</button>`).join('');}
 async function search(){
  const target=document.getElementById('home-add-results'),status=document.getElementById('home-search-status');if(!target||!status)return;
  const version=++searchVersion,query=modalQuery,page=modalPage,scope=modalScope;
  const active=()=>target.isConnected&&dialog().open&&version===searchVersion;
  status.textContent='음악 검색 중…';
  try{
   const result=scope==='catalog'?await resource(0,'catalog',{q:query,page},job=>{if(active())status.textContent=progressMessage(job);}):await api('/songs?q='+encodeURIComponent(query)+'&page='+page);
   if(!active())return;
   status.innerHTML=providerNotice(result)+(result.matched_artists?.length?`<p class="small-muted">${esc(query)} → ${esc(result.matched_artists.join(', '))}</p>`:'');
   target.innerHTML=(searchRows(result.items,scope==='catalog')||empty('검색 결과가 없어요','다른 곡명이나 가수명으로 검색해 보세요.'))+pages(page,result.pages,'search');loadArtwork(target);
  }catch(error){if(active()){
   status.innerHTML=errorHtml(error);
   let saved='',label='저장된 음악에서 찾은 결과';
   if(scope==='catalog'){
    try{
     let local=await api('/songs?q='+encodeURIComponent(query));
     if(!local.items.length){local=await api('/songs');label='바로 열 수 있는 저장된 음악';}
     if(local.items.length)saved=`<h3>${label}</h3>`+searchRows(local.items,false);
    }catch{}
   }
   if(!active())return;
   target.innerHTML=action('다시 검색','search-retry')+action('저장된 음악 보기','local-list')+saved;loadArtwork(target);
   if(error.retry_after){const b=target.querySelector('button');b.disabled=true;setTimeout(()=>{if(b.isConnected)b.disabled=false;},error.retry_after*1000);}
  }}
 }
 function inlineNote(c){return `<article class="inline-note" data-comment-id="${c.id}"><div class="note-person"><span class="avatar mine">${c.user.id===getUser().id?'나':esc(c.user.name.slice(0,1))}</span><strong>${esc(c.user.name)}</strong><span class="pill">${c.visibility==='private'?'나만 보기':'친구 공개'}</span><time>${esc(date(c.created_at))}</time></div><p>${esc(c.text)}</p>${c.user.id===getUser().id?`<div class="note-actions">${action('수정','edit-comment',c.id,'')}${action('삭제','delete-comment',c.id,'')}</div>`:''}</article>`;}
 function lyricRows(){return `<ol class="lyric-list">${current.passages.map((p,i)=>`<li class="line-wrapper" id="home-line-${p.id}"><button class="lyric-line" data-home-action="line" data-id="${p.id}" aria-expanded="false" aria-controls="home-editor-${p.id}"><span class="line-number">${String(i+1).padStart(2,'0')}</span><span>${esc(p.text)}</span></button><div class="inline-notes" id="home-notes-${p.id}" aria-live="polite"></div><div id="home-editor-${p.id}"></div></li>`).join('')}</ol>`;}
 function paintComments(){
  if(root().dataset.homeView!=='song'||!current)return;
  for(const p of current.passages){const target=document.getElementById('home-notes-'+p.id);if(target)target.innerHTML=comments.filter(c=>c.passage_id===p.id).map(inlineNote).join('');}
  const ids=new Set(current.passages.map(p=>p.id)),old=comments.filter(c=>!ids.has(c.passage_id));
  const archive=document.getElementById('home-archived-comments');
  if(archive)archive.innerHTML=old.length?`<h2>이전 가사 버전의 기록</h2>${old.map(c=>`<blockquote>${esc(c.quote)}</blockquote>${inlineNote(c)}`).join('')}`:'';
  const more=document.getElementById('home-comment-more');if(more)more.innerHTML=commentPage<commentPages?action('코멘트 더 보기','more-comments'):'';
 }
 async function loadComments(sid){
  const target=document.getElementById('home-comment-more');if(!target)return;
  try{const data=await api('/songs/'+sid+'/comments?page='+(commentPage+1));if(!target.isConnected||current.id!==sid)return;
   comments=[...new Map([...comments,...data.items].map(c=>[c.id,c])).values()].sort((a,b)=>b.id-a.id);commentPage++;commentPages=data.pages;paintComments();
  }catch(error){if(target.isConnected)target.innerHTML=errorHtml(error,action('코멘트 다시 조회','more-comments'));}
 }
 async function renderSong(id){
  const version=++renderVersion;root().dataset.homeView='song';root().classList.add('home-service');
  clearTimeout(lyricsRetryTimer);lyricsBusy=false;lyricsRetryAt=0;
  root().innerHTML='<div class="loading" role="status">음악을 불러오는 중…</div>';
  try{
   const data=await api('/songs/'+id);if(version!==renderVersion)return;current=data;comments=[];commentPage=0;commentPages=0;
   root().innerHTML=`<a class="back-button" href="#home">${icon('back')} 돌아가기</a><div class="song-hero">${coverImage(current)}<div><div class="eyebrow">${esc(current.album||'MUSIC RECORD')}</div><h1>${esc(current.title)}</h1><p class="song-meta">${esc(current.artist)}${current.album?' · '+esc(current.album):''}</p><div class="rating-control" aria-label="내 별점 선택">${Array.from({length:5},(_,i)=>`<button class="${i<(current.rating||0)?'filled':''}" data-home-action="rate" data-id="${i+1}" aria-label="별점 ${i+1}점" aria-pressed="${current.rating===i+1}">${icon('star')}</button>`).join('')}<span class="rating-label">${current.rating?'나의 별점 '+current.rating+'.0':'별점을 남겨 주세요'}</span></div></div><div id="home-detail-bookmark">${bookmark(current,true)}</div></div><div class="detail-layout reverse-detail"><section class="panel lyrics-panel"><div class="panel-header"><h2>가사와 나의 코멘트</h2><span>구절별 음악 기록</span></div><div class="lyric-hint">${icon('note')} 가사를 눌러 감상을 작성하고, 다시 누르면 작성 창을 닫을 수 있어요.</div><div id="home-lyrics">${current.passages.length?lyricRows():lyricEmpty()}</div><div id="home-provider-notice" role="status"></div><div class="home-lyric-buttons">${action(current.passages.length?'가사 새로 확인':'가사 불러오기','lyrics',current.id,'button outline')}${action(icon('plus')+' 기록 추가','record',current.id,'button dark record-button')}</div><div id="home-comment-more"></div><div id="home-archived-comments"></div></section><aside class="panel critics-panel"><div class="panel-header"><h2>음악 평론 · 선정글</h2><span>CRITICS’ NOTES</span></div><div id="home-reviews">${current.reviews.length?reviewCards(current.reviews):'<p class="loading" role="status">평론·선정글을 찾는 중…</p>'}</div><div id="home-review-notice" role="status"></div><p class="critic-disclaimer">발췌와 선정 정보를 간략히 표시합니다. 자세한 내용은 원문에서 읽어보세요.</p></aside></div>`;
   loadArtwork(root());loadReviews();
   lyricsRetryAt=Date.now()+(current.lyrics_retry_after||0)*1000;syncLyricButtons();
   await loadComments(current.id);
   if(pendingSongId===current.id)pendingSongId=null;
   if(!current.passages.length&&current.lyrics_status!=='instrumental'&&lyricsRetryAt<=Date.now())await loadLyrics(false);
  }catch(error){if(version===renderVersion)root().innerHTML=errorHtml(error,action('다시 열기','song-retry',id));}
 }
 async function loadLyrics(refresh=false,candidateId){
  const target=document.getElementById('home-provider-notice');if(!target||!current||lyricsBusy)return;
  if(lyricsRetryAt>Date.now()){syncLyricButtons();return;}
  if([...root().querySelectorAll('[data-home-form="comment"] textarea')].some(t=>t.value.trim())){toast('작성 중인 감상을 먼저 저장해 주세요.');return;}
  const sid=current.id;lyricsBusy=true;syncLyricButtons();target.textContent='가사를 조회하는 중…';
  try{
   const result=await resource(sid,'lyrics',candidateId?{candidate_id:candidateId}:{refresh},job=>{if(target.isConnected&&current?.id===sid)target.textContent=progressMessage(job);});
   if(!target.isConnected||current.id!==sid)return;
   candidates=result.candidates||[];let html=providerNotice(result);
   if(result.message)html+=`<p>${esc(result.message)}</p>`;
   lyricsRetryAt=Date.now()+(result.retry_after||0)*1000;
   if(result.status==='candidates')html+=`<p>제목이 다른 가사 후보입니다. 같은 곡인지 확인해 주세요.</p>${candidates.map(c=>`<article class="lyric-candidate"><h3>${esc(c.title)}</h3><p>${esc(c.artist)} · ${esc(c.album)} · ${c.duration}초</p><blockquote>${esc(c.preview)}</blockquote>${action('후보 확인','candidate',c.id)}</article>`).join('')}`;
   const updated=await api('/songs/'+sid);if(!target.isConnected)return;current=updated;
   document.getElementById('home-lyrics').innerHTML=current.passages.length?lyricRows():lyricEmpty();
   target.innerHTML=html;paintComments();
  }catch(error){if(target.isConnected){
   lyricsRetryAt=Date.now()+(error.retry_after||0)*1000;
   if(!current.passages.length){current.lyrics_status='error';document.getElementById('home-lyrics').innerHTML=lyricEmpty();}
   target.innerHTML=errorHtml(error);
  }}finally{if(target.isConnected&&current?.id===sid){lyricsBusy=false;syncLyricButtons();}}
 }
 function editor(p){return `<form class="inline-editor" data-home-form="comment" data-id="${p.id}"><label class="form-label" for="home-text-${p.id}">이 구절은 어떻게 들렸나요?</label><textarea class="textarea" id="home-text-${p.id}" name="text" maxlength="2000" required placeholder="당신의 감상이나 떠오른 기억을 남겨 보세요."></textarea><div class="form-meta"><span>한 줄의 가사, 하나의 새로운 이야기.</span></div><div class="form-bottom"><select class="select" name="visibility" aria-label="코멘트 공개 범위"><option value="private">나만 보기</option><option value="friends">친구에게 공개</option></select><button class="button dark" type="submit">코멘트 저장</button></div></form>`;}
 document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-home-action]');if(!button||button.disabled)return;event.preventDefault();button.disabled=true;
  const {homeAction:name,id}=button.dataset;
  try{
   if(name==='close')dialog().close();
   else if(name==='add')await addModal();
   else if(name==='view-all'){viewAll=!viewAll;homePage=1;await renderHome();}
   else if(name==='home-retry')await renderHome();
   else if(name==='home-next'||name==='home-prev'){homePage+=name==='home-next'?1:-1;await renderHome();}
   else if(name==='search-next'||name==='search-prev'){modalPage+=name==='search-next'?1:-1;await search();}
   else if(name==='search-retry')await search();
   else if(name==='local-list'){modalQuery='';modalPage=1;modalScope='local';const form=document.querySelector('[data-home-form="search"]');form.elements.scope.value='local';form.elements.q.value='';await search();}
   else if(name==='select-song'){
    const result=button.dataset.external==='true'?await api('/catalog/import','POST',{external_id:id}):{id:Number(id)};
    await api('/records/'+result.id,'PUT',{recorded:true});dialog().close();pendingSongId=result.id;location.hash='song/'+result.id;
   }
   else if(name==='bookmark'){
    let summary=root().dataset.homeView==='song'&&current?.id===Number(id)?current:null;
    if(!summary)summary=await api('/songs/'+id);
    await api('/records/'+id,'PUT',{saved:!summary.saved});summary.saved=!summary.saved;
    if(root().dataset.homeView==='home')await renderHome();else{const target=document.getElementById('home-detail-bookmark');if(target)target.innerHTML=bookmark(summary,true);}
    toast(summary.saved?'저장한 곡에 담았어요.':'저장한 곡에서 뺐어요.');
   }
   else if(name==='song-retry')await renderSong(Number(id));
   else if(name==='rate'){
    const sid=current.id;await api('/records/'+sid,'PUT',{rating:Number(id),recorded:true});if(current.id!==sid||root().dataset.homeView!=='song')return;current.rating=Number(id);
    root().querySelectorAll('[data-home-action="rate"]').forEach((b,i)=>{b.classList.toggle('filled',i<current.rating);b.setAttribute('aria-pressed',String(i+1===current.rating));});
    root().querySelector('.rating-label').textContent='나의 별점 '+current.rating+'.0';
   }
   else if(name==='record'){
    await api('/records/'+current.id,'PUT',{recorded:true});const first=root().querySelector('[data-home-action="line"]');if(first&&first.getAttribute('aria-expanded')!=='true')first.click();else if(first)document.getElementById('home-editor-'+first.dataset.id)?.querySelector('textarea')?.focus();else toast('음악 기록에 추가했어요.');
   }
   else if(name==='line'){
    const target=document.getElementById('home-editor-'+id);if(!target)return;
    const opened=!!target.querySelector('form');target.innerHTML=opened?'':editor({id});button.classList.toggle('selected',!opened);button.setAttribute('aria-expanded',String(!opened));
    if(!opened)target.querySelector('textarea').focus({preventScroll:true});
   }
   else if(name==='more-comments')await loadComments(current.id);
   else if(name==='lyrics')await loadLyrics(true);
   else if(name==='reviews')await loadReviews();
   else if(name==='candidate'){
    const c=candidates.find(c=>c.id===Number(id));if(!c)return;
    modal('이 가사를 연결할까요?',`<p>${esc(current.title)} ↔ ${esc(c.title)}</p><p>같은 곡인지 확인한 경우에만 연결하세요.</p>`,action('확인하고 연결','confirm-candidate',id,'button dark'));
   }
   else if(name==='confirm-candidate'){dialog().close();await loadLyrics(false,Number(id));}
   else if(name==='edit-comment'){
    const c=await api('/comments/'+id);
    modal('코멘트 수정',`<blockquote class="selected-quote">${esc(c.quote)}</blockquote><form data-home-form="edit" data-id="${c.id}"><label class="form-label" for="home-edit-text">나의 코멘트</label><textarea class="textarea" id="home-edit-text" name="text" maxlength="2000" required>${esc(c.text)}</textarea><div class="form-bottom"><select class="select" name="visibility" aria-label="공개 범위"><option value="private" ${c.visibility==='private'?'selected':''}>나만 보기</option><option value="friends" ${c.visibility==='friends'?'selected':''}>친구에게 공개</option></select><button class="button dark">저장하기</button></div></form>`);
   }
   else if(name==='delete-comment')modal('코멘트를 삭제할까요?','<p>선택한 코멘트가 삭제됩니다.</p>',action('취소','close')+action('삭제','confirm-delete',id,'button danger'));
   else if(name==='confirm-delete'){await api('/comments/'+id,'DELETE');comments=comments.filter(c=>c.id!==Number(id));dialog().close();paintComments();toast('코멘트를 삭제했어요.');}
  }catch(error){toast(error.message);}
  finally{if(name==='lyrics')syncLyricButtons();else if(name!=='reviews')button.disabled=false;}
 });
 document.addEventListener('submit',async event=>{
  const form=event.target;if(!form.matches('[data-home-form]'))return;event.preventDefault();const button=form.querySelector('button');if(button.disabled)return;button.disabled=true;
  const data=Object.fromEntries(new FormData(form));
  try{
   if(form.dataset.homeForm==='search'){modalQuery=data.q.trim();modalScope=data.scope;modalPage=1;await search();}
   else if(form.dataset.homeForm==='comment'){
    const c=await api('/comments','POST',{...data,passage_id:Number(form.dataset.id)});
    if(!form.isConnected)return;comments=[c,...comments.filter(n=>n.id!==c.id)];form.remove();
    const line=root().querySelector(`[data-home-action="line"][data-id="${c.passage_id}"]`);line.classList.remove('selected');line.setAttribute('aria-expanded','false');paintComments();toast('코멘트를 저장했어요.');
   }
   else if(form.dataset.homeForm==='edit'){
    await api('/comments/'+form.dataset.id,'PATCH',data);const updated=await api('/comments/'+form.dataset.id);comments=comments.map(c=>c.id===updated.id?updated:c);dialog().close();paintComments();toast('코멘트를 수정했어요.');
   }
  }catch(error){toast(error.message);}finally{button.disabled=false;}
 });
 return {configure(context){api=context.api;getUser=context.getUser;},renderHome,renderSong,leave(){renderVersion++;clearTimeout(lyricsRetryTimer);root().classList.remove('home-service');delete root().dataset.homeView;}};
})();
