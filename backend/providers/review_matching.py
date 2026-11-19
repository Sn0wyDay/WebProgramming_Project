"""Conservative metadata keys for reviews and editorial selections."""
import re
from .musicbrainz import name_key


def artist_keys(text):
    keys={name_key(text)}
    pair=re.fullmatch(r'\s*([^()[\]]+?)\s*(?:\(([^()[\]]+?)\)|\[([^()[\]]+?)\])\s*',text)
    if not pair:return keys
    left,right=pair[1],pair[2] or pair[3]
    if any(re.search(r'\b(?:feat|ft|with|and|vs)\b|[,&;/+×]',x,re.I) for x in (left,right)):return keys
    korean=lambda x:bool(re.search('[가-힣]',x)) and not re.search('[a-z]',x,re.I)
    latin=lambda x:bool(re.search('[a-z]',x,re.I)) and not re.search('[가-힣]',x)
    if (korean(left) and latin(right)) or (latin(left) and korean(right)):keys.update((name_key(left),name_key(right)))
    return keys


def version_marks(text):
    words=set(re.findall(r'[^\W_]+',text.casefold(),re.UNICODE))
    marks=words&{'live','라이브','remix','acoustic','cover','karaoke','demo','slowed','sped','deluxe','remaster','remastered','리마스터'}
    if words&{'inst','instrumental','반주','연주곡'}:marks.add('instrumental')
    return marks


def title_keys(text):
    # Publishing format is harmless; musical editions and versions stay distinct.
    text=re.sub(r'\s+(?:-\s*|\(\s*)?(?:EP|Single)\)?\s*$','',text,flags=re.I)
    text=re.sub(r'\s*[\(\[]\s*(?:feat\.?|ft\.?)\s+[^)\]]*[)\]]','',text,flags=re.I)
    keys={name_key(text)}
    pair=re.fullmatch(r'\s*([^()[\]]+?)\s*(?:\(([^()[\]]+?)\)|\[([^()[\]]+?)\])\s*',text)
    if pair and not version_marks(text):
        left,right=pair[1],pair[2] or pair[3]
        if bool(re.search('[가-힣]',left))!=bool(re.search('[가-힣]',right)):
            keys.update((name_key(left),name_key(right)))
    return keys


def same_title(left,right):
    return version_marks(left)==version_marks(right) and bool(title_keys(left)&title_keys(right))


def same_artist(left,right_names):
    return any(artist_keys(left)&artist_keys(right) for right in right_names)
