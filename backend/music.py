"""Import provider-verified metadata and append immutable lyric snapshots."""
import hashlib
import json
from pathlib import Path
from sqlalchemy.exc import IntegrityError
from . import db
from .models import Song, Album, LyricVersion, Passage
from .providers import musicbrainz, lrclib


def import_song(external_id, retry=True):
    # Identity comes from the provider, never browser-supplied titles/lyrics.
    existing = db.session.scalar(db.select(Song).where(Song.provider=='musicbrainz', Song.external_id==external_id))
    if existing:
        return existing
    data = musicbrainz.lookup(external_id)
    album = None
    if data['album_id'] and data['album']:
        album = db.session.scalar(db.select(Album).where(Album.provider=='musicbrainz', Album.external_id==data['album_id']))
        if not album:
            album = Album(provider='musicbrainz', external_id=data['album_id'], title=data['album'], artist=data['artist'])
            db.session.add(album)
            db.session.flush()
    song = Song(provider='musicbrainz', external_id=data['external_id'], title=data['title'], artist=data['artist'], album_id=album.id if album else None, duration_ms=data['duration_ms'])
    db.session.add(song)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        song = db.session.scalar(db.select(Song).where(Song.provider=='musicbrainz', Song.external_id==external_id))
        if not song:
            # A concurrent import may have created the shared album. Retry once.
            if retry:
                return import_song(external_id, retry=False)
            raise
    return song


def artist_aliases(song):
    if song.provider != 'musicbrainz':
        return []
    artists=musicbrainz.exact_artists(song.artist)
    return artists[0]['aliases'] if len(artists)==1 else []


def alternate_titles(song, album):
    if song.provider != 'musicbrainz':
        return []
    rules=json.loads((Path(__file__).parent/'data/title_aliases.json').read_text())
    rule=rules.get(song.external_id)
    if rule and rule['title']==song.title and rule['artist']==song.artist and rule['album']==album and song.duration_ms and abs(rule['duration_ms']-song.duration_ms)<=2000:
        return rule['alternate_titles'][:2]
    return musicbrainz.recording_titles(song.external_id)


def lyric_candidates(song):
    album=db.session.get(Album,song.album_id) if song.album_id else None
    return lrclib.candidates(song.title,song.artist,album.title if album else None,song.duration_ms,aliases=artist_aliases(song))


def fetch_lyrics(song, candidate_id=None):
    if candidate_id is not None:
        # Recheck provider candidates; never accept arbitrary browser lyrics/IDs.
        result=next((r for r in lyric_candidates(song) if r['external_id']==str(candidate_id)),None)
        if not result:
            from .providers.http import ProviderError
            raise ProviderError('현재 곡의 가사 후보가 아닙니다. 다시 조회하세요.','invalid_lyric_candidate',400)
        result['match_method']='user_confirmed'
    else:
        result=lrclib.find(song.title,song.artist,song.duration_ms)
        if not result and song.provider=='musicbrainz':
            album=db.session.get(Album,song.album_id) if song.album_id else None
            album_title=album.title if album else None
            titles=alternate_titles(song,album_title)
            if titles:
                result=lrclib.find(song.title,song.artist,song.duration_ms,title_aliases=titles,album=album_title)
            if not result:
                aliases=artist_aliases(song)
                result=lrclib.find(song.title,song.artist,song.duration_ms,aliases=aliases,title_aliases=titles,album=album_title)
    if not result:
        return None
    # Store one canonical representation; never edit previous passages.
    lines = [line.strip() for line in result['text'].splitlines() if line.strip()]
    text = '\n'.join(lines)
    if not text:
        return None
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    version = db.session.scalar(db.select(LyricVersion).where(LyricVersion.song_id==song.id, LyricVersion.provider=='lrclib', LyricVersion.digest==digest))
    if version:
        return version
    version = LyricVersion(song_id=song.id, provider='lrclib', digest=digest, source_url=result['source_url'], matched_title=result.get('title'), match_method=result.get('match_method','exact'))
    db.session.add(version)
    try:
        db.session.flush()
        db.session.add_all([Passage(version_id=version.id, position=i, text=line) for i,line in enumerate(lines)])
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        version = db.session.scalar(db.select(LyricVersion).where(LyricVersion.song_id==song.id, LyricVersion.provider=='lrclib', LyricVersion.digest==digest))
        if not version:
            raise
    return version
