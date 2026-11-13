import re
import unicodedata
from .http import JsonClient, ProviderError

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
                source_url='https://musicbrainz.org/recording/' + record['id'])


def name_key(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def exact_artists(query):
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
    return matches


def search(query, page=1):
    # Escape Lucene operators; users enter ordinary words, not query syntax.
    terms = re.findall(r'[^\W_]+', query, re.UNICODE)
    if not terms:
        return dict(items=[], pages=0, page=page, total=0)
    text = ' AND '.join('"' + t + '"' for t in terms)
    result = client.get('/recording/', {'query': text, 'fmt': 'json', 'limit': 20, 'offset': (page-1)*20})
    matched_artists = []
    if isinstance(result, dict) and result.get('count') in (0, '0'):
        # Recording searches do not reliably index Korean artist aliases.
        # Resolve an exact provider alias first, then search the stable artist ID.
        matched_artists = exact_artists(query)
        if matched_artists:
            artist_query = ' OR '.join('arid:'+a['id'] for a in matched_artists)
            result = client.get('/recording/', {'query': artist_query, 'fmt': 'json', 'limit': 20, 'offset': (page-1)*20})
    if not isinstance(result, dict) or not isinstance(result.get('recordings'), list):
        raise ProviderError('음악 검색 응답이 올바르지 않습니다.')
    try:
        total = max(0, int(result.get('count', 0)))
    except (TypeError, ValueError) as error:
        raise ProviderError('검색 결과 개수가 올바르지 않습니다.') from error
    return dict(items=[normalize(r) for r in result['recordings']], page=page, pages=(total+19)//20, total=total, matched_artists=[a['name'] for a in matched_artists])


def lookup(external_id):
    if not isinstance(external_id, str) or not MBID.fullmatch(external_id):
        raise ProviderError('올바른 MusicBrainz 곡 ID가 필요합니다.', 'invalid_song_id', 400)
    result = client.get('/recording/' + external_id, {'inc': 'artists+releases', 'fmt': 'json'})
    if result is None:
        raise ProviderError('제공처에서 해당 곡을 찾지 못했습니다.', 'song_not_found', 404)
    return normalize(result)


def recording_titles(external_id):
    """Alternate titles explicitly attached to the same recording ID."""
    if not MBID.fullmatch(external_id):
        return []
    result=client.get('/recording/'+external_id, {'inc':'aliases','fmt':'json'})
    if not isinstance(result,dict) or result.get('id')!=external_id:
        raise ProviderError('곡 별칭 응답이 올바르지 않습니다.')
    return list(dict.fromkeys(a['name'] for a in result.get('aliases',[]) if isinstance(a.get('name'),str)))[:2]
