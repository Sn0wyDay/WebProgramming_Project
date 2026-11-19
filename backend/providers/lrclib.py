import math
import re
import unicodedata
from flask import current_app,has_app_context
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler,build_opener
from .http import JsonClient, ProviderError


class LyricsRedirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        parts=urlsplit(newurl)
        if parts.scheme!='https' or parts.netloc!='lrclib.net':raise ProviderError('가사 제공처의 연결 주소를 확인하지 못했습니다.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


class LyricsClient(JsonClient):
    def headers(self):
        headers=super().headers()
        key=current_app.config.get('LRCLIB_API_KEY') if has_app_context() else None
        if key:headers['Lrclib-Api-Key']=key
        return headers

    def open(self,request,timeout):
        if request.get_header('Lrclib-api-key'):
            return build_opener(LyricsRedirects()).open(request,timeout=timeout)
        return super().open(request,timeout)


client = LyricsClient('https://lrclib.net', 1.05)


def normalized(text):
    if not isinstance(text,str):return ''
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def titles(text):
    parts = re.split(r'[()\[\]]', text)
    return {normalized(p) for p in parts if normalized(p)} | {normalized(text)}


def album_key(text):
    # Only format suffixes; keep Deluxe/Live/remaster editions distinct.
    return normalized(re.sub(r'\s+(?:-\s*|\(\s*)?(?:EP|Single)\)?\s*$', '', text, flags=re.I))


def artist_keys(artist, aliases):
    allowed = bilingual_artist_keys(artist)
    for alias in aliases:
        allowed.update(bilingual_artist_keys(alias))
        allowed.update((normalized(artist+alias), normalized(alias+artist)))
    return allowed


def bilingual_artist_keys(text):
    """Recognize JANNABI(잔나비), not a featured artist or a substring match."""
    keys={normalized(text)}
    match=re.fullmatch(r'\s*([^()[\]]+?)\s*(?:\(([^()[\]]+?)\)|\[([^()[\]]+?)\])\s*',text or '')
    if not match:return keys
    left,right=match[1],match[2] or match[3]
    if any(re.search(r'(?:\b(?:feat|ft|with|and|vs)\b|[,&;/+×])',part,re.I) for part in (left,right)):return keys
    korean=lambda part:bool(re.search('[가-힣]',part)) and not re.search('[a-z]',part,re.I)
    latin=lambda part:bool(re.search('[a-z]',part,re.I)) and not re.search('[가-힣]',part)
    if (korean(left) and latin(right)) or (latin(left) and korean(right)):
        keys.update((normalized(left),normalized(right)))
    return keys


def artist_matches(value,artist,aliases):
    return isinstance(value,str) and bool(bilingual_artist_keys(value)&artist_keys(artist,aliases))


def same_version(left, right):
    tags = ('live', 'remix', 'acoustic', '라이브', 'karaoke', 'cover', 'demo', 'slowed', 'sped', 'remaster', 'remastered', 'unplugged')
    def markers(text):
        # Latin markers must be words ("Alive" is not a live edition).
        words=set(re.findall(r'[^\W_]+',text.casefold(),re.UNICODE))
        markers={tag for tag in tags if tag in words}
        if {'instrumental','inst','반주','연주곡'}&words:markers.add('instrumental')
        return markers
    return markers(left)==markers(right)


def lyric_text(row):
    text=row.get('plainLyrics')
    if not isinstance(text,str) or not text.strip():text=row.get('syncedLyrics')
    if not isinstance(text,str):return None
    # Remove timing/metadata only; keep actual lyrics such as [Chorus].
    text=re.sub(r'^\s*\[(?:ar|al|ti|by|offset|length|re|ve):[^\]]*\]\s*$','',text,flags=re.I|re.M)
    text=re.sub(r'\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]|<\d{1,3}:\d{2}(?:[.:]\d{1,3})?>','',text)
    return '\n'.join(line.strip() for line in text.splitlines() if line.strip())


def parse_row(row, artist, duration_ms, aliases=(), album=None, strict=False):
    if not isinstance(row, dict) or not artist_matches(row.get('artistName'),artist,aliases):
        return None
    duration=row.get('duration')
    valid_duration=type(duration) in (int,float) and math.isfinite(duration) and duration>0
    if strict and (not duration_ms or not valid_duration or not album or not row.get('albumName')):
        return None
    if duration_ms and (not valid_duration or abs(duration-duration_ms/1000)>(2 if strict else 8)):
        return None
    if strict and album_key(album)!=album_key(row['albumName']):
        return None
    text=lyric_text(row)
    if row.get('instrumental') or not isinstance(text,str) or not text.strip() or len(text)>100000:
        return None
    if type(row.get('id')) is not int or row['id']<=0 or not isinstance(row.get('trackName'),str):
        return None
    return dict(text=text, external_id=str(row['id']),source_url='https://lrclib.net/api/get/'+str(row['id']),
                title=row['trackName'],artist=row['artistName'],album=row.get('albumName'),duration=duration)


def search_rows(params):
    rows=client.get('/api/search',params)
    if not isinstance(rows,list):
        raise ProviderError('가사 제공처의 응답 형식이 올바르지 않습니다.')
    return rows


def request_artist(artist,aliases):
    # Prefer an explicitly verified Latin name where the catalog uses Korean.
    # This changes the query, never the identity checks on the returned record.
    if re.search('[가-힣]',artist):
        return next((name for name in aliases if re.search('[a-z]',name,re.I) and not re.search('[가-힣,]',name)),artist)
    return artist


def find(title, artist, duration_ms=None, aliases=(), title_aliases=(), album=None,preferred_id=None):
    queries=list(dict.fromkeys([title]+list(title_aliases)))[:3]
    provider_artist=request_artist(artist,aliases)
    def direct(row):
        if row is None:return None
        if not isinstance(row,dict):raise ProviderError('가사 직접 조회 응답 형식이 올바르지 않습니다.')
        for query in queries:
            parsed=parse_row(row,artist,duration_ms,aliases,album,strict=query!=title)
            if parsed and titles(query)&titles(parsed['title']) and same_version(query,parsed['title']):
                if duration_ms and abs(parsed['duration']-duration_ms/1000)>2:continue
                if album and parsed['album'] and album_key(album)!=album_key(parsed['album']):continue
                parsed['match_method']='title_alias' if query!=title else 'exact'
                return parsed
        return None
    if preferred_id and str(preferred_id).isdigit():
        row=client.get('/api/get/'+str(preferred_id))
        if row is not None and (not isinstance(row,dict) or str(row.get('id'))!=str(preferred_id)):
            raise ProviderError('가사 제공처의 곡 ID가 일치하지 않습니다.')
        result=direct(row)
        if result:return result
    # A signature lookup does not depend on the provider's search index.
    # Explicit aliases are tried before any broader search, never guessed.
    for query in queries:
        params={'track_name':query,'artist_name':provider_artist}
        if album:params['album_name']=album
        if duration_ms and 1000<=duration_ms<=3600000:params['duration']=duration_ms/1000
        result=direct(client.get('/api/get',params))
        if result:return result
    def choose(rows,query):
        matches=[]
        for row in rows:
            parsed=parse_row(row,artist,duration_ms,aliases,album,strict=query!=title)
            if not parsed or not titles(query).intersection(titles(parsed['title'])) or not same_version(query,parsed['title']):continue
            parsed['match_method']='title_alias' if query!=title else 'exact'
            matches.append(parsed)
        # Provider ordering is not a confidence score. Prefer this album and
        # the closest duration over reissues, compilations and incomplete rows.
        def rank(row):
            album_match=bool(album and row['album'] and album_key(album)==album_key(row['album']))
            delta=abs(row['duration']-duration_ms/1000) if duration_ms else 0
            return (not album_match,delta,normalized(row['title'])!=normalized(query),int(row['external_id']))
        return min(matches,key=rank) if matches else None
    for query in queries:
        result=choose(search_rows({'track_name':query,'artist_name':provider_artist}),query)
        if result:return result
        # The provider's artist filter cannot expand aliases; title-only search
        # retrieves those rows, then the same strict local identity checks apply.
        result=choose(search_rows({'track_name':query}),query)
        if result:return result
    return None


def candidates(title,artist,album,duration_ms,aliases=()):
    """Suggestions, NOT automatic identity decisions based on track length."""
    if not album or not duration_ms:
        return []
    matches={}
    for row in search_rows({'q':request_artist(artist,aliases)+' '+re.sub(r'\s+-\s+EP$','',album,flags=re.I)}):
        parsed=parse_row(row,artist,duration_ms,aliases,album,strict=True)
        if parsed and same_version(title,parsed['title']):
            key=normalized(parsed['title'])
            rank=lambda value:(abs(value['duration']-duration_ms/1000),int(value['external_id']))
            if key not in matches or rank(parsed)<rank(matches[key]):matches[key]=parsed
    return sorted(matches.values(),key=lambda value:(abs(value['duration']-duration_ms/1000),int(value['external_id'])))[:5]
