import hashlib
import json
from pathlib import Path
from . import db
from .models import Song, LyricVersion, Passage

def load_supplied_lyrics():
    rows = json.loads((Path(__file__).parent/'data/supplied_lyrics.json').read_text(encoding='utf-8'))
    for row in rows:
        songs = db.session.scalars(db.select(Song).where(Song.title == row['title'], Song.artist == row['artist'])).all()
        digest = hashlib.sha256('\n'.join(row['lines']).encode('utf-8')).hexdigest()
        for song in songs:
            existing = db.session.scalar(db.select(LyricVersion).where(LyricVersion.song_id == song.id, LyricVersion.provider == 'user-supplied', LyricVersion.digest == digest))
            if existing:
                continue
            version = LyricVersion(song_id=song.id, provider='user-supplied', digest=digest, source_url='', matched_title=row['title'], match_method='user_supplied')
            db.session.add(version)
            db.session.flush()
            db.session.add_all([Passage(version_id=version.id, position=i, text=line) for i,line in enumerate(row['lines'])])
    db.session.commit()
