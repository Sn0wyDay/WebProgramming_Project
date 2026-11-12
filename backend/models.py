from datetime import datetime, timezone
from . import db

def now():
    return datetime.now(timezone.utc)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False)
    username = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(40), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

class Album(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(32), nullable=False)
    external_id = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    artist = db.Column(db.String(255), nullable=False)
    image = db.Column(db.Text)
    __table_args__ = (db.UniqueConstraint('provider', 'external_id'),)

class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(32), nullable=False)
    external_id = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    artist = db.Column(db.String(255), nullable=False)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'))
    __table_args__ = (db.UniqueConstraint('provider', 'external_id'),)

class LyricVersion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), nullable=False, index=True)
    provider = db.Column(db.String(32), nullable=False)
    digest = db.Column(db.String(64), nullable=False)
    source_url = db.Column(db.Text, nullable=False)
    __table_args__ = (db.UniqueConstraint('song_id', 'provider', 'digest'),)

class Passage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey('lyric_version.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    __table_args__ = (db.UniqueConstraint('version_id', 'position'),)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    passage_id = db.Column(db.Integer, db.ForeignKey('passage.id'), nullable=False, index=True)
    text = db.Column(db.String(2000), nullable=False)
    visibility = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    __table_args__ = (db.CheckConstraint("visibility IN ('private','friends')"),)

class UserSong(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), primary_key=True)
    rating = db.Column(db.Integer)
    saved = db.Column(db.Boolean, default=False, nullable=False)
    recorded = db.Column(db.Boolean, default=False, nullable=False)
    __table_args__ = (db.CheckConstraint('rating IS NULL OR (rating >= 1 AND rating <= 5)'),)

class Friendship(db.Model):
    low_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    high_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    accepted = db.Column(db.Boolean, default=False, nullable=False)
    __table_args__ = (db.CheckConstraint('low_id < high_id'), db.CheckConstraint('requester_id = low_id OR requester_id = high_id'))

class ReviewSource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), nullable=False, index=True)
    source_id = db.Column(db.Integer, db.ForeignKey('review_source.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(1000), nullable=False, unique=True)
    introduction = db.Column(db.Text)
