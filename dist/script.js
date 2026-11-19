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
async function allPages(path){
 const sep=path.includes('?')?'&':'?',first=await api(path);
 const rest=await Promise.all(Array.from({length:Math.max(0,first.pages-1)},(_,i)=>api(path+sep+'page='+(i+2))));
 return [first,...rest].flatMap(r=>r.items);
}
const allRecords=()=>allPages('/records');
// 곡 제목·가수는 바뀌지 않으므로 화면 이동 사이에 재사용합니다.
const songCache=new Map();
async function songMap(ids){
 const missing=[...new Set(ids)].filter(id=>!songCache.has(id));
 await Promise.all(missing.map(id=>api('/songs/'+id).then(s=>songCache.set(id,{id:s.id,title:s.title,artist:s.artist,album:s.album,cover:s.cover||null})).catch(()=>{})));
 return Object.fromEntries(ids.filter(id=>songCache.has(id)).map(id=>[id,songCache.get(id)]));
}
const ORB_TONES=['sky','dawn','dusk','mint','honey'];
const orbClass=id=>`orb orb-${ORB_TONES[(Math.max(1,Number(id)||1)-1)%ORB_TONES.length]}`;
// 나의 기록·내 계정 화면. 디자인 규칙: docs/design/records-account-system.md
const COVER_TONES=['sage','sand','sky','rose','lilac'];
const coverTone=s=>COVER_TONES[(s?.id||0)%COVER_TONES.length];
const coverTile=(s,size)=>`<span class="rv-cover ${size} rv-tile tone-${coverTone(s)}" aria-hidden="true">${esc(initial(s?.title||'♪'))}</span>`;
// 표지를 불러오지 못하면 error 핸들러가 글자 타일로 바꿉니다.
const cover=(s,size='')=>s?.cover?`<img class="rv-cover ${size}" src="${esc(s.cover)}" alt="" loading="lazy" decoding="async" data-song="${esc(s.id)}">`:coverTile(s,size);
const visLabel=v=>v==='private'?'나만 보기':'친구 공개';
const songLine=s=>`${esc(s?.artist||'')}${s?.album?` · ${esc(s.album)}`:''}`;
const WEEKDAYS='일월화수목금토';
const dayMark=d=>{const t=new Date(d);return `<time class="rv-date" datetime="${esc(d)}"><b>${t.getDate()}</b><span>${WEEKDAYS[t.getDay()]}</span></time>`;};
const monthLabel=d=>{const t=new Date(d);return `${t.getFullYear()}년 ${t.getMonth()+1}월`;};
const STAR='<path d="M12 2.8l2.8 5.8 6.3.9-4.6 4.4 1.1 6.3L12 17.2l-5.6 3 1.1-6.3-4.6-4.4 6.3-.9z"/>';
const stars=n=>n?`<span class="rv-stars" role="img" aria-label="별점 5점 중 ${n}점">${[1,2,3,4,5].map(i=>`<svg viewBox="0 0 24 24" aria-hidden="true"${i<=n?' class="on"':''}>${STAR}</svg>`).join('')}</span>`:'<span>별점 없음</span>';
const ratingOf=r=>r.recorded||r.rating?stars(r.rating):'<span>아직 기록 전</span>';
const sectionHead=(id,title,count,link='')=>`<div class="rv-section-head"><h2 id="${id}">${title}${count===undefined?'':` <span class="rv-count">${count}</span>`}</h2>${link}</div>`;
const entryMenu=c=>`<div class="rv-menu-wrap"><button type="button" class="rv-more" data-action="entry-menu" aria-label="코멘트 메뉴" aria-haspopup="menu" aria-expanded="false">${icon('more')}</button><div class="rv-menu" role="menu" aria-label="코멘트 메뉴" hidden><button type="button" role="menuitem" tabindex="-1" data-action="edit" data-id="${c.id}">코멘트 수정</button><button type="button" role="menuitem" tabindex="-1" data-action="toggle-vis" data-id="${c.id}">${c.visibility==='private'?'친구 공개로 바꾸기':'나만 보기로 바꾸기'}</button><a role="menuitem" tabindex="-1" href="#song/${c.song_id}">곡 보기</a><hr><button type="button" role="menuitem" tabindex="-1" class="danger" data-action="delete" data-id="${c.id}">삭제</button></div></div>`;
const entry=(c,s)=>`<article class="rv-entry" data-id="${c.id}">${dayMark(c.created_at)}<a class="rv-entry-cover" href="#song/${c.song_id}" tabindex="-1" aria-hidden="true">${cover(s,'xl')}</a><div class="rv-entry-body">
 <div class="rv-entry-top"><div class="rv-entry-song"><a class="rv-title" href="#song/${c.song_id}">${esc(s?.title||'곡 정보 없음')}</a><p class="rv-sub">${songLine(s)}</p></div>${entryMenu(c)}</div>
 <blockquote class="rv-lyric">${esc(c.quote)}</blockquote><p class="rv-reflection">${esc(c.text)}</p>
 <p class="rv-meta">${c.visibility==='private'?icon('lock')+'나만 보기':'친구 공개'}</p></div></article>`;
