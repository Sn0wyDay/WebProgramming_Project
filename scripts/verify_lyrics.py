"""Opt-in real regression check for Jannabi; uses a disposable DB and no private data.
Run: .venv/bin/python -m scripts.verify_lyrics
"""
import tempfile
from pathlib import Path
from unittest.mock import patch
from flask_migrate import upgrade
from backend import create_app,db
from backend.models import User,Song,Album
from backend.providers import lrclib,musicbrainz


def main():
    with tempfile.TemporaryDirectory(prefix='reverse-lyrics-') as folder:
        app=create_app({'TESTING':True,'SECRET_KEY':'live','SESSION_SQLALCHEMY_TABLE':'live_lyric_sessions',
                        'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(Path(folder)/'test.db'),
                        'PROVIDER_CACHE_PATH':str(Path(folder)/'providers.db')})
        with app.app_context():
            upgrade(directory=str(Path(__file__).resolve().parents[1]/'migrations'))
            album=Album(provider='fixture',external_id='monkey',title='MONKEY HOTEL',artist='잔나비')
            db.session.add(album);db.session.flush()
            db.session.add_all([User(id=1,email='live@example.com',username='live',name='Test',password_hash='unused'),
                Song(id=1,provider='musicbrainz',external_id='39c40d9b-a35a-4c68-9da2-7471121c5f16',title='뜨거운 여름밤은 가고 남은 건 볼품없지만',artist='잔나비',album_id=album.id,duration_ms=243000)])
            db.session.commit()
        c=app.test_client()
        with c.session_transaction() as session:session['user_id']=1
        token=c.get('/api/session').json['csrf_token']
        with patch.object(musicbrainz.client,'get',side_effect=AssertionError('No MusicBrainz HTTP')):
            r=c.post('/api/songs/1/lyrics',json={},headers={'X-CSRFToken':token})
        assert r.status_code==200 and r.json['status']=='available',r.json
        detail=c.get('/api/songs/1').json
        assert detail['source_url']=='https://lrclib.net/api/get/13007700'
        assert detail['passages'] and any(any('\uac00'<=ch<='\ud7a3' for ch in p['text']) for p in detail['passages'])
        print('REAL LYRIC PASS:',detail['title'],'/',detail['artist'],'/ lines:',len(detail['passages']),'/ selected ID: 13007700',flush=True)
        with patch.object(lrclib.client,'get',side_effect=AssertionError('Stored lyrics must not query the provider')):
            assert c.post('/api/songs/1/lyrics',json={},headers={'X-CSRFToken':token}).json['from_database'] is True
        print('REAL PERSISTENCE PASS: saved lyrics open without either external provider')


if __name__=='__main__':main()
