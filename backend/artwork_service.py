"""Keep verified cover thumbnails locally so browsing does not depend on a CDN."""
import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler,build_opener
from flask import current_app
from . import db
from .models import Album
from .providers import coverart
from .providers.http import JsonClient,ProviderError


def image_type(raw):
    if raw.startswith(b'\xff\xd8\xff'):return 'image/jpeg'
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png'
    if raw.startswith(b'RIFF') and raw[8:12]==b'WEBP':return 'image/webp'
    return None


def allowed_url(url):
    parts=urlsplit(url)
    return parts.scheme=='https' and parts.port in (None,443) and not parts.username and not parts.password and (parts.hostname in ('coverartarchive.org','archive.org') or (parts.hostname or '').endswith('.archive.org'))


class CoverRedirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # Older archive redirects still advertise HTTP; request HTTPS directly.
        if newurl.startswith('http://') and allowed_url('https://'+newurl[7:]):newurl='https://'+newurl[7:]
        if not allowed_url(newurl):raise ProviderError('앨범 이미지의 연결 주소를 확인하지 못했습니다.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def directory():
    return Path(current_app.config['ARTWORK_CACHE_PATH'])


def filename(url):
    return hashlib.sha256(url.encode()).hexdigest()+'.img'


def prune(folder):
    files=[]
    for path in folder.glob('*.img'):
        if not re.fullmatch(r'[0-9a-f]{64}\.img',path.name):continue
        try:
            stat=path.stat();files.append((stat.st_mtime,stat.st_size,path))
        except FileNotFoundError:continue
    files.sort(key=lambda item:item[0]);size=sum(item[1] for item in files)
    while len(files)>128 or size>32*1024*1024:
        _,length,path=files.pop(0)
        try:path.unlink()
        except FileNotFoundError:pass
        size-=length


def local_url(image):
    if not image or not coverart.source_url(image):return None
    name=filename(image)
    return '/api/media/artwork/'+name if (directory()/name).is_file() else None


class ImageClient(JsonClient):
    def headers(self):
        return {**super().headers(),'Accept':'image/jpeg,image/png,image/webp'}

    def open(self,request,timeout):
        if not allowed_url(request.full_url):raise ProviderError('앨범 이미지 주소가 올바르지 않습니다.')
        return build_opener(CoverRedirects()).open(request,timeout=timeout)

    def _read(self,key,store):
        row=super()._read(key,store)
        if row and isinstance(row['value'],dict) and not (directory()/row['value'].get('filename','missing')).is_file():return None
        return row

    def decode(self,raw,key,headers):
        mime=image_type(raw)
        if not mime or headers.get('Content-Type','').split(';')[0].strip().lower()!=mime:
            raise ValueError('unexpected image content')
        name=filename(self.base+key)
        folder=directory();folder.mkdir(parents=True,exist_ok=True)
        handle,path=tempfile.mkstemp(prefix='.cover-',dir=folder)
        try:
            with os.fdopen(handle,'wb') as output:output.write(raw)
            os.replace(path,folder/name)
            prune(folder)
        finally:
            if os.path.exists(path):os.unlink(path)
        return dict(filename=name,mime=mime)


# JSON metadata and image downloads share the same cross-process provider lease.
image_client=ImageClient('https://coverartarchive.org',1.05)


def album_for(song):
    return db.session.get(Album,song.album_id) if song.album_id else None


def cached(song):
    album=album_for(song)
    local=local_url(album.image) if album else None
    if local:return dict(status='available',image=local,local_cached=True,source_url=coverart.source_url(album.image))
    return None


def image_for(album):
    return (local_url(album.image) or album.image) if album else None


def lookup(song):
    album=album_for(song)
    if not album or album.provider!='musicbrainz':return dict(status='missing',image=None,retry_after=300)
    hit=cached(song)
    if hit:return hit
    try:
        if not album.image:
            result=coverart.find(album.external_id)
            if not result:return dict(status='missing',image=None,retry_after=300)
            album.image=result['image'];db.session.commit()
        if current_app.config['ARTWORK_DOWNLOAD_ENABLED'] and coverart.source_url(album.image):
            image_client.get(urlsplit(album.image).path)
        return dict(status='available',image=image_for(album),local_cached=bool(local_url(album.image)),source_url=coverart.source_url(album.image))
    except ProviderError as error:
        current_app.logger.warning('Local artwork cache: code=%s message=%s',error.code,str(error))
        # The original verified URL remains usable even if a download fails.
        return dict(status='unavailable',image=image_for(album),local_cached=False,code=error.code,
                    message='앨범 이미지를 다시 확인하는 중입니다.',retry_after=max(60,error.retry_after))


def cached_file(name):
    if not re.fullmatch(r'[0-9a-f]{64}\.img',name):return None
    path=directory()/name
    return path if path.is_file() else None
