"""Verified year-end selections from a public WordPress API, not invented reviews."""
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from .http import JsonClient,ProviderError
from .izm import text_blocks
from .review_matching import same_artist,same_title

SOURCE='HELLOKPOP'


def normalize_search(data):
    if not isinstance(data,list):raise ProviderError('선정 기사 검색 응답을 확인하지 못했습니다.')
    articles=[]
    for row in data[:5]:
        if not isinstance(row,dict):continue
        title=' '.join(text_blocks((row.get('title') or {}).get('rendered','')))
        year=re.match(r'^(20\d{2}) In Review:.*Honorable Mentions$',title,re.I)
        if not year:continue
        url=row.get('link','');parts=urlsplit(url)
        if parts.scheme!='https' or parts.netloc!='www.hellokpop.com' or not parts.path.startswith('/review/'):continue
        author_id=row.get('author')
        authors=[a.get('name') for a in (row.get('_embedded') or {}).get('author',[]) if isinstance(a,dict) and a.get('id')==author_id and isinstance(a.get('name'),str)]
        if not authors:continue
        body=(row.get('content') or {}).get('rendered','')
        if not isinstance(body,str):continue
        soup=BeautifulSoup(body,'html.parser')
        for node in soup(['script','style','iframe','noscript']):node.decompose()
        genre='';section=None;entries=[]
        for node in soup.find_all(['h1','h2','h3','h4','p','li']):
            if node.name.startswith('h'):
                heading=node.get_text(' ',strip=True)
                if heading in ('Songs','Albums'):section='song' if heading=='Songs' else 'album'
                else:genre=heading;section=None
                continue
            if not section:continue
            for line in node.get_text('\n',strip=True).splitlines():
                pair=re.split(r'\s+[–—]\s+',line,maxsplit=1)
                if len(pair)==2 and all(p.strip() for p in pair):
                    entries.append(dict(artist=pair[0].strip(),title=pair[1].strip(),kind=section,genre=genre[:100]))
        if entries:articles.append(dict(title=title[:255],author=authors[0].strip()[:255],url=url,year=int(year[1]),entries=entries[:2000]))
    # Discard article bodies, author profiles and unrelated posts before caching.
    return articles


client=JsonClient('https://www.hellokpop.com/wp-json/wp/v2',1.05,transform=normalize_search)


def find(title,artist,album=None,title_aliases=(),artist_names=(),instrumental=False):
    if instrumental:return []
    queries=list(dict.fromkeys([title]+list(title_aliases)))[:2]
    for query in queries:
        rows=client.get('/posts',{'search':query,'per_page':5,'_embed':'author',
                                 '_fields':'id,title,link,author,content,_links,_embedded','orderby':'relevance'})
        if not isinstance(rows,list):raise ProviderError('선정 기사 목록을 확인하지 못했습니다.')
        found={}
        for article in rows:
            for entry in article['entries']:
                if not same_artist(entry['artist'],[artist]+list(artist_names)):continue
                song_match=entry['kind']=='song' and any(same_title(entry['title'],t) for t in [title]+list(title_aliases))
                album_match=entry['kind']=='album' and album and same_title(entry['title'],album)
                if not (song_match or album_match):continue
                intro=f"{article['year']}년 연말 결산 Honorable Mentions 선정 기사입니다."
                context=f"선정 항목: {entry['artist']} – {entry['title']} · {entry['genre']} · {article['year']}년 Honorable Mentions."
                found[article['url']]=dict(title=article['title'],author=article['author'],url=article['url'],introduction=intro,
                                          context=context[:500],relation='song' if song_match else 'album',article_type='selection',source=SOURCE)
        if found:return list(found.values())[:3]
    return []
