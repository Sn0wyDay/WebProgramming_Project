"""Opt-in REAL IZM integration check in a disposable SQLite DB.

Run: .venv/bin/python -m scripts.verify_reviews
Uses public catalog identifiers, never inserts into a real user's database.
"""
import tempfile
from pathlib import Path
from flask_migrate import upgrade
from backend import create_app,db
from backend.models import Album,Song,User,Review


def main():
    with tempfile.TemporaryDirectory(prefix='reverse-reviews-') as folder:
        app=create_app({'TESTING':True,'SECRET_KEY':'temporary-live-check','SESSION_SQLALCHEMY_TABLE':'live_review_sessions',
                        'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(Path(folder)/'live.db'),
                        'PROVIDER_CACHE_PATH':str(Path(folder)/'providers.db')})
        with app.app_context():
            upgrade(directory=str(Path(__file__).resolve().parents[1]/'migrations'))
            album=Album(provider='musicbrainz',external_id='2cf9d49c-0101-4964-aa94-874e8d0d0f15',title='NO PAIN',artist='Silica Gel')
            db.session.add(album);db.session.flush()
            db.session.add_all([User(id=1,email='live@example.com',username='live',name='Live',password_hash='unused'),
                Song(id=1,provider='musicbrainz',external_id='cf3b2fd9-e6cc-49bf-abf3-63a3af75a6dc',title='밤편지',artist='IU'),
                Song(id=2,provider='musicbrainz',external_id='d0ea4b20-5f4c-4e49-9fdb-e585d810d9da',title='NO PAIN',artist='Silica Gel',album_id=album.id)])
            db.session.commit()
        c=app.test_client()
        with c.session_transaction() as session:session['user_id']=1
        for sid in (1,2):
            token=c.get('/api/session').json['csrf_token']
            r=c.post(f'/api/songs/{sid}/reviews',json={},headers={'X-CSRFToken':token})
            assert r.status_code==200 and r.json['status']=='available',r.json
            row=r.json['reviews'][0]
            assert row['url'].startswith('https://www.izm.co.kr/posts?id=')
            assert len(row['introduction'])<=111 and len(row['introduction'].split())<=20
            if sid==1:assert row['title']=='밤편지' and row['author']=='홍은솔' and row['kind']=='song'
            else:assert row['title']=='Power Andre 99' and row['author']=='김태훈' and row['kind']=='album_track'
            print('REAL REVIEW PASS:',row['title'],'/',row['author'],'/',row['kind'],'/',row['url'],flush=True)
        with app.app_context():assert db.session.query(Review).count()==2
        # Provider-disabled read proves stored excerpts remain available.
        from unittest.mock import patch
        with patch('backend.providers.izm.find',side_effect=AssertionError('No network')):
            assert c.get('/api/songs/2').json['reviews'][0]['title']=='Power Andre 99'
        print('REAL PERSISTENCE PASS: saved reviews readable with provider disabled')


if __name__=='__main__':main()
