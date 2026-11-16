'use strict';
const main=document.querySelector('#main'),modal=document.querySelector('#modal');
let user,csrf,song,searchPage=1,searchQuery='',searchScope='catalog',lyricCandidates=[],songComments=[],songCommentsPage=0,songCommentsPages=0;
async function api(path,method='GET',data){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
 try{
  const r=await fetch('/api'+path,{method,signal:controller.signal,headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:data===undefined?undefined:JSON.stringify(data)});
  const j=await r.json();
  if(!r.ok){if(r.status===401){user=null;auth();}throw Error(j.error||'요청 실패');}
  return j;
 }catch(e){if(e.name==='AbortError')throw Error('응답 시간이 초과되었습니다. 다시 시도해 주세요.');throw e;}
 finally{clearTimeout(timer);}
}
const btn=(label,action,id='')=>`<button class="button outline" data-action="${action}" data-id="${esc(id)}">${label}</button>`;
const searchInput=(label,type='search')=>`<input name="q" type="${type}" aria-label="${label}" placeholder="${label}" maxlength="100" required>`;
const input=(name,label,type='text')=>`<label class="form-label">${label}<input class="field" name="${name}" type="${type}" ${type==='password'?'minlength="8" maxlength="128"':''} required></label>`;
function show(title,html){document.querySelector('#modal-content').innerHTML=`<div class="modal-heading"><h2>${esc(title)}</h2>${btn('닫기','close')}</div><div class="modal-body">${html}</div>`;if(!modal.open)modal.showModal();}
function message(e){show('안내',`<p>${esc(e.message||e)}</p>`);}
function auth(signup=false){main.innerHTML=`<h1>${signup?'회원가입':'다시 듣고, 새롭게 남기다'}</h1><form class="panel" id="${signup?'register':'login'}">${signup?input('email','이메일','email')+input('username','아이디 (영문·숫자·밑줄 3~32자)')+input('name','표시 이름'):input('identifier','이메일 또는 아이디')}${input('password','비밀번호 (8~128자)','password')}<button class="button dark">${signup?'가입':'로그인'}</button>${btn(signup?'로그인':'회원가입',signup?'login':'register')}</form>`;}
const card=s=>`<article class="song-card panel"><a class="song-title" href="#song/${s.id}">${esc(s.title)}</a><p>${esc(s.artist)}</p></article>`;
const externalCard=s=>`<article class="song-card panel"><h3>${esc(s.title)}</h3><p>${esc(s.artist)}</p><p class="small-muted">${esc(s.album||'앨범 정보 없음')}</p>${btn('가사와 기록 보기','import',s.external_id)}<small>MusicBrainz</small></article>`;
const note=c=>`<article class="saved-note"><strong>${esc(c.user.name)}</strong><time> · ${esc(new Date(c.created_at).toLocaleString('ko-KR'))}</time><span class="pill">${c.visibility==='private'?'나만 보기':'친구 공개'}</span><blockquote>${esc(c.quote)}</blockquote><p>${esc(c.text)}</p><a href="#song/${c.song_id}">곡 보기</a>${c.user.id===user.id?btn('수정','edit',c.id)+btn('삭제','delete',c.id):''}</article>`;
const PAGE_SIZE=20;
const initial=name=>Array.from(String(name??'').trim())[0]||'나';
function toast(text){const t=document.querySelector('#toast');t.textContent=text;t.classList.add('visible');clearTimeout(toast.timer);toast.timer=setTimeout(()=>t.classList.remove('visible'),2400);}
async function commentSummary(){
 const first=await api('/comments'),recent=first.items.slice(0,3);
 if(first.pages<=1)return {total:first.items.length,recent};
 const last=await api('/comments?page='+first.pages);
 return {total:(first.pages-1)*PAGE_SIZE+last.items.length,recent};
}
async function allRecords(){
 const first=await api('/records');
 const rest=await Promise.all(Array.from({length:Math.max(0,first.pages-1)},(_,i)=>api('/records?page='+(i+2))));
 return [first,...rest].flatMap(r=>r.items);
}
const accountNote=c=>`<a class="account-note" href="#song/${c.song_id}"><blockquote>${esc(c.quote)}</blockquote><p>${esc(c.text)}</p><span class="account-note-meta"><span class="pill">${c.visibility==='private'?'나만 보기':'친구 공개'}</span><time>${esc(new Date(c.created_at).toLocaleDateString('ko-KR'))}</time></span></a>`;
async function account(){
 const [c,r,f]=await Promise.allSettled([commentSummary(),allRecords(),api('/friends')]);
 const comments=c.value,records=r.value,friends=f.value?.items;
 const incoming=friends?.filter(x=>x.status==='incoming').length||0;
 const stats=[['코멘트',comments?.total,'#records','comment'],['저장한 곡',records?.filter(x=>x.saved).length,'#records','bookmark'],['기록한 음악',records?.filter(x=>x.recorded).length,'#records','headphones'],['친구',friends?.filter(x=>x.status==='accepted').length,'#friends','friends']];
 main.innerHTML=`<div class="account-page">
 <section class="account-hero" aria-labelledby="account-title"><span class="avatar account-avatar" aria-hidden="true">${esc(initial(user.name))}</span><div class="account-identity"><div class="eyebrow">MY ACCOUNT</div><h1 id="account-title">${esc(user.name)}</h1><p>@${esc(user.username)}</p></div><a class="button outline" href="#records">나의 기록 보기</a></section>
 <div class="account-stats">${stats.map(([label,value,href,ic])=>`<a class="account-stat" href="${href}"><span>${icon(ic)}${label}</span><strong>${value===undefined?'—':value}</strong></a>`).join('')}</div>
 <div class="account-grid"><div class="account-column">
  <section class="panel account-section" aria-labelledby="account-profile-title"><div class="panel-header"><h2 id="account-profile-title">프로필</h2></div><form id="profile" class="account-form"><label class="form-label" for="account-name">표시 이름</label><div class="account-field-row"><input class="field" id="account-name" name="name" value="${esc(user.name)}" maxlength="40" autocomplete="nickname" required><button class="button dark">저장</button></div><p class="small-muted">친구 목록과 코멘트에 보이는 이름이에요. 1~40자로 입력하세요.</p></form><dl class="account-info"><div><dt>아이디</dt><dd>@${esc(user.username)}</dd></div></dl></section>
  <section class="panel account-section" aria-labelledby="account-settings-title"><div class="panel-header"><h2 id="account-settings-title">계정</h2></div>${incoming?`<a class="account-row" href="#friends"><span><strong>받은 친구 요청</strong><small>친구 화면에서 수락하거나 거절할 수 있어요.</small></span><span class="pill">${incoming}건</span></a>`:''}<div class="account-row"><span><strong>로그아웃</strong><small>이 브라우저에서 로그인 상태를 종료해요.</small></span><button class="button danger small" data-action="logout">로그아웃</button></div></section>
 </div>
 <section class="panel account-section" aria-labelledby="account-notes-title"><div class="panel-header"><h2 id="account-notes-title">최근 남긴 코멘트</h2>${comments?.total?'<a class="text-button" href="#records">전체 보기</a>':''}</div>${comments===undefined?'<p class="account-empty" role="alert">코멘트를 불러오지 못했어요.</p>':comments.recent.map(accountNote).join('')||'<div class="account-empty"><p>아직 남긴 코멘트가 없어요.<br>마음에 닿은 가사 구절에 첫 감상을 남겨 보세요.</p><a class="button outline" href="#home">음악 찾으러 가기</a></div>'}</section>
 </div></div>`;
}
function nav(){
 const userButton=document.querySelector('.user-button'),onAccount=location.hash==='#account';
 document.querySelector('#profile-name').textContent=user?.name||'로그인';
 userButton.querySelector('.avatar').textContent=user?initial(user.name):'나';
 userButton.setAttribute('aria-label',user?`내 계정: ${user.name}`:'로그인');
 userButton.classList.toggle('active',Boolean(user)&&onAccount);
 if(user&&onAccount)userButton.setAttribute('aria-current','page');else userButton.removeAttribute('aria-current');
 document.querySelector('#navigation').innerHTML=[['home','홈'],['friends','친구'],['ai','AI 추천'],['records','나의 기록']].map(([a,b])=>`<a class="nav-link" href="#${a}">${b}</a>`).join('');}
