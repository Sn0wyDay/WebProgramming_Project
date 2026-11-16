'use strict';
const main=document.querySelector('#main'),modal=document.querySelector('#modal');
let user,csrf;
async function api(path,method='GET',data){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
 try{
  const r=await fetch('/api'+path,{method,signal:controller.signal,headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:data===undefined?undefined:JSON.stringify(data)});
  const j=await r.json();
  if(!r.ok){if(r.status===401){user=null;auth();}const error=Error(j.error||'요청 실패');error.code=j.code;error.retry_after=j.retry_after||0;throw error;}
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

const note=c=>`<article class="saved-note"><strong>${esc(c.user.name)}</strong><time> · ${esc(new Date(c.created_at).toLocaleString('ko-KR'))}</time><span class="pill">${c.visibility==='private'?'나만 보기':'친구 공개'}</span><blockquote>${esc(c.quote)}</blockquote><p>${esc(c.text)}</p><a href="#song/${c.song_id}">곡 보기</a>${c.user.id===user.id?btn('수정','edit',c.id)+btn('삭제','delete',c.id):''}</article>`;
function nav(){document.querySelector('#profile-name').textContent=user?.name||'로그인';document.querySelector('#navigation').innerHTML=[['home','홈','explore'],['friends','친구','friends'],['ai','AI 추천','spark'],['records','나의 기록','note']].map(([a,b,i])=>`<a class="nav-link ${location.hash==='#'+a||(!location.hash&&a==='home')?'active':''}" href="#${a}">${icon(i)}<span>${b}</span></a>`).join('');}
async function render(){
 nav();if(!user)return auth();const [route,id]=location.hash.slice(1).split('/');
 REHome.leave();
 if(route==='song')await REHome.renderSong(Number(id));
 else if(route==='friends'){
  const r=await api('/friends'),feed=await api('/comments?scope=friends');
  main.innerHTML=`<h1>같은 음악, 다른 이야기.</h1><form id="users" class="search-box">${searchInput('이름 또는 아이디')}<button class="button dark">친구 검색</button></form><div id="results"></div><section class="panel"><h2>친구와 요청</h2>${r.items.map(x=>`<div class="person-row"><span>${esc(x.user.name)} @${esc(x.user.username)} · ${esc(x.status)}</span>${x.status==='incoming'?btn('수락','accept',x.user.id):''}${btn(x.status==='accepted'?'친구 해제':x.status==='incoming'?'거절':'요청 취소','remove',x.user.id)}${x.status==='accepted'?btn('기록 보기','friend-feed',x.user.id):''}</div>`).join('')||'아직 친구가 없습니다.'}</section><h2>공유 코멘트</h2>${feed.items.map(note).join('')||'공유된 코멘트 없음'}`;
 }else if(route==='records')main.innerHTML=`<h1>나의 기록</h1>${btn('코멘트','notes')}${btn('기록한 음악','recorded')}${btn('저장한 곡','saved')}<input class="field" id="filter" placeholder="현재 목록 검색"><div id="results">${(await api('/comments')).items.map(note).join('')}</div>`;
 else if(route==='ai')main.innerHTML=`<h1>당신의 취향에 이어지는 음악.</h1><section class="recommend-top"><p>Gemini 설정 보류 · 실제 AI 연동 미검증</p>${btn('추천받기','recommend')}</section>`;
 else await REHome.renderHome();
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-action]');if(!b)return;e.preventDefault();if(b.disabled)return;b.disabled=true;const {action,id}=b.dataset;
 try{
  if(action==='close')modal.close();
  else if(action==='register'||action==='login')auth(action==='register');
  else if(action==='profile'){if(!user)return auth();show('프로필 수정',`<form id="profile">${input('name','표시 이름')}<button class="button dark">저장</button></form>${btn('로그아웃','logout')}`);}
  else if(action==='logout'){await api('/logout','POST');user=null;modal.close();await render();}
  else if(action==='about')show('서비스 안내','<p>좋아하는 음악을 찾고, 가사 구절에 감상을 남겨 보세요. 곡마다 가사와 앨범 표지의 제공 여부가 다를 수 있습니다.</p>');
  else if(action==='edit'){const c=await api('/comments/'+id);show('코멘트 수정',`<form id="edit" data-id="${id}"><textarea class="textarea" name="text" maxlength="2000" required>${esc(c.text)}</textarea><select class="select" name="visibility"><option value="private" ${c.visibility==='private'?'selected':''}>나만 보기</option><option value="friends" ${c.visibility==='friends'?'selected':''}>친구 공개</option></select><button class="button dark">저장</button></form>`);}
  else if(action==='delete')show('삭제할까요?',`<p>삭제한 코멘트는 복구할 수 없습니다.</p>${btn('삭제','confirm-delete',id)}`);
  else if(action==='confirm-delete'){await api('/comments/'+id,'DELETE');modal.close();await render();}
  else if(action==='request'){await api('/friends/'+id,'POST');await render();}
  else if(action==='accept'||action==='remove'){await api('/friends/'+id,action==='accept'?'PATCH':'DELETE');await render();}
  else if(action==='friend-feed')show('친구의 기록',(await api('/comments?scope=friends&user_id='+id)).items.map(note).join('')||'공유 기록 없음');
  else if(action==='notes')document.querySelector('#results').innerHTML=(await api('/comments')).items.map(note).join('');
  else if(action==='saved'||action==='recorded'){const r=await api('/records');const s=await Promise.all(r.items.filter(x=>x[action]).map(x=>api('/songs/'+x.song_id)));document.querySelector('#results').innerHTML=s.map(card).join('')||'기록 없음';}
  else if(action==='recommend')await api('/recommendations','POST',{});
 }catch(err){message(err);}finally{b.disabled=false;}
});
document.addEventListener('submit',async e=>{
 const f=e.target;if(f.matches('[data-home-form]'))return;e.preventDefault();const b=f.querySelector('button');if(!b||b.disabled)return;b.disabled=true;const data=Object.fromEntries(new FormData(f));
 try{
  if(f.id==='login'){const r=await api('/login','POST',data);user=r.user;csrf=r.csrf_token;await render();}
  else if(f.id==='register'){await api('/register','POST',data);auth();}
  else if(f.id==='profile'){user=(await api('/profile','PATCH',data)).user;modal.close();await render();}
  else if(f.id==='users')document.querySelector('#results').innerHTML=(await api('/users?q='+encodeURIComponent(data.q))).items.map(u=>`<div class="person-row">${esc(u.name)} @${esc(u.username)} ${btn('친구 요청','request',u.id)}</div>`).join('')||'검색 결과 없음';
  else if(f.id==='edit'){await api('/comments/'+f.dataset.id,'PATCH',data);modal.close();await render();}
 }catch(err){message(err);}finally{b.disabled=false;}
});
document.addEventListener('input',e=>{if(e.target.id==='filter')document.querySelectorAll('#results article').forEach(a=>a.hidden=!a.textContent.toLowerCase().includes(e.target.value.toLowerCase()));});
REHome.configure({api,getUser:()=>user});
window.addEventListener('hashchange',()=>render().catch(message));
(async()=>{try{const r=await api('/session');user=r.user;csrf=r.csrf_token;await render();}catch(err){main.textContent=err.message;}})();
