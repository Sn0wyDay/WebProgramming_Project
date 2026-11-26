"""Read IZM's public search response. Retain metadata and a short excerpt only."""
import re
import time
from flask import g,has_request_context
from bs4 import BeautifulSoup
from .http import JsonClient,ProviderError
from .musicbrainz import name_key
from .review_matching import same_artist,same_title

SOURCE='IZM'
SITE='https://www.izm.co.kr'
LABELED_CREDITS=re.compile(r'\s*\((?:작사|작곡|편곡)\s*:\s*[^()]+\)\s*$')
CREDIT_NAMES=r'[가-힣]{2,5}(?:\s*,\s*[가-힣]{2,5})*'
UNLABELED_CREDITS=re.compile(rf'\s*\({CREDIT_NAMES}\s+/\s+{CREDIT_NAMES}\)\s*$')


def text_blocks(html):
    soup=BeautifulSoup(html,'html.parser')
    for node in soup(['script','style','iframe','noscript']):node.decompose()
    return [re.sub(r'\s+',' ',s).strip() for s in soup.get_text('\n').splitlines() if s.strip()]


def short_excerpt(lines):
    if not lines:return ''
    # At most one sentence, 20 whitespace-delimited words and 110 characters.
    sentence=re.split(r'(?<=[.!?。])\s+',lines[0],maxsplit=1)[0]
    words=sentence.split();excerpt=' '.join(words[:20])
    cut=len(words)>20 or len(excerpt)>110
    return excerpt[:110].rstrip()+('…' if cut else '')


def normalize_search(data):
    if not isinstance(data,dict) or not isinstance(data.get('contents'),dict):
        raise ProviderError('평론 검색 응답을 확인하지 못했습니다.')
    contents=data['contents'];items=[]
    for category,kind in [('single_review_contents','song'),('album_review_contents','album')]:
        rows=contents.get(category)
        if not isinstance(rows,list):raise ProviderError('평론 목록 형식이 올바르지 않습니다.')
        for row in rows[:30]:
            if not isinstance(row,dict) or row.get('main_category')!='Review':continue
            rid=row.get('id');title=row.get('title');author=row.get('writer_name');html=row.get('content')
            if type(rid) is not int or rid<=0 or not isinstance(title,str) or not title.strip() or not isinstance(author,str) or not author.strip() or not isinstance(html,str):continue
            artists=[]
            for artist in row.get('artists') or []:
                if isinstance(artist,dict):artists.extend(artist.get(k) for k in ('kr_name','en_name') if isinstance(artist.get(k),str) and artist[k].strip())
            if not artists:continue
            lines=text_blocks(html);tracks=[];in_tracks=False
            for line in lines:
                if re.fullmatch(r'[-\s]*수록곡[-\s]*',line):in_tracks=True;continue
                if in_tracks:
                    match=re.match(r'^\d{1,2}\.\s*(.+)',line)
                    if match:tracks.append(re.sub(r'\s*\[추천\]\s*$','',match[1]).strip())
            intro=short_excerpt(lines)
            if intro:items.append(dict(external_id=rid,title=title.strip()[:255],author=author.strip()[:255],artists=artists,
                                      kind=kind,tracks=tracks[:100],introduction=intro,url=SITE+'/posts?id='+str(rid)))
    # Raw article HTML and unrelated feature articles never enter the disk cache.
    return items


REVIEW_RETRY_SECONDS=8


class ReviewSearchClient(JsonClient):
    retry_unhinted_503=True

    def _read(self,key,store):
        row=super()._read(key,store)
        if (row and key.startswith('/') and has_request_context() and getattr(g,'refresh_reviews',False)
                and time.time()-row['saved']>=REVIEW_RETRY_SECONDS):
            # An earlier list can be nonempty but have no article for this recording.
            return dict(row,expires=0)
        return row

    @staticmethod
    def _fallback(cached,error):
        value=JsonClient._fallback(cached,error)
        if has_request_context():
            g.review_search_error=error
        return value


client=ReviewSearchClient('https://api.izm.co.kr/api',1.05,transform=normalize_search)


def track_titles(tracks):
    # Some IZM tracklists label the credits on the first track only.
    has_labeled_credits=any(LABELED_CREDITS.search(track) for track in tracks)
    for track in tracks:
        yield track
        title=LABELED_CREDITS.sub('',track)
        if title==track and has_labeled_credits:
            title=UNLABELED_CREDITS.sub('',track)
        if title!=track:yield title


def has_track(row,titles):
    return any(same_title(track,title) for track in track_titles(row['tracks']) for title in titles)


def match(row,title,artist_names,album=None,instrumental=False,release_names=()):
    if not any(same_artist(a,artist_names) for a in row['artists']):return None
    if row['kind']=='song':
        return 'song' if same_title(row['title'],title) else None
    if album and same_title(row['title'],album):return 'album'
    if (not instrumental and any(same_title(row['title'],name) for name in release_names)
            and has_track(row,(title,))):return 'album_track'
    return None


def find(title,artist,album=None,instrumental=False,resolve_aliases=None,title_aliases=(),
         release_names=(),resolve_releases=None):
    names=[artist];seen=set();found={};received={}
    titles=[title,*title_aliases]

    def collect(releases=release_names):
        for row in received.values():
            relation=next((kind for t in titles if (kind:=match(row,t,names,album,instrumental,releases))),None)
            if relation:found[row['url']]={**row,'relation':relation}

    def collect_verified_tracks():
        if not resolve_releases or instrumental:return
        if any(
            row['kind']=='album' and any(same_artist(a,names) for a in row['artists']) and has_track(row,titles)
            for row in received.values()
        ):
            # This lookup is keyed by the selected recording ID.
            collect(resolve_releases())

    def search(query):
        key=name_key(query)
        if not key or key in seen:return
        seen.add(key)
        rows=client.get('/content/search/',{'keyword':query})
        if not isinstance(rows,list):raise ProviderError('평론 검색을 완료하지 못했습니다.')
        for row in rows:received[row['url']]=row
        collect()
    # An album or artist search for another track may already contain this review.
    for query in dict.fromkeys([title,album,artist,*title_aliases]):
        if not query:continue
        rows=client.cached('/content/search/',{'keyword':query})
        if rows:
            received.update((row['url'],row) for row in rows)
    collect()
    if found:return list(found.values())[:3]
    search(title)
    if found:return list(found.values())[:3]
    if album:search(album)
    if found:return list(found.values())[:3]
    for alternate in list(title_aliases)[:1]:search(alternate)
    if found:return list(found.values())[:3]
    alias_error=None
    if resolve_aliases and not re.search('[가-힣]',artist):
        try:names+=resolve_aliases()
        except ProviderError as error:alias_error=error
    names=list(dict.fromkeys(names))
    # Recheck earlier title/album results after their artist aliases are known.
    collect()
    if found:return list(found.values())[:3]
    # IZM indexes Korean artist names. Prefer a provider-verified Korean alias.
    query=next((n for n in names if re.search('[가-힣]',n)),artist)
    search(query)
    if not found:collect_verified_tracks()
    if alias_error and not found:raise alias_error
    return sorted(found.values(),key=lambda row:row['relation']!='song')[:3]