const bookmark=r=>`<button type="button" class="rv-bookmark" data-action="bookmark" data-id="${r.song_id}" aria-pressed="${Boolean(r.saved)}" aria-label="저장">${icon('bookmark')}</button>`;
const songRow=(r,s,count,size='md')=>`<div class="rv-row ${size}"><a href="#song/${r.song_id}" tabindex="-1" aria-hidden="true">${cover(s,size)}</a><div class="rv-row-body"><a class="rv-title" href="#song/${r.song_id}">${esc(s?.title||'곡 정보 없음')}</a><p class="rv-sub">${songLine(s)}</p><p class="rv-row-meta">${ratingOf(r)}<span>${count?`코멘트 ${count}`:'코멘트 없음'}</span></p></div>${bookmark(r)}</div>`;
const songTile=(href,s,title,sub,meta='')=>`<a class="rv-tile-link" href="${href}">${cover(s,'fill')}<span class="rv-tile-title">${esc(title)}</span><span class="rv-tile-sub">${esc(sub)}</span>${meta?`<span class="rv-tile-meta">${meta}</span>`:''}</a>`;
const recordTile=(r,s)=>songTile('#song/'+r.song_id,s,s?.title||'곡 정보 없음',s?.artist||'',ratingOf(r));
const emptyState=(title,text,cta=true)=>`<div class="rv-empty"><strong>${title}</strong><p>${text}</p>${cta?'<a class="rv-link" href="#home">음악 찾으러 가기</a>':''}</div>`;
function closeMenus(){document.querySelectorAll('.rv-more[aria-expanded="true"]').forEach(t=>{t.setAttribute('aria-expanded','false');t.nextElementSibling.hidden=true;});}

