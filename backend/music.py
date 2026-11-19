"""Import provider-verified metadata and append immutable lyric snapshots."""
import hashlib
import json
import re
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
    song = Song(provider='musicbrainz', external_id=data['external_id'], title=data['title'], artist=data['artist'], album_id=album.id if album else None, duration_ms=data['duration_ms'],is_instrumental=data.get('instrumental',False))
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
    # Metadata/review lookups may already have resolved this precise recording.
    # Reading those verified names must never add a MusicBrainz HTTP dependency.
    precise=musicbrainz.client.recall('recording-artist-names:'+song.external_id)
    names=precise if precise else musicbrainz.cached_artist_aliases(song.artist)
    album=db.session.get(Album,song.album_id) if song.album_id else None
    rule=verified_lyric_rule(song,album.title if album else None)
    return list(dict.fromkeys(list(names)+rule.get('artist_aliases',[])))


def verified_lyric_rule(song,album):
    if song.provider!='musicbrainz':return {}
    rules=json.loads((Path(__file__).parent/'data/title_aliases.json').read_text())
    rule=rules.get(song.external_id)
    if (rule and rule['title']==song.title and rule['artist']==song.artist
            and musicbrainz.name_key(rule['album'])==musicbrainz.name_key(album or '')
            and song.duration_ms and abs(rule['duration_ms']-song.duration_ms)<=2000):return rule
    return {}


def alternate_titles(song, album):
    if song.provider != 'musicbrainz':
        return []
    rule=verified_lyric_rule(song,album)
    if rule:
        return rule['alternate_titles'][:2]
    return musicbrainz.recording_titles(song.external_id,allow_network=False)


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
        album=db.session.get(Album,song.album_id) if song.album_id else None
        album_title=album.title if album else None
        # Lyrics depend on LRCLIB only. Optional MusicBrainz hints are cache-only.
        previous=db.session.scalar(db.select(LyricVersion).where(LyricVersion.song_id==song.id,LyricVersion.provider=='lrclib').order_by(LyricVersion.id.desc()))
        preferred=re.fullmatch(r'https://lrclib.net/api/get/([1-9][0-9]*)',previous.source_url) if previous else None
        titles=alternate_titles(song,album_title)
        if previous and previous.match_method=='user_confirmed' and previous.matched_title:
            titles=list(dict.fromkeys(titles+[previous.matched_title]))
        result=lrclib.find(song.title,song.artist,song.duration_ms,aliases=artist_aliases(song),
                          title_aliases=titles,album=album_title,preferred_id=preferred[1] if preferred else None)
        if result and previous and previous.match_method=='user_confirmed' and result.get('title')==previous.matched_title:
            result['match_method']='user_confirmed'
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
