"""Read IZM's public search response. Retain metadata and a short excerpt only."""
import re
from bs4 import BeautifulSoup
from .http import JsonClient,ProviderError
from .musicbrainz import name_key

SOURCE='IZM'
SITE='https://www.izm.co.kr'


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


client=JsonClient('https://api.izm.co.kr/api',1.05,transform=normalize_search)


def track_key(text):
    # Featured credits can differ in typography. Live/remix/instrumental tags stay.
    return name_key(re.sub(r'\s*[([]\s*(?:feat\.?|ft\.?)\s+[^)\]]*[)\]]','',text,flags=re.I))


def match(row,title,artist_names,album=None,instrumental=False):
    if not {name_key(a) for a in artist_names}&{name_key(a) for a in row['artists']}:return None
    if row['kind']=='song':
        return 'song' if track_key(row['title'])==track_key(title) else None
    if album and name_key(row['title'])==name_key(album):return 'album'
    # An album review must list this exact version as a track; a mention in prose
    # or an artist name alone is insufficient. Instrumentals keep their suffix.
    if not instrumental and any(track_key(t)==track_key(title) for t in row['tracks']):return 'album_track'
    return None


def find(title,artist,album=None,instrumental=False,resolve_aliases=None):
    names=[artist];seen=set();found={};received={}
    def collect():
        for row in received.values():
            relation=match(row,title,names,album,instrumental)
            if relation:found[row['url']]={**row,'relation':relation}
    def search(query):
        key=name_key(query)
        if not key or key in seen:return
        seen.add(key)
        rows=client.get('/content/search/',{'keyword':query})
        if not isinstance(rows,list):raise ProviderError('평론 검색을 완료하지 못했습니다.')
        for row in rows:received[row['url']]=row
        collect()
    search(title)
    if found:return list(found.values())[:3]
    if album:search(album)
    if found:return list(found.values())[:3]
    if resolve_aliases and not re.search('[가-힣]',artist):names+=resolve_aliases()
    names=list(dict.fromkeys(names))
    # Recheck earlier title/album results after their artist aliases are known.
    collect()
    if found:return list(found.values())[:3]
    # IZM indexes Korean artist names. Prefer a provider-verified Korean alias.
    query=next((n for n in names if re.search('[가-힣]',n)),artist)
    search(query)
    return sorted(found.values(),key=lambda row:row['relation']!='song')[:3]