async function searchSongs(){
 const target=document.querySelector('#results');
 target.innerHTML='<p role="status">음악 검색 중…</p>';
 try{
  const path=searchScope==='catalog'?'/catalog/search':'/songs';
  const r=await api(path+'?q='+encodeURIComponent(searchQuery)+'&page='+searchPage);
  if(!target.isConnected)return;
  target.innerHTML=`${r.matched_artists?.length?`<p class="small-muted">가수 별칭으로 찾았어요: ${esc(searchQuery)} → ${esc(r.matched_artists.join(', '))}</p>`:''}<div class="song-grid">${r.items.map(searchScope==='catalog'?externalCard:card).join('')||'<p>검색 결과가 없습니다. 곡명이나 가수명을 바꿔 보세요.</p>'}</div><div class="search-pages">${searchPage>1?btn('이전','search-prev'):''}<span>${searchPage} / ${Math.max(1,r.pages)}</span>${searchPage<r.pages?btn('다음','search-next'):''}</div>`;
 }catch(e){if(target.isConnected)target.innerHTML=`<p role="alert">${esc(e.message)}</p>${btn('다시 검색','search-retry')}`;}
}
const inlineNote=c=>`<article class="passage-comment" data-comment-id="${c.id}"><div class="note-person"><strong>${esc(c.user.name)}</strong><span class="pill">${c.visibility==='private'?'나만 보기':'친구 공개'}</span><time>${esc(new Date(c.created_at).toLocaleString('ko-KR'))}</time></div><p>${esc(c.text)}</p>${c.user.id===user.id?`<div class="note-actions">${btn('수정','edit',c.id)}${btn('삭제','delete',c.id)}</div>`:''}</article>`;
function paintSongComments(){
 const list=document.querySelector('#song-comment-list');if(!list||!song)return;
 for(const p of song.passages){
  const target=document.getElementById('notes-'+p.id);
  if(target)target.innerHTML=songComments.filter(c=>c.passage_id===p.id).map(inlineNote).join('');
 }
 const activeIds=new Set(song.passages.map(p=>p.id));
 const archived=songComments.filter(c=>!activeIds.has(c.passage_id));
 list.innerHTML=archived.length?`<h2>이전 가사 버전의 코멘트</h2><p class="small-muted">작성 당시 구절과 함께 보관합니다.</p>${archived.map(note).join('')}`:'';
 document.querySelector('#song-comment-status').innerHTML=songCommentsPage<songCommentsPages?btn('코멘트 더 불러오기','more-comments'):'';
}
async function loadSongComments(sid){
 const target=document.querySelector('#song-comment-list'),status=document.querySelector('#song-comment-status');
 if(!target||!status)return;
 status.textContent='코멘트를 불러오는 중…';
 try{
  const r=await api('/songs/'+sid+'/comments?page='+(songCommentsPage+1));
  if(!target.isConnected||song?.id!==sid)return;
  songComments=[...new Map([...songComments,...r.items].map(c=>[c.id,c])).values()].sort((a,b)=>b.id-a.id);
  songCommentsPage++;songCommentsPages=r.pages;paintSongComments();
 }catch(e){if(status.isConnected)status.innerHTML=`<p role="alert">${esc(e.message)}</p>${btn('코멘트 다시 조회','more-comments')}`;}
}
function lyricsHtml(s){return `${s.lyrics_title&&s.lyrics_title!==s.title?`<p class="small-muted">가사 제공처 제목: ${esc(s.lyrics_title)}${s.lyrics_match==='user_confirmed'?' · 사용자 확인 연결':' · 확인된 다른 제목'}</p>`:''}${s.passages.map(p=>`<div class="passage-block"><button class="lyric-line" data-action="passage" data-id="${p.id}" aria-expanded="false" aria-controls="p-${p.id}">${esc(p.text)}</button><div class="passage-comments" id="notes-${p.id}" aria-live="polite"></div><div id="p-${p.id}"></div></div>`).join('')||'<p>가사 없음 — LRCLIB에서 곡명·가수·재생시간이 일치하는 가사를 찾지 못했습니다.</p>'}${s.source_url?`<p class="lyrics-source"><a href="${esc(s.source_url)}" target="_blank" rel="noopener">가사 출처: LRCLIB</a> · 이용자 등록 자료</p>`:''}`;}
async function loadLyrics(sid,candidateId){
 const target=document.querySelector('#lyrics-content');if(!target)return;
 target.innerHTML='<p role="status">LRCLIB에서 가사를 찾고 있습니다…</p>';
 try{
  const response=await api('/songs/'+sid+'/lyrics','POST',candidateId===undefined?{}:{candidate_id:candidateId});
  const updated=await api('/songs/'+sid);
  if(!target.isConnected)return;
  song=updated;lyricCandidates=response.candidates||[];
  if(response.status==='candidates'){
   target.innerHTML=`${updated.passages.length?lyricsHtml(updated):''}<p>같은 가수·앨범에서 재생시간이 비슷한 가사를 찾았습니다. 제목이 달라 자동 연결하지 않았습니다. 내용을 확인해 주세요.</p>${lyricCandidates.map(c=>`<article class="lyric-candidate"><h3>${esc(c.title)}</h3><p>${esc(c.artist)} · ${esc(c.album)} · ${esc(c.duration)}초</p><blockquote>${esc(c.preview)}</blockquote>${btn('후보 확인','choose-lyrics',c.id)}</article>`).join('')}`;
  }else target.innerHTML=lyricsHtml(updated);
  paintSongComments();
 }catch(e){if(target.isConnected)target.innerHTML=`<p role="alert">가사 조회 실패: ${esc(e.message)}</p>${btn('다시 조회','lyrics',sid)}`;}
}
async function detail(id){
 const current=await api('/songs/'+Number(id));song=current;
 songComments=[];songCommentsPage=0;songCommentsPages=0;
 main.innerHTML=`<a href="#home">홈으로</a><div class="song-hero"><div><h1>${esc(current.title)}</h1><p>${esc(current.artist)} · ${esc(current.album||'앨범 정보 없음')}</p>${current.provider==='musicbrainz'?`<a class="small-muted" href="https://musicbrainz.org/recording/${esc(current.external_id)}" target="_blank" rel="noopener">음악 정보: MusicBrainz</a>`:''}<div class="song-actions">${btn('곡 저장','save',current.id)}${btn('저장 취소','unsave',current.id)}${btn('음악 기록 추가','record',current.id)}<label>별점 <select id="rating"><option value="">선택</option>${[1,2,3,4,5].map(x=>`<option>${x}</option>`).join('')}</select></label></div></div></div><div class="detail-layout"><section class="panel"><h2>가사와 감상</h2><p class="small-muted">구절을 누르면 작성 창이 열리고, 다시 누르면 닫힙니다.</p><div id="lyrics-content">${lyricsHtml(current)}</div>${btn('가사 다시 조회','lyrics',current.id)}</section><aside class="panel"><h2>평론</h2>${current.reviews.map(r=>`<article><h3>${esc(r.title)}</h3><p>${esc(r.author)} · ${esc(r.source)}</p><p>${esc(r.introduction||'')}</p><a href="${/^https?:\/\//.test(r.url)?esc(r.url):'#'}" rel="noopener" target="_blank">원문</a></article>`).join('')||'등록된 평론 없음'}</aside></div><section id="song-comments"><div id="song-comment-list"></div><div id="song-comment-status" role="status"></div></section>`;
 await loadSongComments(current.id);
 if(!current.passages.length)await loadLyrics(current.id);
}
async function render(){
 nav();if(!user)return auth();const [route,id]=location.hash.slice(1).split('/');
 if(route==='song')await detail(id);
 else if(route==='account')await account();
 else if(route==='friends'){
  const r=await api('/friends'),feed=await api('/comments?scope=friends');
  main.innerHTML=`<h1>같은 음악, 다른 이야기.</h1><form id="users" class="search-box">${searchInput('이름 또는 아이디')}<button class="button dark">친구 검색</button></form><div id="results"></div><section class="panel"><h2>친구와 요청</h2>${r.items.map(x=>`<div class="person-row"><span>${esc(x.user.name)} @${esc(x.user.username)} · ${esc(x.status)}</span>${x.status==='incoming'?btn('수락','accept',x.user.id):''}${btn(x.status==='accepted'?'친구 해제':x.status==='incoming'?'거절':'요청 취소','remove',x.user.id)}${x.status==='accepted'?btn('기록 보기','friend-feed',x.user.id):''}</div>`).join('')||'아직 친구가 없습니다.'}</section><h2>공유 코멘트</h2>${feed.items.map(note).join('')||'공유된 코멘트 없음'}`;
 }else if(route==='records')main.innerHTML=`<h1>나의 기록</h1>${btn('코멘트','notes')}${btn('기록한 음악','recorded')}${btn('저장한 곡','saved')}<input class="field" id="filter" placeholder="현재 목록 검색"><div id="results">${(await api('/comments')).items.map(note).join('')}</div>`;
 else if(route==='ai')main.innerHTML=`<h1>당신의 취향에 이어지는 음악.</h1><section class="recommend-top"><p>Gemini 설정 보류 · 실제 AI 연동 미검증</p>${btn('추천받기','recommend')}</section>`;
 else{
  main.innerHTML=`<div class="page-heading"><div><div class="eyebrow">YOUR THOUGHTS BETWEEN THE LYRICS</div><h1>음악을 다시 듣고,<br>새롭게 남기는 이야기.</h1></div></div><div class="search-options"><label for="search-scope">검색 범위</label><select class="select" id="search-scope"><option value="catalog">외부 음악 (곡명·가수)</option><option value="local">저장된 음악·가사</option></select></div><form id="search" class="search-box">${searchInput('곡명 또는 가수명 검색')}<button class="button dark">검색</button></form><p class="small-muted">음악 정보 MusicBrainz · 가사 LRCLIB. 검색 결과를 선택하면 로컬 DB에 추가합니다.</p><h2 id="results-title">최근 추가한 음악</h2><div id="results"><div class="song-grid">${(await api('/songs')).items.map(card).join('')||'<p>검색해서 첫 음악을 찾아보세요.</p>'}</div></div>`;
  document.querySelector('#search-scope').value=searchScope;
  if(searchQuery){document.querySelector('#search input').value=searchQuery;document.querySelector('#results-title').textContent='검색 결과';await searchSongs();}
 }
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-action]');if(!b)return;e.preventDefault();if(b.disabled)return;b.disabled=true;const {action,id}=b.dataset;
 try{
  if(action==='close')modal.close();
  else if(action==='register'||action==='login')auth(action==='register');
  else if(action==='logout'){await api('/logout','POST');user=null;modal.close();await render();}
  else if(action==='about')show('서비스 안내','<p>기록은 SQLite에 저장합니다. 음악 정보는 MusicBrainz, 가사는 LRCLIB 공개 API로 조회합니다. 곡마다 가사 제공 여부가 다릅니다. Gemini는 설정 보류 상태입니다.</p>');
  else if(action==='import'){b.textContent='곡 불러오는 중…';const s=await api('/catalog/import','POST',{external_id:id});location.hash='song/'+s.id;}
  else if(action==='lyrics')await loadLyrics(Number(id));
  else if(action==='more-comments')await loadSongComments(song.id);
  else if(action==='choose-lyrics'){
   const candidate=lyricCandidates.find(c=>c.id===Number(id));if(!candidate)return;
   show('이 가사를 연결할까요?',`<p>${esc(song.title)} ↔ ${esc(candidate.title)}</p><p>제목이 다릅니다. 같은 곡의 가사인지 확인한 경우에만 연결하세요.</p>${btn('확인하고 연결','confirm-lyrics',candidate.id)}`);
  }
  else if(action==='confirm-lyrics'){modal.close();await loadLyrics(song.id,Number(id));}
  else if(action==='search-prev'||action==='search-next'){searchPage+=action==='search-next'?1:-1;await searchSongs();}
  else if(action==='search-retry')await searchSongs();
  else if(action==='passage'){
   const target=document.getElementById('p-'+id);
   if(!target)return;
   const expanded=!target.querySelector('.inline-editor');
   b.setAttribute('aria-expanded',String(expanded));
   if(!expanded)target.replaceChildren();
   else target.innerHTML=`<form class="inline-editor" id="comment" data-id="${id}"><textarea class="textarea" name="text" maxlength="2000" required></textarea><select class="select" name="visibility"><option value="private">나만 보기</option><option value="friends">친구에게 공개</option></select><button class="button dark">감상 저장</button></form>`;
  }
  else if(['save','unsave','record'].includes(action)){await api('/records/'+id,'PUT',action==='record'?{recorded:true}:{saved:action==='save'});show('저장 완료','<p>기록을 저장했습니다.</p>');}
  else if(action==='edit'){const c=await api('/comments/'+id);show('코멘트 수정',`<form id="edit" data-id="${id}"><textarea class="textarea" name="text" maxlength="2000" required>${esc(c.text)}</textarea><select class="select" name="visibility"><option value="private" ${c.visibility==='private'?'selected':''}>나만 보기</option><option value="friends" ${c.visibility==='friends'?'selected':''}>친구 공개</option></select><button class="button dark">저장</button></form>`);}
  else if(action==='delete')show('삭제할까요?',`<p>삭제한 코멘트는 복구할 수 없습니다.</p>${btn('삭제','confirm-delete',id)}`);
  else if(action==='confirm-delete'){await api('/comments/'+id,'DELETE');modal.close();await render();}
  else if(action==='request'){await api('/friends/'+id,'POST');await render();}
  else if(action==='accept'||action==='remove'){await api('/friends/'+id,action==='accept'?'PATCH':'DELETE');await render();}
  else if(action==='friend-feed')show('친구의 기록',(await api('/comments?scope=friends&user_id='+id)).items.map(note).join('')||'공유 기록 없음');
  else if(action==='notes')document.querySelector('#results').innerHTML=(await api('/comments')).items.map(note).join('');
  else if(action==='saved'||action==='recorded'){const r=await api('/records');const s=await Promise.all(r.items.filter(x=>x[action]).map(x=>api('/songs/'+x.song_id)));document.querySelector('#results').innerHTML=s.map(card).join('')||'기록 없음';}
  else if(action==='recommend')await api('/recommendations','POST',{});
 }catch(err){message(err);}finally{b.disabled=false;if(action==='import')b.textContent='가사와 기록 보기';}
});
document.addEventListener('submit',async e=>{
 e.preventDefault();const f=e.target,b=f.querySelector('button');if(!b||b.disabled)return;b.disabled=true;const data=Object.fromEntries(new FormData(f));
 try{
  if(f.id==='login'){const r=await api('/login','POST',data);user=r.user;csrf=r.csrf_token;await render();}
  else if(f.id==='register'){await api('/register','POST',data);auth();}
  else if(f.id==='profile'){user=(await api('/profile','PATCH',data)).user;await render();toast('이름을 저장했어요.');}
  else if(f.id==='search'){searchQuery=data.q;searchPage=1;searchScope=document.querySelector('#search-scope').value;document.querySelector('#results-title').textContent='검색 결과';await searchSongs();}
  else if(f.id==='users')document.querySelector('#results').innerHTML=(await api('/users?q='+encodeURIComponent(data.q))).items.map(u=>`<div class="person-row">${esc(u.name)} @${esc(u.username)} ${btn('친구 요청','request',u.id)}</div>`).join('')||'검색 결과 없음';
  else if(f.id==='comment'){
   const created=await api('/comments','POST',{...data,passage_id:Number(f.dataset.id)});
   if(f.isConnected&&song?.id===created.song_id){
    songComments=[created,...songComments.filter(c=>c.id!==created.id)];
    f.remove();
    document.querySelector(`[data-action="passage"][data-id="${created.passage_id}"]`)?.setAttribute('aria-expanded','false');
    paintSongComments();
    document.getElementById('notes-'+created.passage_id)?.scrollIntoView({block:'nearest',behavior:'smooth'});
   }
  }
  else if(f.id==='edit'){await api('/comments/'+f.dataset.id,'PATCH',data);modal.close();await render();}
 }catch(err){message(err);}finally{b.disabled=false;}
});
document.addEventListener('change',async e=>{if(e.target.id==='rating'&&e.target.value)try{await api('/records/'+song.id,'PUT',{rating:Number(e.target.value)});}catch(err){message(err);}});
document.addEventListener('input',e=>{if(e.target.id==='filter')document.querySelectorAll('#results article').forEach(a=>a.hidden=!a.textContent.toLowerCase().includes(e.target.value.toLowerCase()));});
window.addEventListener('hashchange',()=>render().catch(message));
(async()=>{try{const r=await api('/session');user=r.user;csrf=r.csrf_token;await render();}catch(err){main.textContent=err.message;}})();
