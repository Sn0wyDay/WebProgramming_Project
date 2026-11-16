"""Optional album artwork, matched by MusicBrainz release IDs, never title guesses."""
import re
import time
from urllib.parse import urlsplit
from . import musicbrainz
from .http import JsonClient, ProviderError

client = JsonClient('https://coverartarchive.org', 1.05)


def source_url(image):
    if not isinstance(image, str):
        return None
    parts = urlsplit(image)
    match = re.fullmatch(r'/release/([0-9a-f-]{36})/[0-9]+(?:-(?:250|500|1200))?\.(?:jpg|jpeg|png|webp)', parts.path)
    if parts.scheme != 'https' or parts.netloc != 'coverartarchive.org' or not match or not musicbrainz.MBID.fullmatch(match[1]):
        return None
    return 'https://musicbrainz.org/release/' + match[1] + '/cover-art'


def front(data, release_id=None):
    if data is None:
        return None
    if not isinstance(data, dict) or not isinstance(data.get('images'), list):
        raise ProviderError('앨범 표지 응답 형식이 올바르지 않습니다.')
    release = urlsplit(str(data.get('release', '')))
    actual_id = release.path.removeprefix('/release/')
    if release.scheme not in ('http', 'https') or release.netloc != 'musicbrainz.org' or not release.path.startswith('/release/') or not musicbrainz.MBID.fullmatch(actual_id) or (release_id and actual_id != release_id):
        raise ProviderError('앨범 표지의 발매 ID가 일치하지 않습니다.')
    for image in data['images']:
        if not isinstance(image, dict) or image.get('front') is not True or image.get('approved') is not True:
            continue
        image_id = str(image.get('id', ''))
        if not image_id.isdigit():
            continue
        thumbs = image.get('thumbnails') or {}
        if not isinstance(thumbs, dict):
            continue
        for url in (thumbs.get('500'), thumbs.get('large'), thumbs.get('250'), thumbs.get('small'), image.get('image')):
            if not isinstance(url, str):
                continue
            url = 'https:' + url[5:] if url.startswith('http:') else url
            image_path = r'/release/' + actual_id + '/' + image_id + r'(?:-(?:250|500|1200))?\.(?:jpg|jpeg|png|webp)'
            if source_url(url) and re.fullmatch(image_path, urlsplit(url).path):
                return dict(image=url, source_url=source_url(url), provider='Cover Art Archive')
    return None


def find(release_id):
    if not isinstance(release_id, str) or not musicbrainz.MBID.fullmatch(release_id):
        return None
    blocked = client.recall('retry:' + release_id)
    if blocked and blocked['until'] > time.time():
        raise ProviderError('앨범 표지는 잠시 뒤 다시 조회합니다.', blocked['code'], 503, blocked['until'] - time.time())
    try:
        data = client.get('/release/' + release_id)
        result = front(data, release_id)
        if result:
            return result
        # Some editions have no image. Only a provider-confirmed release group
        # may supply another edition's cover; album names are not enough.
        release = musicbrainz.client.get('/release/' + release_id, {'inc': 'release-groups', 'fmt': 'json'})
        if not isinstance(release, dict) or release.get('id') != release_id:
            raise ProviderError('앨범의 발매 정보를 확인하지 못했습니다.')
        group_id = (release.get('release-group') or {}).get('id', '')
        return front(client.get('/release-group/' + group_id)) if musicbrainz.MBID.fullmatch(str(group_id)) else None
    except ProviderError as error:
        client.remember('retry:' + release_id, dict(until=time.time() + max(60, error.retry_after), code=error.code))
        raise
