import re
import unicodedata
from .http import JsonClient, ProviderError
from .versions import is_instrumental

client = JsonClient('https://musicbrainz.org/ws/2', 1.05)
MBID = re.compile(r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$')


def normalize(record):
    if not isinstance(record, dict) or not MBID.fullmatch(str(record.get('id', ''))):
        raise ProviderError('곡 식별자가 올바르지 않습니다.')
    credits = record.get('artist-credit') or []
    artist = ''.join(c if isinstance(c, str) else c.get('name', c.get('artist', {}).get('name', '')) + c.get('joinphrase', '') for c in credits)
    releases = record.get('releases') or []
    release = next((r for r in releases if r.get('status') == 'Official'), releases[0] if releases else {})
    if not record.get('title') or not artist:
        raise ProviderError('곡명 또는 가수 정보가 없는 응답입니다.')
    return dict(external_id=record['id'], provider='musicbrainz', title=record['title'], artist=artist,
                album=release.get('title'), album_id=release.get('id'), duration_ms=record.get('length'),
                instrumental=is_instrumental(record['title'],record.get('disambiguation','')),
                source_url='https://musicbrainz.org/recording/' + record['id'])


def name_key(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


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


def search(query, page=1):
    # Escape Lucene operators; users enter ordinary words, not query syntax.
    terms = re.findall(r'[^\W_]+', query, re.UNICODE)
    if not terms:
        return dict(items=[], pages=0, page=page, total=0)
    text = ' AND '.join('"' + t + '"' for t in terms)
    matched_artists=client.recall('artist-query:'+name_key(query)) or []
    if matched_artists:
        artist_query=' OR '.join('arid:'+a['id'] for a in matched_artists)
        result=client.get('/recording/',{'query':artist_query,'fmt':'json','limit':20,'offset':(page-1)*20})
    else:
        result=client.get('/recording/',{'query':text,'fmt':'json','limit':20,'offset':(page-1)*20})
        if isinstance(result,dict) and result.get('count') in (0,'0'):
            matched_artists=exact_artists(query)
            if matched_artists:
                artist_query=' OR '.join('arid:'+a['id'] for a in matched_artists)
                result=client.get('/recording/',{'query':artist_query,'fmt':'json','limit':20,'offset':(page-1)*20})
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
    return dict(items=items, page=page, pages=(total+19)//20, total=total, matched_artists=[a['name'] for a in matched_artists])


def lookup(external_id):
    if not isinstance(external_id, str) or not MBID.fullmatch(external_id):
        raise ProviderError('올바른 MusicBrainz 곡 ID가 필요합니다.', 'invalid_song_id', 400)
    snapshot=client.recall(external_id)
    if snapshot:return snapshot
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
