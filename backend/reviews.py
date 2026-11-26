"""Optional, public review metadata; no account records are sent to the provider."""
import hashlib
import json
import time
import math
from contextlib import contextmanager
from flask import g,has_request_context
from sqlalchemy.exc import IntegrityError
from . import db
from .models import Album,Review,ReviewLink,ReviewSource
from .providers import izm,musicbrainz,hellokpop
from .providers.http import ProviderError


MATCH_RULE_VERSION=4


def for_song(song):
    rows=db.session.execute(db.select(Review,ReviewLink).join(ReviewLink,ReviewLink.review_id==Review.id)
                            .where(ReviewLink.song_id==song.id,
                                   (ReviewLink.kind!='album_track') | (ReviewLink.match_version==MATCH_RULE_VERSION))
                            .order_by(Review.id.desc()).limit(3)).all()
    return [dict(id=r.id,title=r.title,author=r.author,url=r.url,source=db.session.get(ReviewSource,r.source_id).name,
                 introduction=link.context or r.introduction,kind=link.kind,article_type=r.article_type) for r,link in rows]


def save(song,items,retry=True):
    try:
        for item in items:
            source_name=item.get('source',izm.SOURCE)
            source=db.session.scalar(db.select(ReviewSource).where(ReviewSource.name==source_name))
            if not source:
                source=ReviewSource(name=source_name);db.session.add(source);db.session.flush()
            review=db.session.scalar(db.select(Review).where(Review.url==item['url']))
            if not review:
                review=Review(song_id=song.id,source_id=source.id,title=item['title'],author=item['author'],url=item['url'],introduction=item['introduction'],article_type=item.get('article_type','review'))
                db.session.add(review);db.session.flush()
            link=db.session.get(ReviewLink,(song.id,review.id))
            if link is None:
                link=ReviewLink(song_id=song.id,review_id=review.id)
                db.session.add(link)
            elif link.kind!='album_track' or link.match_version==MATCH_RULE_VERSION:
                continue
            link.kind=item['relation']
            link.context=item.get('context')
            link.match_version=MATCH_RULE_VERSION
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if not retry:raise
        save(song,items,retry=False)


@contextmanager
def provider_budget(seconds):
    if not has_request_context():yield;return
    deadline=getattr(g,'provider_deadline',time.monotonic()+18)
    g.provider_deadline=min(deadline,time.monotonic()+seconds)
    try:yield
    finally:g.provider_deadline=deadline


MISSING_CACHE_SECONDS=300


def lookup(song,refresh=False):
    existing=for_song(song)
    if existing:return dict(status='available',reviews=existing,from_database=True)
    album=db.session.get(Album,song.album_id) if song.album_id else None
    identity=[MATCH_RULE_VERSION,song.provider,song.external_id,song.title,song.artist,album.title if album else None,song.is_instrumental]
    key=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()
    error=izm.client.recall('review-retry:'+key)
    if error and error['until']>time.time():
        return dict(status='unavailable',reviews=[],retry_after=max(1,math.ceil(error['until']-time.time())))
    missing=izm.client.recall('review-missing:'+key)
    if missing:
        remaining=math.ceil(missing['until']-time.time())
        manual_wait=max(0,remaining-MISSING_CACHE_SECONDS+izm.REVIEW_RETRY_SECONDS)
        if remaining>0 and (not refresh or manual_wait):
            return dict(status='missing',reviews=[],retry_after=manual_wait)
    if has_request_context():
        g.refresh_reviews=refresh
        g.review_search_error=None
    from .music import alternate_titles
    album_title=album.title if album else None
    title_aliases=alternate_titles(song,album_title)
    errors=[];items=[]
    try:
        metadata={}
        if song.provider=='musicbrainz':
            metadata=dict(
                resolve_aliases=lambda:musicbrainz.recording_artist_aliases(song.external_id),
                release_names=musicbrainz.recording_release_names(song.external_id,allow_network=False),
                resolve_releases=lambda:musicbrainz.recording_release_names(song.external_id),
            )
        with provider_budget(9):
            items=izm.find(song.title,song.artist,album_title,song.is_instrumental,title_aliases=title_aliases,**metadata)
    except ProviderError as error:
        errors.append(error)
    if not items:
        try:
            aliases=[]
            if song.provider=='musicbrainz':aliases=musicbrainz.client.recall('recording-artist-names:'+song.external_id) or []
            with provider_budget(8):
                items=hellokpop.find(song.title,song.artist,album_title,title_aliases=title_aliases,artist_names=aliases,instrumental=song.is_instrumental)
        except ProviderError as error:errors.append(error)
    if has_request_context() and g.review_search_error:
        errors.append(g.review_search_error)
    if not items and errors:
        wait=max(3,max(error.retry_after for error in errors))
        izm.client.remember('review-retry:'+key,dict(until=time.time()+wait))
        if missing:izm.client.remember('review-missing:'+key,dict(until=0))
        return dict(status='unavailable',reviews=[],retry_after=wait)
    if not items:
        izm.client.remember('review-missing:'+key,dict(until=time.time()+MISSING_CACHE_SECONDS))
        return dict(status='missing',reviews=[],retry_after=izm.REVIEW_RETRY_SECONDS)
    save(song,items)
    return dict(status='available',reviews=for_song(song),partial=bool(errors))
