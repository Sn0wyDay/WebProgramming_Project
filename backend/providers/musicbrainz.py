import json
from functools import lru_cache
from pathlib import Path
import re
import unicodedata
import hashlib
from .http import JsonClient, ProviderError
from .versions import is_instrumental

client = JsonClient('https://musicbrainz.org/ws/2', 1.05)
MBID = re.compile(r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$')


@lru_cache(maxsize=1)
def title_rules():
    path = Path(__file__).resolve().parents[1] / 'data' / 'title_aliases.json'
    return json.loads(path.read_text(encoding='utf-8'))


def corrected_item(item):
    rule = title_rules().get(item.get('external_id'))
    if rule and item.get('title') in rule.get('misspellings', ()):
        return {**item, 'title': rule['title']}
    return item


def corrected_recording_ids(query, title_only=False):
    term = name_key(query)
    matches = []
    for mbid, rule in title_rules().items():
        if not rule.get('misspellings'):
            continue
        titles = [rule['title'], *rule['misspellings'], *rule.get('alternate_titles', ())]
        artists = [rule['artist'], *rule.get('artist_aliases', ())]
        if any(term == name_key(title) or
               (not title_only and any(term in (name_key(artist + title), name_key(title + artist)) for artist in artists))
               for title in titles):
            matches.append(mbid)
    return matches


def corrected_page(page):
    return {**page, 'items': [corrected_item(item) for item in page['items']]}


def official_release_names(releases):
    return list(dict.fromkeys(
        release['title'] for release in releases
        if isinstance(release,dict) and release.get('status')=='Official'
        and isinstance(release.get('title'),str) and release['title'].strip()
    ))


def normalize(record):
    if not isinstance(record, dict) or not MBID.fullmatch(str(record.get('id', ''))):
        raise ProviderError('곡 식별자가 올바르지 않습니다.')
    credits = record.get('artist-credit') or []
    artist = ''.join(c if isinstance(c, str) else c.get('name', c.get('artist', {}).get('name', '')) + c.get('joinphrase', '') for c in credits)
    releases = record.get('releases') or []
    release = next((r for r in releases if r.get('status') == 'Official'), releases[0] if releases else {})
    if not record.get('title') or not artist:
        raise ProviderError('곡명 또는 가수 정보가 없는 응답입니다.')
    # Recording search embeds only matching release tracks in media[].track.
    # Their credited titles can differ across language editions of the same recording.
    release_titles = []
    for edition in releases:
        for medium in edition.get('media', []):
            for track in medium.get('track', []):
                title = track.get('title')
                if (isinstance(title, str) and title.strip() and title != record['title']
                        and title not in release_titles):
                    release_titles.append(title)
    return corrected_item(dict(release_titles=release_titles[:4], release_names=official_release_names(releases),
                external_id=record['id'], provider='musicbrainz', title=record['title'], artist=artist,
                album=release.get('title'), album_id=release.get('id'), duration_ms=record.get('length'),
                instrumental=is_instrumental(record['title'],record.get('disambiguation','')),
                source_url='https://musicbrainz.org/recording/' + record['id']))


def name_key(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def search_key(query,page,field='all',artist=''):
    prefix = 'corrected-search:' if corrected_recording_ids(query) else 'search-result:'
    if field!='all':prefix+=field+':'
    term = unicodedata.normalize('NFKC',query).casefold().strip()
    if field == 'combined':
        term = json.dumps([term, unicodedata.normalize('NFKC',artist).casefold().strip()])
    return prefix+hashlib.sha256(f'{page}:{term}'.encode()).hexdigest()


def cached_search(query,page=1,field='all',artist=''):
    page = client.recall(search_key(query,page,field,artist))
    return corrected_page(page) if page is not None else None


def exact_artists(query):
    known=client.recall('artist-query:'+name_key(query))
    if known:return known
    terms = re.findall(r'[^\W_]+', query, re.UNICODE)
    if not terms:
        return []
    text = ' AND '.join('"'+t+'"' for t in terms)
    result = client.get('/artist/', {'query': text, 'fmt': 'json', 'limit': 10})
    if not isinstance(result, dict) or not isinstance(result.get('artists'), list):
        raise ProviderError('가수 별칭 검색 응답이 올바르지 않습니다.')
    matches = []
    for artist in result['artists']:
        names = [artist.get('name', ''), artist.get('sort-name', '')] + [a.get('name', '') for a in artist.get('aliases', [])]
        if any(name_key(n)==name_key(query) for n in names) and MBID.fullmatch(str(artist.get('id',''))):
            matches.append(dict(id=artist['id'], name=artist['name'], aliases=list(dict.fromkeys(n for n in names if n))))
    if matches:client.remember('artist-query:'+name_key(query),matches)
    return matches


def search_terms(value):
    return ' AND '.join(f'"{term}"' for term in re.findall(r'[^\W_]+', value))


def search(query, page=1, field='all', artist=''):
    text = search_terms(query)
    artist_input = artist if field == 'combined' else query
    artist_terms = search_terms(artist_input)
    if not text or not artist_terms:
        return dict(items=[], pages=0, page=page, total=0)
    artist_clause = f'(artist:({artist_terms}) OR artistname:({artist_terms}))'
    if field in ('title', 'combined'):
        text = f'recording:({text})'
    elif field == 'artist':
        text = artist_clause
    corrected_ids = [] if field == 'artist' else corrected_recording_ids(query, title_only=field != 'all')
    if corrected_ids:
        text = ' OR '.join(['(' + text + ')'] + ['rid:' + mbid + '^10' for mbid in corrected_ids])

    def recordings(matches):
        ids = ' OR '.join('arid:' + item['id'] for item in matches)
        if field == 'combined':
            expression = f'({text}) AND ({ids or artist_clause})'
        else:
            expression = ids or text
        return client.get('/recording/', {'query': expression, 'fmt': 'json', 'limit': 20, 'offset': (page-1)*20})

    matched_artists = [] if field == 'title' else client.recall('artist-query:'+name_key(artist_input)) or []
    result = recordings(matched_artists)
    if not matched_artists and field != 'title' and isinstance(result, dict) and result.get('count') in (0,'0'):
        matched_artists = exact_artists(artist_input)
        if matched_artists:
            result = recordings(matched_artists)
    if not isinstance(result, dict) or not isinstance(result.get('recordings'), list):
        raise ProviderError('음악 검색 응답이 올바르지 않습니다.')
    try:
        total = max(0, int(result.get('count', 0)))
    except (TypeError, ValueError) as error:
        raise ProviderError('검색 결과 개수가 올바르지 않습니다.') from error
    items=[normalize(r) for r in result['recordings']]
    from flask import g,has_request_context
    source_mode=getattr(g,'provider_status',{}).get('mode') if has_request_context() else None
    if source_mode not in ('cache','stale'):
        for item in items:client.remember(item['external_id'],item)
    response=dict(items=items, page=page, pages=(total+19)//20, total=total, matched_artists=[a['name'] for a in matched_artists])
    if source_mode!='stale':client.remember(search_key(query,page,field,artist),response)
    return response


def lookup(external_id):
    if not isinstance(external_id, str) or not MBID.fullmatch(external_id):
        raise ProviderError('올바른 MusicBrainz 곡 ID가 필요합니다.', 'invalid_song_id', 400)
    snapshot=client.recall(external_id)
    if snapshot:return corrected_item(snapshot)
    result = client.get('/recording/' + external_id, {'inc': 'artists+releases', 'fmt': 'json'})
    if result is None:
        raise ProviderError('제공처에서 해당 곡을 찾지 못했습니다.', 'song_not_found', 404)
    return normalize(result)


def recording_titles(external_id,allow_network=True):
    """Alternate titles explicitly attached to the same recording ID."""
    if not MBID.fullmatch(external_id):
        return []
    result=(client.get if allow_network else client.cached)('/recording/'+external_id, {'inc':'aliases','fmt':'json'})
    if result is None and not allow_network:return []
    if not isinstance(result,dict) or result.get('id')!=external_id:
        raise ProviderError('곡 별칭 응답이 올바르지 않습니다.')
    return list(dict.fromkeys(a['name'] for a in result.get('aliases',[]) if isinstance(a.get('name'),str)))[:2]


def recording_release_names(external_id,allow_network=True):
    if not MBID.fullmatch(external_id):
        return []
    path='/recording/'+external_id
    params={'inc':'artists+releases','fmt':'json'}
    row=client.cached(path,params)
    if row is None and allow_network:
        row=client.get(path,params)
    if row is None and not allow_network:
        snapshot=client.recall(external_id) or {}
        return snapshot.get('release_names',[]) if snapshot.get('external_id')==external_id else []
    if row is None:return []
    if not isinstance(row,dict) or row.get('id')!=external_id:
        if not allow_network:return []
        raise ProviderError('곡의 수록 앨범 정보를 확인하지 못했습니다.')
    return official_release_names(row.get('releases') or [])


def cached_artist_aliases(query):
    known=client.recall('artist-query:'+name_key(query))
    if known and len(known)==1:return known[0]['aliases']
    terms=re.findall(r'[^\W_]+',query,re.UNICODE)
    text=' AND '.join('"'+t+'"' for t in terms)
    raw=client.cached('/artist/',{'query':text,'fmt':'json','limit':10})
    if not isinstance(raw,dict):return []
    matches=[]
    for artist in raw.get('artists',[]):
        names=[artist.get('name',''),artist.get('sort-name','')]+[a.get('name','') for a in artist.get('aliases',[])]
        if any(name_key(n)==name_key(query) for n in names):matches.append(names)
    return matches[0] if len(matches)==1 else []


def recording_artist_aliases(external_id):
    """Review-only alias lookup, anchored to a recording rather than a homonym search."""
    if not isinstance(external_id,str) or not MBID.fullmatch(external_id):return []
    known=client.recall('recording-artist-names:'+external_id)
    if known is not None:return known
    row=client.get('/recording/'+external_id,{'inc':'artists','fmt':'json'})
    if not isinstance(row,dict) or row.get('id')!=external_id:
        raise ProviderError('곡의 가수 정보를 확인하지 못했습니다.')
    credits=[c['artist'] for c in row.get('artist-credit',[]) if isinstance(c,dict) and isinstance(c.get('artist'),dict)]
    # Do not expand an ambiguous collaboration into a solo artist's reviews.
    if len(credits)!=1:return []
    artist_id=credits[0].get('id','')
    if not MBID.fullmatch(str(artist_id)):return []
    artist=client.get('/artist/'+artist_id,{'inc':'aliases','fmt':'json'})
    if not isinstance(artist,dict) or artist.get('id')!=artist_id:
        raise ProviderError('가수의 다른 표기를 확인하지 못했습니다.')
    names=[artist.get('name',''),credits[0].get('name','')]+[a.get('name','') for a in artist.get('aliases',[]) if isinstance(a,dict)]
    names=list(dict.fromkeys(n for n in names if isinstance(n,str) and n.strip()))
    client.remember('recording-artist-names:'+external_id,names)
    return names


REPORT_GENRES = {
    '인디 팝': 'indie pop', '인디 록': 'indie rock', 'R&B': 'r&b', '팝': 'pop',
    '힙합': 'hip hop', '재즈': 'jazz', '포크': 'folk', '일렉트로닉': 'electronic',
}


def report_candidates(song, genre):
    # Keep query syntax server-owned. Only public catalog metadata reaches the provider.
    words = re.findall(r'[^\W_]+', song.artist, re.UNICODE)
    if not words:
        return []
    artist = 'artist:"' + ' '.join(words) + '"'
    tag = f'tag:"{REPORT_GENRES[genre]}"' if genre else None
    queries = [artist] if not tag else [artist + ' AND ' + tag, tag]
    seen = {(name_key(song.artist), name_key(song.title))}
    items = []
    for query in queries:
        data = client.get('/recording/', {'query': query + ' AND video:false', 'fmt': 'json', 'limit': 30})
        if not isinstance(data, dict) or not isinstance(data.get('recordings'), list):
            raise ProviderError('추천 곡 목록을 읽을 수 없습니다.')
        for recording in data['recordings']:
            item = normalize(recording)
            key = (name_key(item['artist']), name_key(item['title']))
            if key in seen or item['external_id'] == song.external_id:
                continue
            seen.add(key)
            # Import can reuse the verified search row even during a provider outage.
            client.remember(item['external_id'], item)
            items.append(item)
            if len(items) == 12:
                return items
        if len(items) >= 3:
            break
    return items
