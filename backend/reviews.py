"""Optional, public review metadata; no account records are sent to the provider."""
import hashlib
import json
import time
from sqlalchemy.exc import IntegrityError
from . import db
from .models import Album,Review,ReviewLink,ReviewSource
from .providers import izm,musicbrainz
from .providers.http import ProviderError


def for_song(song):
    rows=db.session.execute(db.select(Review,ReviewLink.kind).join(ReviewLink,ReviewLink.review_id==Review.id)
                            .where(ReviewLink.song_id==song.id).order_by(Review.id.desc()).limit(3)).all()
    return [dict(id=r.id,title=r.title,author=r.author,url=r.url,source=db.session.get(ReviewSource,r.source_id).name,
                 introduction=r.introduction,kind=kind) for r,kind in rows]


def save(song,items,retry=True):
    try:
        source=db.session.scalar(db.select(ReviewSource).where(ReviewSource.name==izm.SOURCE))
        if not source:
            source=ReviewSource(name=izm.SOURCE);db.session.add(source);db.session.flush()
        for item in items:
            review=db.session.scalar(db.select(Review).where(Review.url==item['url']))
            if not review:
                review=Review(song_id=song.id,source_id=source.id,title=item['title'],author=item['author'],url=item['url'],introduction=item['introduction'])
                db.session.add(review);db.session.flush()
            if not db.session.get(ReviewLink,(song.id,review.id)):
                db.session.add(ReviewLink(song_id=song.id,review_id=review.id,kind=item['relation']))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if not retry:raise
        save(song,items,retry=False)


def lookup(song):
    existing=for_song(song)
    if existing:return dict(status='available',reviews=existing,from_database=True)
    album=db.session.get(Album,song.album_id) if song.album_id else None
    identity=[song.provider,song.external_id,song.title,song.artist,album.title if album else None,song.is_instrumental]
    key=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()
    error=izm.client.recall('review-retry:'+key)
    if error and error['until']>time.time():
        return dict(status='unavailable',reviews=[],retry_after=max(1,int(error['until']-time.time())))
    missing=izm.client.recall('review-missing:'+key)
    if missing==[]:return dict(status='missing',reviews=[],retry_after=300)
    try:
        resolver=(lambda:musicbrainz.recording_artist_aliases(song.external_id)) if song.provider=='musicbrainz' else None
        items=izm.find(song.title,song.artist,album.title if album else None,song.is_instrumental,resolve_aliases=resolver)
    except ProviderError as error:
        wait=max(60,error.retry_after)
        izm.client.remember('review-retry:'+key,dict(until=time.time()+wait))
        return dict(status='unavailable',reviews=[],retry_after=wait)
    if not items:
        izm.client.remember('review-missing:'+key,[])
        return dict(status='missing',reviews=[],retry_after=300)
    save(song,items)
    return dict(status='available',reviews=for_song(song))
