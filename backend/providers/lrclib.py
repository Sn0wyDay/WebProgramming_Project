import math
import re
import unicodedata
from .http import JsonClient, ProviderError

client = JsonClient('https://lrclib.net', 0.5)


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def titles(text):
    parts = re.split(r'[()\[\]]', text)
    return {normalized(p) for p in parts if normalized(p)} | {normalized(text)}


def album_key(text):
    # Only format suffixes; keep Deluxe/Live/remaster editions distinct.
    return normalized(re.sub(r'\s+(?:-\s*|\(\s*)?(?:EP|Single)\)?\s*$', '', text, flags=re.I))


def artist_keys(artist, aliases):
    allowed = {normalized(artist)}
    for alias in aliases:
        allowed.update((normalized(alias), normalized(artist+alias), normalized(alias+artist)))
    return allowed


def same_version(left, right):
    tags = ('live', 'remix', 'instrumental', 'acoustic', '라이브')
    def markers(text):
        # Latin markers must be words ("Alive" is not a live edition).
        words=set(re.findall(r'[^\W_]+',text.casefold(),re.UNICODE))
        return {tag for tag in tags if tag in words}
    return markers(left)==markers(right)


def parse_row(row, artist, duration_ms, aliases=(), album=None, strict=False):
    if not isinstance(row, dict) or normalized(row.get('artistName', '')) not in artist_keys(artist,aliases):
        return None
    duration=row.get('duration')
    valid_duration=type(duration) in (int,float) and math.isfinite(duration) and duration>0
    if strict and (not duration_ms or not valid_duration or not album or not row.get('albumName')):
        return None
    if duration_ms and valid_duration and abs(duration-duration_ms/1000)>(2 if strict else 8):
        return None
    if strict and album_key(album)!=album_key(row['albumName']):
        return None
    text=row.get('plainLyrics')
    if not text and isinstance(row.get('syncedLyrics'),str):
        text=re.sub(r'\[[^\]]*\]','',row['syncedLyrics'])
    if row.get('instrumental') or not isinstance(text,str) or not text.strip() or len(text)>100000:
        return None
    if type(row.get('id')) is not int or not isinstance(row.get('trackName'),str):
        return None
    return dict(text=text, external_id=str(row['id']),source_url='https://lrclib.net/api/get/'+str(row['id']),
                title=row['trackName'],artist=row['artistName'],album=row.get('albumName'),duration=duration)


def search_rows(params):
    rows=client.get('/api/search',params)
    if not isinstance(rows,list):
        raise ProviderError('가사 제공처의 응답 형식이 올바르지 않습니다.')
    return rows


def find(title, artist, duration_ms=None, aliases=(), title_aliases=(), album=None):
    for query in list(dict.fromkeys([title]+list(title_aliases)))[:3]:
        for row in search_rows({'track_name':query,'artist_name':artist}):
            parsed=parse_row(row,artist,duration_ms,aliases,album,strict=query!=title)
            if not parsed or not titles(query).intersection(titles(parsed['title'])):
                continue
            if not same_version(query,parsed['title']):
                continue
            parsed['match_method']='title_alias' if query!=title else 'exact'
            return parsed
    return None


def candidates(title,artist,album,duration_ms,aliases=()):
    """Suggestions, NOT automatic identity decisions based on track length."""
    if not album or not duration_ms:
        return []
    matches={}
    for row in search_rows({'artist_name':artist,'album_name':album}):
        parsed=parse_row(row,artist,duration_ms,aliases,album,strict=True)
        if parsed and same_version(title,parsed['title']):
            key=normalized(parsed['title'])
            matches.setdefault(key,parsed)
    return list(matches.values())[:5]
