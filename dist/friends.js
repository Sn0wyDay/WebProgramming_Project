'use strict';
const Friends = (() => {
 let root, relations=[], selected='', query='', searchPage=1, feedPage=1, searchSeq=0, feedSeq=0, refreshSeq=0;
 let searchItems=[], searchPages=0, feedPages=0, busy=new Set(), refreshing=false;
 const active=()=>root?.isConnected && location.hash==='#friends' && !!user;
 const button=(text,action,id='')=>`<button type="button" data-friend="${action}" data-id="${esc(id)}">${text}</button>`;
 const empty=text=>`<p class="fr-empty">${text}</p>`;
 const status=text=>`<p class="fr-loading" role="status"><span class="fr-spinner" aria-hidden="true"></span>${text}</p>`;
 const avatar=u=>`<span class="fr-avatar" aria-hidden="true">${esc(Array.from(u.name)[0]||'♪')}</span>`;
 function actions(u){
  const state=relations.find(r=>r.user.id===u.id)?.status||u.status||'none';
  return state==='accepted'?`<a class="fr-profile-link" href="#friend/${u.id}">페이지 보기</a>`+button('친구 해제','confirm',u.id):state==='incoming'?button('수락','accept',u.id)+button('거절','remove',u.id):state==='outgoing'?button('요청 취소','remove',u.id):button('친구 요청','request',u.id);
 }
 const row=u=>`<div class="fr-person" data-person="${u.id}">${avatar(u)}<div class="fr-identity"><strong><a href="#friend/${u.id}">${esc(u.name)}</a></strong><span>@${esc(u.username)}</span></div><div class="fr-actions">${actions(u)}</div></div>`;
 function announce(text){const el=root.querySelector('#fr-notice');el.textContent=text;}
 function reconcile(target, users){
  const old=new Map([...target.querySelectorAll(':scope > [data-person]')].map(n=>[Number(n.dataset.person),n]));
  target.querySelectorAll(':scope > .fr-empty, :scope > .fr-loading').forEach(n=>n.remove());
  for(const u of users){const prev=old.get(u.id),template=document.createElement('template');template.innerHTML=row(u);const next=template.content.firstElementChild;
   if(prev){if(prev.outerHTML!==next.outerHTML)prev.replaceWith(next);old.delete(u.id);}else target.append(next);
  }
  old.forEach(n=>n.remove());
  if(!users.length)target.innerHTML=empty('아직 없어요. 이름이나 아이디로 친구를 찾아보세요.');
 }
 const sleeve=u=>`<a class="fr-vinyl-profile" href="#friend/${u.id}" aria-label="${esc(u.name)}님의 홈으로 이동"><span class="fr-disc-wrap"><span class="fr-disc tone-${u.id%4}" aria-hidden="true"><span class="fr-disc-rim">RE:VERSE · PERSONAL RECORD COLLECTION · 33⅓ RPM</span><span class="fr-disc-label"><small>SIDE A / RE:VERSE</small><strong>${esc(u.name)}</strong><span>MY MUSIC ROOM</span></span><span class="fr-disc-hole"></span></span></span><span class="fr-profile-caption"><strong>${esc(u.name)}</strong><small>@${esc(u.username)}</small></span></a>`;
 function lists(){
  for(const state of ['incoming','outgoing']){
   const items=relations.filter(r=>r.status===state).map(r=>r.user);
   root.querySelector(`[data-count="${state}"]`).textContent=items.length;
   reconcile(root.querySelector('#fr-'+state),items);
  }
  const friends=relations.filter(r=>r.status==='accepted');
  root.querySelector('[data-count="accepted"]').textContent=friends.length;
  const shelf=root.querySelector('#fr-shelf');
  const html=friends.length?friends.map(r=>`<div class="fr-shelf-item">${sleeve(r.user)}<div class="fr-shelf-tools">${button('친구 해제','confirm',r.user.id)}</div></div>`).join(''):empty('아직 친구가 없어요. 친구를 찾아 음악을 함께 나눠보세요.');
  if(shelf.innerHTML!==html)shelf.innerHTML=html;
  reconcile(root.querySelector('#fr-search-list'),searchItems);
  if(!query)root.querySelector('#fr-search-list').innerHTML=empty('이름 또는 아이디를 입력해 친구를 찾아보세요.');
 }
 async function refresh(){
  const seq=++refreshSeq,owner=root;
  const data=await api('/friends');if(!active()||owner!==root||seq!==refreshSeq)return;
  relations=data.items;
  if(selected&&!relations.some(r=>String(r.user.id)===selected&&r.status==='accepted'))selected='';
  // Search states are server snapshots; replace them when relationships change.
  searchItems=searchItems.map(u=>({...u,status:relations.find(r=>r.user.id===u.id)?.status||'none'}));
  lists();
 }
 async function search(page=1){
  const seq=++searchSeq,owner=root,target=root.querySelector('#fr-search-list'),pager=root.querySelector('#fr-search-pages');
  if(page===1){searchItems=[];target.innerHTML=status('친구를 찾고 있어요');}pager.replaceChildren();
  if(!query){target.innerHTML=empty('이름 또는 아이디를 입력해 친구를 찾아보세요.');return;}
  try{const data=await api('/users?q='+encodeURIComponent(query)+'&page='+page);
   if(!active()||root!==owner||seq!==searchSeq)return;
   searchPage=page;searchPages=data.pages;searchItems=page===1?data.items:[...searchItems,...data.items];
   reconcile(target,searchItems);if(!searchItems.length)target.innerHTML=empty('일치하는 사용자가 없어요. 다른 이름으로 찾아보세요.');
   pager.innerHTML=page<searchPages?button('검색 결과 더 보기','search-more'):'';
  }catch(e){if(active()&&root===owner&&seq===searchSeq){target.innerHTML=`<p role="alert">${esc(e.message)}</p>${button('다시 검색','search-retry')}`;}}
 }
 const record=(c,i)=>`<article class="fr-track"><div class="fr-track-number" aria-hidden="true">${String(i+1).padStart(2,'0')}</div><div class="fr-track-body"><a class="fr-song" href="#song/${c.song_id}">${esc(c.song_title)}</a><p class="fr-artist">${esc(c.song_artist)}</p><blockquote>${esc(c.quote)}</blockquote><p class="fr-thought">${esc(c.text)}</p><footer>${esc(c.user.name)} <span>@${esc(c.user.username)}</span><time datetime="${esc(c.created_at)}">${esc(new Date(c.created_at).toLocaleDateString('ko-KR'))}</time></footer></div></article>`;
 async function feed(page=1){
  const seq=++feedSeq,owner=root,target=root.querySelector('#fr-feed'),pager=root.querySelector('#fr-feed-pages');
  const name=relations.find(r=>String(r.user.id)===selected)?.user.name;
  root.querySelector('#fr-feed-title').textContent=name?name+'님의 음악 기록':'친구들의 음악 기록';
  root.querySelectorAll('[data-friend="select"]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===selected)));
  if(page===1)target.innerHTML=status('공유한 감상을 불러오는 중');pager.replaceChildren();
  try{const data=await api('/comments?scope=friends&page='+page+(selected?'&user_id='+selected:''));
   if(!active()||root!==owner||seq!==feedSeq)return;
   const count=page===1?0:target.querySelectorAll('article').length;
   if(page===1)target.replaceChildren();
   target.insertAdjacentHTML('beforeend',data.items.map(c=>`<a class="fr-share-notification" href="#shared/${c.id}"><span class="fr-notification-dot" aria-hidden="true"></span><span><strong>${esc(c.user.name)}님이 기록을 공유했어요</strong><small>${esc(c.song_title)} · ${esc(c.song_artist)}</small><time datetime="${esc(c.created_at)}">${esc(new Date(c.created_at).toLocaleDateString('ko-KR'))}</time></span><span aria-hidden="true">↗</span></a>`).join(''));
   if(!target.children.length)target.innerHTML=empty('아직 공유한 감상이 없어요. 친구가 공개한 기록이 이곳에 쌓입니다.');
   feedPage=page;feedPages=data.pages;pager.innerHTML=page<feedPages?button('감상 더 보기','feed-more'):'';
  }catch(e){if(active()&&root===owner&&seq===feedSeq){if(page===1)target.replaceChildren();pager.innerHTML=`<p role="alert">${esc(e.message)}</p>${button('다시 불러오기','feed-retry',page)}`;}}
 }
 async function removeAnimation(row){
  if(!row||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const a=row.animate([{height:row.offsetHeight+'px',opacity:1,overflow:'hidden'},{height:0,opacity:0,overflow:'hidden',paddingTop:0,paddingBottom:0}],{duration:220,easing:'ease-out',fill:'forwards'});
  try{await a.finished;}catch{} a.cancel();
 }
 function confirm(id,trigger){
  const person=relations.find(r=>String(r.user.id)===id)?.user;if(!person)return;
  const dialog=document.createElement('dialog');dialog.className='fr-dialog';dialog.setAttribute('aria-labelledby','fr-confirm-title');
  dialog.innerHTML=`<h2 id="fr-confirm-title">${esc(person.name)}님과 친구를 해제할까요?</h2><p>서로의 친구 공개 감상을 볼 수 없게 됩니다.</p><div>${button('취소','cancel-dialog')}${button('친구 해제','confirm-remove',id)}</div><p class="fr-dialog-error" role="alert"></p>`;
  root.append(dialog);dialog.addEventListener('close',()=>{dialog.remove();if(trigger.isConnected)trigger.focus();else root.querySelector('[data-friend=sidebar]').focus();},{once:true});dialog.showModal();dialog.querySelector('button').focus();
 }
 async function click(e){
  const b=e.target.closest('[data-friend]');if(!b||!active())return;
  const {friend:action,id}=b.dataset;
  if(b.disabled)return;
  if(action==='sidebar'){
   const collapsed=root.classList.toggle('fr-sidebar-collapsed');
   b.setAttribute('aria-expanded',String(!collapsed));
   b.setAttribute('aria-label',collapsed?'사이드바 펼치기':'사이드바 접기');
   b.innerHTML=collapsed?'☰ <span>친구 찾기</span>':'‹ <span>접기</span>';
   root.querySelector('.fr-library').inert=collapsed;
   return;
  }
  if(action==='cancel-dialog'){b.closest('dialog').close();return;}
  if(action==='confirm'){confirm(id,b);return;}
  if(action==='select'){selected=id;await feed();return;}
  if(action==='search-more'||action==='search-retry'){b.disabled=true;await search(action==='search-more'?searchPage+1:1);if(b.isConnected)b.disabled=false;return;}
  if(action==='feed-more'||action==='feed-retry'){b.disabled=true;await feed(action==='feed-more'?feedPage+1:Number(id)||1);if(b.isConnected)b.disabled=false;return;}
  if(!['request','accept','remove','confirm-remove'].includes(action)||busy.has(id))return;
  busy.add(id);const label=b.textContent;const owner=root;
  root.querySelectorAll(`[data-id="${id}"]`).forEach(n=>n.disabled=true);b.innerHTML='<span class="fr-spinner" aria-hidden="true"></span>처리 중';b.setAttribute('aria-busy','true');
  let success=false;
  try{
   await api('/friends/'+id,action==='request'?'POST':action==='accept'?'PATCH':'DELETE');success=true;
   if(root!==owner||!active())return;
   const dialog=b.closest('dialog');if(dialog)dialog.close();
   // Clear cached shared text immediately after server-confirmed relationship changes.
   ++feedSeq;root.querySelector('#fr-feed').replaceChildren();
   if(action!=='request')await removeAnimation(b.closest('[data-person]'));
   const focusId=id;await refresh();await feed();
   if(query)await search(1);
   announce(action==='accept'?'친구가 되었어요. 음악 기록을 함께 살펴보세요.':action==='request'?'친구 요청을 보냈어요.':'친구 관계를 변경했어요.');
   (root.querySelector(`[data-person="${focusId}"] button`)||root.querySelector('#fr-query')).focus({preventScroll:true});
  }catch(e){
   if(root!==owner||!active())return;
   announce((success?'관계는 변경됐지만 목록을 갱신하지 못했어요. ':e.message+' '));
   const error=b.closest('dialog')?.querySelector('.fr-dialog-error');if(error)error.textContent=e.message;
   // A conflicting request may have changed server permissions: discard old feed.
   ++feedSeq;root.querySelector('#fr-feed').replaceChildren();
   try{await refresh();await feed();}catch{root.querySelector('#fr-feed-pages').innerHTML=button('다시 불러오기','feed-retry',1);}
  }finally{busy.delete(id);if(root===owner){root.querySelectorAll(`[data-id="${id}"]`).forEach(n=>n.disabled=false);}if(b.isConnected){b.textContent=label;b.removeAttribute('aria-busy');}}
 }
 async function mount(){
  ++searchSeq;++feedSeq;++refreshSeq;selected='';query='';searchItems=[];relations=[];
  main.innerHTML=`<section class="friends-room"><div id="fr-notice" role="status" aria-live="polite"></div><div class="fr-sidebar-toolbar"><button type="button" data-friend="sidebar" aria-controls="fr-sidebar" aria-expanded="true" aria-label="사이드바 접기">‹ <span>접기</span></button></div><div class="fr-layout"><aside class="fr-library" id="fr-sidebar"><form id="fr-search"><label for="fr-query">친구 찾기</label><div><input id="fr-query" name="q" type="search" maxlength="100" placeholder="이름 또는 아이디" autocomplete="off"><button>검색</button></div></form><div id="fr-search-list">${empty('이름 또는 아이디로 친구를 찾아보세요.')}</div><div id="fr-search-pages"></div>${[['incoming','받은 요청'],['outgoing','보낸 요청']].map(([key,title])=>`<section class="fr-group"><h2>${title}<span data-count="${key}">0</span></h2><div id="fr-${key}">${status('목록을 불러오는 중')}</div></section>`).join('')}<section class="fr-group fr-notifications"><h2 id="fr-feed-title">친구들의 음악 기록</h2><div id="fr-feed" aria-live="polite"></div><div id="fr-feed-pages"></div></section></aside><section class="fr-records fr-collection" aria-labelledby="fr-shelf-title"><header><div><h2 id="fr-shelf-title">내 친구 <span data-count="accepted">0</span></h2></div></header><div id="fr-shelf" class="fr-shelf"></div></section></div></section>`;
  root=main.querySelector('.friends-room');root.addEventListener('click',click);
  root.querySelector('#fr-search').addEventListener('submit',e=>{e.preventDefault();e.stopPropagation();query=new FormData(e.target).get('q').trim();search(1);});
  try{await refresh();if(active())await feed();}catch(e){if(active()){announce(e.message);root.querySelectorAll('.fr-loading').forEach(n=>n.replaceWith(Object.assign(document.createElement('p'),{textContent:'목록을 불러오지 못했어요. 다시 시도해 주세요.'})));root.querySelector('#fr-feed-pages').innerHTML=button('다시 불러오기','refresh');}}
 }
 async function sync(){if(!active()||refreshing||busy.size)return;refreshing=true;++feedSeq;root.querySelector('#fr-feed').replaceChildren();try{await refresh();if(active())await feed();}catch(e){if(active())announce(e.message);}finally{refreshing=false;}}
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&active()){++feedSeq;root.querySelector('#fr-feed').replaceChildren();}else sync();});
 window.addEventListener('focus',sync);
 document.addEventListener('click',e=>{if(e.target.closest('[data-friend="refresh"]'))sync();});
 let profileSeq=0;
 async function profile(id){
  const seq=++profileSeq, route=location.hash;
  main.innerHTML='<section class="friends-room fr-profile"><a href="#friends" class="fr-back">← 친구 목록</a><div id="fr-profile-content" aria-live="polite">'+status('친구의 페이지를 불러오는 중')+'</div></section>';
  const target=main.querySelector('#fr-profile-content');let nextPage=1;
  async function load(page){
   const data=await api('/friends/'+Number(id)+'/profile?page='+page);
   if(seq!==profileSeq||location.hash!==route||!target.isConnected)return;
   if(page===1){
    const s=data.featured_song;
    target.innerHTML=`<header class="fr-profile-hero">${avatar(data.user)}<div><p>FRIEND'S MUSIC ROOM</p><h1>${esc(data.user.name)}</h1><span>@${esc(data.user.username)}</span></div></header><section class="fr-featured"><p class="fr-section-label">대표 음악</p>${s?`<a class="fr-featured-song" href="#song/${s.id}"><span class="fr-sleeve" aria-hidden="true">RE:<br>VERSE</span><span><strong>${esc(s.title)}</strong><small>${esc(s.artist)}</small></span><span aria-hidden="true">↗</span></a>`:empty('아직 대표 음악이 없어요.')}</section><section><header class="fr-profile-tabs"><h2>공개 감상 <span>${data.public_count}</span></h2><p>친구에게 공개한 기록만 보여요.</p></header><div id="fr-profile-notes"></div><div id="fr-profile-more"></div></section>`;
   }
   const notes=target.querySelector('#fr-profile-notes');
   notes.insertAdjacentHTML('beforeend',data.items.map((c,i)=>record(c,(page-1)*20+i)).join(''));
   if(page===1&&!data.items.length)notes.innerHTML=empty('아직 공개한 감상이 없어요. 대표 음악을 먼저 만나보세요.');
   nextPage=page+1;target.querySelector('#fr-profile-more').innerHTML=page<data.pages?'<button type="button" class="fr-more">감상 더 보기</button>':'';
  }
  target.addEventListener('click',async e=>{
   const b=e.target.closest('.fr-more');if(!b||b.disabled)return;b.disabled=true;b.textContent='불러오는 중…';
   try{await load(nextPage);}catch(err){b.disabled=false;b.textContent='다시 불러오기';target.querySelector('#fr-profile-error').textContent=err.message;}
  });
  try{await load(1);if(target.isConnected)target.insertAdjacentHTML('beforeend','<p id="fr-profile-error" role="alert"></p>');}
  catch(e){if(target.isConnected){target.innerHTML=`<p role="alert">${esc(e.message)} 친구 관계를 확인하고 다시 열어주세요.</p><a href="#friends">친구 목록으로</a>`;}}
 }
 // Discard shared records when leaving the tab; revalidate access on return.
 document.addEventListener('visibilitychange',()=>{if(location.hash.startsWith('#friend/')){if(document.hidden)main.querySelector('#fr-profile-content')?.replaceChildren();else profile(location.hash.split('/')[1]);}});
 window.addEventListener('focus',()=>{if(location.hash.startsWith('#friend/')&&user)profile(location.hash.split('/')[1]);});
 async function shared(id){
  const route=location.hash;
  main.innerHTML=`<section class="friends-room fr-profile"><a class="fr-back" href="#friends">← 친구 목록</a><div id="fr-shared-content" aria-live="polite">${status('공유한 기록을 불러오는 중')}</div></section>`;
  const target=main.querySelector('#fr-shared-content');
  try{const c=await api('/comments/'+Number(id));if(!target.isConnected||location.hash!==route)return;
   target.innerHTML=`<header class="fr-shared-heading"><p>SHARED LINER NOTE</p><h1>${esc(c.user.name)}님이 공유한 기록</h1><a href="#friend/${c.user.id}">친구 홈으로 ↗</a></header>${record(c,0)}`;
  }catch(e){if(target.isConnected)target.innerHTML=`<p role="alert">${esc(e.message)} 친구 관계나 공개 범위가 변경되었을 수 있어요.</p><a href="#friends">친구 목록으로 돌아가기</a>`;}
 }
 document.addEventListener('visibilitychange',()=>{if(location.hash.startsWith('#shared/')){if(document.hidden)main.querySelector('#fr-shared-content')?.replaceChildren();else shared(location.hash.split('/')[1]);}});
 window.addEventListener('focus',()=>{if(location.hash.startsWith('#shared/')&&user)shared(location.hash.split('/')[1]);});
 return {mount,profile,shared};
})();
