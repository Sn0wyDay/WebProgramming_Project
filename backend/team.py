"""Explicit, one-time team showcase data. Never resets existing relationships."""
import secrets
from werkzeug.security import generate_password_hash
from . import db
from .models import User, Song, TeamProfile, Friendship

MEMBERS = [
    ('안민기', 'team_minki', '리도어', '0g'),
    ('손주희', 'team_juhee', '기리보이', '시간이 날 기다려'),
    ('엄기윤', 'team_giyoon', '페퍼톤스', '21세기의 어떤 날'),
    ('설은진', 'team_eunjin', '실리카겔', 'mercurial'),
]

def connect_team(user_id):
    for profile in db.session.scalars(db.select(TeamProfile)).all():
        if profile.user_id == user_id:
            continue
        low, high = sorted((user_id, profile.user_id))
        if not db.session.get(Friendship, (low, high)):
            db.session.add(Friendship(low_id=low, high_id=high, requester_id=user_id, accepted=True))

def seed_team():
    existing_users = db.session.scalars(db.select(User)).all()
    added = []
    for name, handle, artist, title in MEMBERS:
        if db.session.scalar(db.select(TeamProfile).join(Song, TeamProfile.song_id == Song.id).where(Song.title == title, Song.artist == artist)):
            continue
        # A unique matching name reuses the actual local account without changing credentials.
        matches = db.session.scalars(db.select(User).where(User.name == name)).all()
        person = matches[0] if len(matches) == 1 else db.session.scalar(db.select(User).where(User.username == handle, User.email == handle+'@team.reverse.invalid'))
        if person and db.session.get(TeamProfile, person.id):
            continue
        if person is None:
            username = handle
            while db.session.scalar(db.select(User).where(User.username == username)):
                username = handle + '_' + secrets.token_hex(3)
            person = User(name=name, username=username, email=username+'@team.reverse.invalid', password_hash=generate_password_hash(secrets.token_urlsafe(48)))
            db.session.add(person)
            db.session.flush()
        track = db.session.scalar(db.select(Song).where(Song.title == title, Song.artist == artist))
        if track is None:
            track = Song(provider='team-showcase', external_id=handle, title=title, artist=artist)
            db.session.add(track)
            db.session.flush()
        db.session.add(TeamProfile(user_id=person.id, song_id=track.id))
        added.append(person.id)
    db.session.flush()
    if added:
        for person in existing_users:
            connect_team(person.id)
        for uid in added:
            connect_team(uid)
    db.session.commit()