// 즐겨 듣는 앨범: 기록·저장·코멘트가 많은 앨범 3개. 결산이 아니라 바로가기입니다.
function favoriteAlbums(records,comments,songs){
 const albums=new Map();
 const add=id=>{const s=songs[id];if(!s?.album)return;const key=s.album+'\u0000'+s.artist,a=albums.get(key)||{s,score:0,order:albums.size};a.score++;if(!a.s.cover&&s.cover)a.s=s;albums.set(key,a);};
 records.filter(r=>r.recorded||r.saved).forEach(r=>add(r.song_id));comments.forEach(c=>add(c.song_id));
 return [...albums.values()].sort((a,b)=>b.score-a.score||a.order-b.order).slice(0,3);
}
async function account(){
 const seq=renderSeq;
 const [c,r,f]=await Promise.allSettled([commentSummary(),allRecords(),api('/friends')]);
 const comments=c.value,records=r.value,friends=f.value?.items;
 comments?.recent.sort((a,b)=>new Date(b.created_at)-new Date(a.created_at));
 const songs=await songMap([...(comments?.recent||[]).map(x=>x.song_id),...(records||[]).map(x=>x.song_id)]);
 const incoming=friends?.filter(x=>x.status==='incoming').length||0;
 if(seq!==renderSeq)return;// 기다리는 사이 다른 화면으로 이동했으면 그리지 않습니다.
 const albums=records?favoriteAlbums(records,comments?.recent||[],songs):[];
 const stats=[[comments?.total,'코멘트','#records/comments'],[records?.filter(x=>x.saved).length,'저장한 곡','#records/saved'],[records?.filter(x=>x.recorded).length,'기록한 음악','#records/recorded'],[friends?.filter(x=>x.status==='accepted').length,'친구','#friends']];
 main.innerHTML=`<div class="rv rv-account">
 <div class="rv-head"><h1>내 계정</h1></div>
 <div class="rv-layout rv-layout-account">
 <section class="rv-side-top" aria-label="프로필"><div class="rv-profile"><span class="rv-avatar" aria-hidden="true">${esc(initial(user.name))}</span><div class="rv-identity"><p class="rv-name">${esc(user.name)}</p><p class="rv-handle">@${esc(user.username)}</p></div></div>
  <nav class="rv-stats" aria-label="내 활동">${stats.map(([n,label,href])=>`<a href="${href}"><b>${n===undefined?'—':n}</b>${label}</a>`).join('')}</nav></section>
 <div class="rv-main rv-stack">
  ${albums.length?`<section aria-labelledby="fav-title">${sectionHead('fav-title','즐겨 듣는 앨범')}<div class="rv-grid cols-3">${albums.map(a=>songTile('#song/'+a.s.id,a.s,a.s.album,a.s.artist)).join('')}</div></section>`:''}
  <section aria-labelledby="recent-title">${sectionHead('recent-title','최근 코멘트',undefined,comments?.total?`<a class="rv-link" href="#records">전체 ${comments.total}</a>`:'')}
  ${comments===undefined?'<p class="rv-empty" role="alert">코멘트를 불러오지 못했어요. 새로고침해 주세요.</p>':comments.recent.map(x=>entry(x,songs[x.song_id])).join('')||emptyState('아직 남긴 코멘트가 없어요','마음에 닿은 가사 구절을 눌러 첫 감상을 남겨 보세요.')}</section>
 </div>
 <div class="rv-side-bottom"><div class="rv-settings">
   <button type="button" class="rv-setting-row" data-action="edit-name" aria-expanded="false" aria-controls="profile"><span>표시 이름</span><span class="rv-value">${esc(user.name)}</span>${icon('chevron')}</button>
   <form id="profile" class="rv-name-form" hidden><div class="rv-name-field"><input id="account-name" name="name" value="${esc(user.name)}" maxlength="40" autocomplete="nickname" aria-label="표시 이름" required><span class="rv-counter" id="account-name-count" aria-hidden="true">${Array.from(user.name).length}/40</span></div><div class="rv-form-actions"><button type="button" data-action="edit-name-cancel">취소</button><button type="submit" class="rv-save">저장</button></div></form>
   <a class="rv-setting-row" href="#friends" aria-label="받은 친구 요청 ${incoming}건"><span>받은 친구 요청</span><span class="rv-value${incoming?' accent':''}">${incoming?incoming+'건':'없음'}</span>${icon('chevron')}</a>
  </div><button type="button" class="rv-logout" data-action="logout">로그아웃</button></div>
 </div></div>`;
}
const RECORD_TABS=[['comments','코멘트'],['recorded','기록한 음악'],['saved','저장한 곡']];
const VIS_FILTERS=[['all','전체'],['friends','친구 공개'],['private','나만 보기']];
let recordsView=null;
async function recordsPage(tab){
 const seq=renderSeq,prev=document.querySelector('.rv-records')?recordsView:null;// 수정·삭제 후 다시 그릴 때 검색어와 공개 범위를 유지합니다.
 const [comments,recs]=await Promise.all([allPages('/comments'),allPages('/records')]);
 comments.sort((a,b)=>new Date(b.created_at)-new Date(a.created_at));// 날짜 여백과 월 묶음은 최신순을 전제로 합니다.
 const songs=await songMap([...comments.map(c=>c.song_id),...recs.map(r=>r.song_id)]);
 if(seq!==renderSeq)return;
 recordsView={tab:RECORD_TABS.some(([k])=>k===tab)?tab:'comments',q:prev?.q||'',vis:prev?.vis||'all',comments,recs,songs};
 main.innerHTML=`<div class="rv rv-records">
 <div class="rv-head"><h1>나의 기록</h1><label class="rv-search">${icon('search')}<input id="records-filter" type="search" placeholder="곡명, 가수, 가사, 코멘트 검색" aria-label="기록 검색" maxlength="100" autocomplete="off" value="${esc(recordsView.q)}"></label></div>
 <div class="rv-layout"><div class="rv-main">
  <div class="rv-toolbar"><div class="rv-seg" role="tablist" aria-label="기록 종류">${RECORD_TABS.map(([k,label])=>`<button type="button" class="records-tab" role="tab" id="tab-${k}" aria-controls="records-list" aria-selected="${k===recordsView.tab}" data-action="records-tab" data-id="${k}">${label}<span></span></button>`).join('')}</div><div id="records-subbar" class="rv-filters" role="group" aria-label="공개 범위"></div></div>
  <div id="records-list" class="rv-list" role="tabpanel" aria-labelledby="tab-${recordsView.tab}"></div>
 </div><aside class="rv-rail" id="records-rail" aria-label="다른 기록"></aside></div></div>`;
 paintRecords();
}
function paintRecords(){
 const v=recordsView,q=v.q.trim().toLowerCase(),has=(...xs)=>!q||xs.some(x=>String(x??'').toLowerCase().includes(q));
 const list=document.querySelector('#records-list'),sub=document.querySelector('#records-subbar'),rail=document.querySelector('#records-rail');
 if(!list)return;
 const recorded=v.recs.filter(r=>r.recorded),saved=v.recs.filter(r=>r.saved),counts={comments:v.comments.length,recorded:recorded.length,saved:saved.length};
 RECORD_TABS.forEach(([k])=>{const t=document.getElementById('tab-'+k);if(t)t.lastElementChild.textContent=counts[k];});
 const perSong={};v.comments.forEach(c=>perSong[c.song_id]=(perSong[c.song_id]||0)+1);
 const songText=id=>[v.songs[id]?.title,v.songs[id]?.artist,v.songs[id]?.album];
 list.setAttribute('aria-labelledby','tab-'+v.tab);
 sub.hidden=v.tab!=='comments';
 if(v.tab==='comments'){
  const visCount=k=>k==='all'?'':v.comments.filter(c=>c.visibility===k).length;
  sub.innerHTML=VIS_FILTERS.map(([k,l])=>`<button type="button" aria-pressed="${k===v.vis}" data-action="records-vis" data-id="${k}">${l}${k==='all'?'':`<span>${visCount(k)}</span>`}</button>`).join('');
  const items=v.comments.filter(c=>(v.vis==='all'||c.visibility===v.vis)&&has(c.quote,c.text,...songText(c.song_id)));
  const months=[];items.forEach(c=>{const m=monthLabel(c.created_at);if(months.at(-1)?.label!==m)months.push({label:m,items:[]});months.at(-1).items.push(c);});
  list.innerHTML=months.map(m=>`<section class="rv-month"><h2 class="rv-month-head">${m.label}<span>${m.items.length}개</span></h2>${m.items.map(c=>entry(c,v.songs[c.song_id])).join('')}</section>`).join('')||(v.comments.length?emptyState('찾는 코멘트가 없어요','검색어나 공개 범위를 바꿔 보세요.',false):emptyState('아직 남긴 코멘트가 없어요','마음에 닿은 가사 구절을 눌러 첫 감상을 남겨 보세요.'));
 }else if(v.tab==='recorded'){
  const items=recorded.filter(r=>has(...songText(r.song_id)));
  list.innerHTML=items.length?`<div class="rv-rows">${items.map(r=>songRow(r,v.songs[r.song_id],perSong[r.song_id],'lg')).join('')}</div>`:recorded.length?emptyState('찾는 곡이 없어요','다른 검색어로 찾아보세요.',false):emptyState('기록한 음악이 없어요','곡 화면에서 음악 기록을 추가하면 여기에 모여요.');
 }else{
  const items=saved.filter(r=>has(...songText(r.song_id)));
  list.innerHTML=items.length?`<div class="rv-grid cols-4 rv-list-grid">${items.map(r=>recordTile(r,v.songs[r.song_id])).join('')}</div>`:saved.length?emptyState('찾는 곡이 없어요','다른 검색어로 찾아보세요.',false):emptyState('저장한 곡이 없어요','곡 화면에서 저장하면 여기에 모여요.');
 }
 const more=k=>`<button type="button" class="rv-link" data-action="records-tab" data-id="${k}">모두 보기</button>`;
 const railRecorded=v.tab!=='recorded'&&recorded.length?`<section aria-labelledby="rail-recorded">${sectionHead('rail-recorded','기록한 음악',recorded.length,more('recorded'))}<div class="rv-rows">${recorded.slice(0,3).map(r=>songRow(r,v.songs[r.song_id],perSong[r.song_id])).join('')}</div></section>`:'';
 const railSaved=v.tab!=='saved'&&saved.length?`<section aria-labelledby="rail-saved">${sectionHead('rail-saved','저장한 곡',saved.length,more('saved'))}<div class="rv-grid">${saved.slice(0,4).map(r=>recordTile(r,v.songs[r.song_id])).join('')}</div></section>`:'';
 rail.innerHTML=railRecorded+railSaved;
 rail.hidden=!rail.innerHTML;
}
function nav(){
 const route=location.hash.slice(1).split('/')[0]||'home';
 const userButton=document.querySelector('.user-button'),onAccount=route==='account';
 document.querySelector('#profile-name').textContent=user?.name||'로그인';
 const avatar=userButton.querySelector('.avatar');
 avatar.className=user?`avatar ${orbClass(user.id)}`:'avatar mine';
 avatar.textContent=user?'':'나';
 userButton.setAttribute('aria-label',user?`내 계정: ${user.name}`:'로그인');
 userButton.classList.toggle('active',Boolean(user)&&onAccount);
 if(user&&onAccount)userButton.setAttribute('aria-current','page');else userButton.removeAttribute('aria-current');
 document.querySelector('#navigation').innerHTML=[['home','홈'],['friends','친구'],['ai','AI 추천'],['records','나의 기록']].map(([a,b])=>`<a class="nav-link${user&&a===route?' active':''}" href="#${a}"${user&&a===route?' aria-current="page"':''}>${b}</a>`).join('');}
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
let renderSeq=0;
async function render(){
 renderSeq++;nav();if(!user)return auth();const [route,id]=location.hash.slice(1).split('/');
 if(route==='song')await detail(id);
 else if(route==='account')await account();
 else if(route==='friends'){
  const r=await api('/friends'),feed=await api('/comments?scope=friends');
  main.innerHTML=`<h1>같은 음악, 다른 이야기.</h1><form id="users" class="search-box">${searchInput('이름 또는 아이디')}<button class="button dark">친구 검색</button></form><div id="results"></div><section class="panel"><h2>친구와 요청</h2>${r.items.map(x=>`<div class="person-row"><span>${esc(x.user.name)} @${esc(x.user.username)} · ${esc(x.status)}</span>${x.status==='incoming'?btn('수락','accept',x.user.id):''}${btn(x.status==='accepted'?'친구 해제':x.status==='incoming'?'거절':'요청 취소','remove',x.user.id)}${x.status==='accepted'?btn('기록 보기','friend-feed',x.user.id):''}</div>`).join('')||'아직 친구가 없습니다.'}</section><h2>공유 코멘트</h2>${feed.items.map(note).join('')||'공유된 코멘트 없음'}`;
 }else if(route==='records')await recordsPage(id);
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
  else if(action==='records-tab'&&recordsView){
   recordsView.tab=id;history.replaceState(null,'','#records/'+id);
   document.querySelectorAll('.records-tab').forEach(t=>t.setAttribute('aria-selected',String(t.dataset.id===id)));
   const fromRail=Boolean(b.closest('.rv-rail'));// 다시 그리면 레일의 버튼이 사라지므로 먼저 확인합니다.
   paintRecords();
   if(fromRail){document.querySelector('.rv-records')?.scrollIntoView({block:'start'});document.getElementById('tab-'+id)?.focus();}
  }
  else if(action==='entry-menu'){
   const open=b.getAttribute('aria-expanded')!=='true';closeMenus();
   b.setAttribute('aria-expanded',String(open));b.nextElementSibling.hidden=!open;
   if(open)b.nextElementSibling.querySelector('[role="menuitem"]')?.focus();
  }
  else if(action==='toggle-vis'){
   const c=await api('/comments/'+id),visibility=c.visibility==='private'?'friends':'private';
   await api('/comments/'+id,'PATCH',{text:c.text,visibility});
   const local=recordsView?.comments.find(x=>x.id===Number(id));
   if(local&&document.querySelector('.rv-records')){local.visibility=visibility;paintRecords();}else await render();
   document.querySelector(`.rv-entry[data-id="${id}"] .rv-more`)?.focus();
   toast(visibility==='friends'?'친구에게 공개했어요.':'나만 보기로 바꿨어요.');
  }
  else if(action==='bookmark'){
   const saved=b.getAttribute('aria-pressed')!=='true',songId=Number(id);
   await api('/records/'+songId,'PUT',{saved});
   const region=b.closest('.rv-rail')?'#records-rail':'#records-list';
   if(recordsView){const r=recordsView.recs.find(x=>x.song_id===songId);if(r)r.saved=saved;else recordsView.recs.push({song_id:songId,rating:null,saved,recorded:false});paintRecords();}
   (document.querySelector(`${region} [data-action="bookmark"][data-id="${songId}"]`)||document.querySelector('.rv-seg [aria-selected="true"]'))?.focus();
   toast(saved?'저장했어요.':'저장을 취소했어요.');
  }
  else if(action==='edit-name'||action==='edit-name-cancel'){
   const row=document.querySelector('[data-action="edit-name"]'),form=document.querySelector('#profile'),field=document.querySelector('#account-name');
   const open=action==='edit-name'&&row.getAttribute('aria-expanded')!=='true';
   row.setAttribute('aria-expanded',String(open));form.hidden=!open;
   if(open)field.focus();else{field.value=user.name;updateNameCount();row.focus();}
  }
  else if(action==='records-vis'&&recordsView){recordsView.vis=id;paintRecords();document.querySelector(`[data-action="records-vis"][data-id="${id}"]`)?.focus();}
  else if(action==='recommend')await api('/recommendations','POST',{});
 }catch(err){message(err);}finally{b.disabled=false;if(action==='import')b.textContent='가사와 기록 보기';if(b.closest('.rv-menu'))closeMenus();}
});
// 코멘트 '…' 메뉴: 바깥을 누르거나 Esc를 누르면 닫고, 위아래 화살표로 항목을 옮깁니다.
document.addEventListener('click',e=>{if(!e.target.closest('.rv-menu-wrap'))closeMenus();});
document.addEventListener('focusout',e=>{const wrap=e.target.closest?.('.rv-menu-wrap');if(wrap&&e.relatedTarget&&!wrap.contains(e.relatedTarget))closeMenus();});
document.addEventListener('keydown',e=>{
 const menu=e.target.closest?.('.rv-menu');
 if(e.key==='Escape'&&(menu||e.target.closest?.('.rv-menu-wrap'))){const trigger=e.target.closest('.rv-menu-wrap').querySelector('.rv-more');closeMenus();trigger.focus();}
 else if(menu&&(e.key==='ArrowDown'||e.key==='ArrowUp')){e.preventDefault();const items=[...menu.querySelectorAll('[role="menuitem"]')],i=items.indexOf(e.target);items[(i+(e.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();}
});
// 앨범 표지를 불러오지 못하면 같은 자리에 글자 타일을 놓고, 그 곡은 다시 요청하지 않습니다.
document.addEventListener('error',e=>{
 const img=e.target;if(!(img instanceof HTMLImageElement)||!img.classList.contains('rv-cover'))return;
 const s=songCache.get(Number(img.dataset.song));if(s)s.cover=null;
 const size=[...img.classList].find(c=>c!=='rv-cover')||'';
 img.outerHTML=coverTile(s||{title:'♪'},size);
},true);
const updateNameCount=()=>{const f=document.querySelector('#account-name'),n=document.querySelector('#account-name-count');if(f&&n)n.textContent=Array.from(f.value).length+'/40';};
document.addEventListener('input',e=>{if(e.target.id==='account-name')updateNameCount();});
document.addEventListener('submit',async e=>{
 e.preventDefault();const f=e.target,b=f.querySelector('button:not([type="button"])');if(!b||b.disabled)return;b.disabled=true;const data=Object.fromEntries(new FormData(f));
 try{
  if(f.id==='login'){const r=await api('/login','POST',data);user=r.user;csrf=r.csrf_token;await render();}
  else if(f.id==='register'){await api('/register','POST',data);auth();}
  else if(f.id==='profile'){user=(await api('/profile','PATCH',data)).user;await render();document.querySelector('[data-action="edit-name"]')?.focus();toast('이름을 저장했어요.');}
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
document.addEventListener('input',e=>{if(e.target.id==='records-filter'&&recordsView){recordsView.q=e.target.value;paintRecords();}});
document.addEventListener('input',e=>{if(e.target.id==='filter')document.querySelectorAll('#results article').forEach(a=>a.hidden=!a.textContent.toLowerCase().includes(e.target.value.toLowerCase()));});
window.addEventListener('hashchange',()=>render().catch(message));
(async()=>{try{const r=await api('/session');user=r.user;csrf=r.csrf_token;await render();}catch(err){main.textContent=err.message;}})();
