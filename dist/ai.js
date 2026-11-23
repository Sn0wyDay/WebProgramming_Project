'use strict';

// Each visit owns its view and its responses. Leaving the report discards its personal data.
async function mountReport() {
  const view = document.createElement('div');
  view.className = 'music-report';
  view.innerHTML = '<h1>AI 리포트</h1><p role="status">내 음악 기록을 불러오는 중…</p>';
  main.replaceChildren(view);
  const owner = user.id;
  const active = () => view.isConnected && user?.id === owner && location.hash === '#ai';
  const chapters = [
    ['ai-top', '나의 TOP 5', '내가 가장 높은 별점을 준 음악', 'dark'],
    ['ai-talked', '많이 이야기한 아티스트', '가장 많은 이야기를 남긴 아티스트', 'soft'],
    ['ai-overall', '종합 추천', '당신의 기록을 종합한 오늘의 추천', 'paper'],
    ['ai-similar', '비슷한 음악', '오늘은 어떤 장르가 끌리나요?', 'plain'],
  ];
  const genres = ['인디 팝', '인디 록', 'R&B', '팝', '힙합', '재즈', '포크', '일렉트로닉'];
  const art = s => esc(s.cover || 'assets/album-placeholder.svg');
  const songLink = s => '<a class="ai-detail-link" href="#song/' + s.id + '">' + esc(s.title) + ' · ' + esc(s.artist) + icon('chevron') + '</a>';
  const recsByArtist = new Map();
  const candidates = new Map();
  let profileSeed;
  let seeds;

  async function load() {
    const [records, notes] = await Promise.all([allRecords(), allPages('/comments')]);
    const owned = records.filter(r => r.saved || r.recorded || r.rating);
    const ids = [...new Set([...owned.map(r => r.song_id), ...notes.map(n => n.song_id)])];
    const songs = await songMap(ids);
    if (ids.some(id => !songs[id])) throw Error('일부 곡 정보를 불러오지 못했어요.');
    const rated = owned.filter(r => r.rating).sort((a,b) => b.rating-a.rating || a.song_id-b.song_id);
    const artists = new Map(), counts = new Map();
    for (const n of notes) {
      const s = songs[n.song_id];
      counts.set(s.id, (counts.get(s.id) || 0) + 1);
      if (!artists.has(s.artist)) artists.set(s.artist, {song:s, count:0, latest:n.text});
      artists.get(s.artist).count++;
    }
    const points = new Map(owned.map(r => [r.song_id, (r.rating || 0) + Number(r.saved) + Number(r.recorded)]));
    profileSeed = ids.map(id => songs[id]).sort((a,b) =>
      ((points.get(b.id) || 0) + (counts.get(b.id) || 0)) - ((points.get(a.id) || 0) + (counts.get(a.id) || 0)))[0];
    seeds = ids.map(id => songs[id]);
    if (!seeds.length) seeds = (await api('/songs')).items;
    if (!active()) return;
    const top = rated.slice(0,5).map(r => ({...songs[r.song_id],rating:r.rating}));
    const [first,...others] = top;
    const topHtml = first ? `<div class="ai-top-grid">
      <a class="ai-top-hero" href="#song/${first.id}"><span class="ai-rank-big">No.1</span><img src="${art(first)}" alt=""><span class="ai-top-hero-text"><strong>${esc(first.title)}</strong><small>${esc(first.artist)} · ★ ${first.rating}</small></span></a>
      <ol class="ai-top-list">${others.map((s,i)=>`<li><a class="ai-top-row" href="#song/${s.id}"><span class="ai-rank">${i+2}</span><img src="${art(s)}" alt=""><span class="ai-top-text"><strong>${esc(s.title)}</strong><small>${esc(s.artist)} · ★ ${s.rating}</small></span></a></li>`).join('')}</ol></div>` : '<p>곡에 별점을 남기면 여기에 모여요.</p>';
    const talked = [...artists.values()].sort((a,b)=>b.count-a.count).slice(0,3);
    const talkedHtml = talked.length ? `<div class="ai-talked-grid">${talked.map(({song:s,count,latest},i) => {
      recsByArtist.set(s.artist, seeds.filter(x=>x.artist===s.artist));
      return `<button class="ai-talked-card" data-report-artist="${esc(s.artist)}"><span class="ai-talked-rank">${i+1}</span><img src="${art(s)}" alt=""><strong>${esc(s.artist)}</strong><span class="ai-talked-count"><b>${count}</b>개의 코멘트</span><span class="ai-talked-quote">${esc(latest)}</span></button>`;
    }).join('')}</div>` : '<p>가사에 첫 감상을 남기면 아티스트별로 모아 볼 수 있어요.</p>';
    const overallHtml = profileSeed ? `<p>별점·저장·기록·코멘트를 합산해 고른 곡은 ‘${esc(profileSeed.title)}’입니다. 이 아티스트의 다른 음악을 찾아보세요.</p><button class="button dark" data-find="overall">음악 찾기</button>` : '<p>곡을 저장하거나 감상을 남기면 내 기록에서 추천 기준을 찾아요.</p>';
    const similarHtml = seeds.length ? `<div class="recommend-top"><label class="form-label">좋아하는 곡<select class="field" id="ai-seed">${seeds.map(s=>`<option value="${s.id}">${esc(s.title)} · ${esc(s.artist)}</option>`).join('')}</select></label>
      <label class="form-label">듣고 싶은 장르<select class="field" id="ai-genre">${genres.map(g=>`<option>${esc(g)}</option>`).join('')}</select></label><button class="button dark" data-find="similar">음악 추천받기</button></div>` : '<a class="button outline" href="#home">홈에서 음악 찾기</a>';
    const bodies = [topHtml,talkedHtml,overallHtml,similarHtml];
    view.innerHTML = `<header><h1>AI 리포트</h1><p>내 음악 기록과 장르를 기준으로 찾는 카탈로그 추천입니다. Gemini 추천은 설정 대기 중입니다.</p></header>
      <nav class="ai-chapters" aria-label="리포트 목차">${chapters.map(([id,label],i)=>`<button class="ai-chapter" data-chapter="${id}"><span>0${i+1}</span>${label}</button>`).join('')}</nav>
      <div class="ai-story">${chapters.map(([id,,title,tone],i)=>`<section id="${id}" class="ai-slide ai-slide-${tone} is-in"><div class="ai-slide-head"><h2>${title}</h2></div>${bodies[i]}${i>=2?'<div class="ai-results" aria-live="polite"></div>':''}</section>`).join('')}</div>`;
  }

  function candidateButton(s) {
    return `<button class="ai-detail-link" data-report-song="${esc(s.external_id)}">${esc(s.title)} · ${esc(s.artist)} ${icon('chevron')}</button>`;
  }

  async function discover(button) {
    const section = button.closest('section'), results = section.querySelector('.ai-results');
    const similar = button.dataset.find === 'similar';
    const seed = similar ? seeds.find(s=>String(s.id)===view.querySelector('#ai-seed').value) : profileSeed;
    const genre = similar ? view.querySelector('#ai-genre').value : '';
    const params = new URLSearchParams({seed:seed.id,genre});
    results.textContent = '음악을 찾는 중…';
    try {
      const {items} = await api('/report/discovery?' + params);
      if (!active()) return;
      const groups = new Map();
      for (const item of items) {
        candidates.set(item.external_id,item);
        if (!groups.has(item.artist)) groups.set(item.artist,[]);
        groups.get(item.artist).push(item);
        const known = recsByArtist.get(item.artist) || [];
        if (!known.some(s=>s.external_id===item.external_id)) recsByArtist.set(item.artist,[...known,item]);
      }
      if (!items.length) {results.textContent='조건에 맞는 다른 곡을 찾지 못했어요.';return;}
      results.innerHTML = `<p>${esc(seed.artist)}${genre?' · '+esc(genre):''} 기준 검색 결과</p><div class="ai-result-columns"><section><h3>노래</h3>${items.slice(0,3).map(candidateButton).join('')}</section>
        <section><h3>아티스트</h3>${[...groups.keys()].slice(0,3).map(name=>`<button class="ai-detail-link" data-report-artist="${esc(name)}">${esc(name)} ${icon('chevron')}</button>`).join('')}</section></div>`;
    } catch(error) {if(active()) results.textContent=error.message;}
  }

  view.addEventListener('click', async event => {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    if (button.dataset.chapter) {
      document.getElementById(button.dataset.chapter)?.scrollIntoView({block:'start'});
      return;
    }
    if (button.dataset.reportArtist) {
      const artist = button.dataset.reportArtist;
      const panel = view.querySelector('dialog');
      panel.querySelector('h2').textContent=artist;
      panel.querySelector('.ai-artist-songs').innerHTML=(recsByArtist.get(artist)||[]).map(s=>s.id?songLink(s):candidateButton(s)).join('');
      panel.showModal();
      return;
    }
    button.disabled=true;
    try {
      if (button.dataset.find) await discover(button);
      else if (button.dataset.reportSong && candidates.has(button.dataset.reportSong)) {
        const {id}=await api('/catalog/import','POST',{external_id:button.dataset.reportSong});
        if (active()) location.hash='#song/'+id;
      } else if (button.dataset.close!==undefined) button.closest('dialog').close();
      else if (button.dataset.retry!==undefined) await mountReport();
    } catch(error) {if(active()) toast(error.message);}
    finally {button.disabled=false;}
  });
  try {
    await load();
    if (!active()) return;
    view.insertAdjacentHTML('beforeend','<dialog aria-labelledby="report-artist-title"><div class="modal-heading"><h2 id="report-artist-title"></h2><button class="button outline" data-close>닫기</button></div><div class="modal-body ai-artist-songs"></div></dialog>');
  } catch(error) {
    if (active()) view.innerHTML=`<h1>AI 리포트</h1><p role="alert">${esc(error.message)}</p><button class="button outline" data-retry>다시 불러오기</button>`;
  }
}
