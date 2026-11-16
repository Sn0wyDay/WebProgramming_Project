"""Real multi-source lookup for Redoor in an isolated temporary database.
Run: .venv/bin/python -m scripts.verify_editorial_sources
"""
import tempfile
from pathlib import Path
from unittest.mock import patch
from flask_migrate import upgrade
from backend import create_app,db
from backend.models import User,Song,Album,Review
from backend.providers import izm,hellokpop


def main():
    with tempfile.TemporaryDirectory(prefix='reverse-editorial-') as folder:
        app=create_app({'TESTING':True,'SECRET_KEY':'live','SESSION_SQLALCHEMY_TABLE':'live_editorial_sessions',
                        'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(Path(folder)/'test.db'),
                        'PROVIDER_CACHE_PATH':str(Path(folder)/'providers.db')})
        with app.app_context():
            upgrade(directory=str(Path(__file__).resolve().parents[1]/'migrations'))
            a=Album(provider='musicbrainz',external_id='733405be-94ce-4f1d-9475-9c12c4e3be10',title='Hospital',artist='Redoor')
            db.session.add(a);db.session.flush()
            db.session.add_all([User(id=1,email='live@example.com',username='live',name='Test',password_hash='unused'),
                Song(id=1,provider='musicbrainz',external_id='635b1cad-a0c2-465d-8208-fd9b897b9125',title='욕망주사기',artist='Redoor',album_id=a.id,duration_ms=263000)])
            db.session.commit()
        c=app.test_client()
        with c.session_transaction() as session:session['user_id']=1
        token=c.get('/api/session').json['csrf_token']
        r=c.post('/api/songs/1/reviews',json={},headers={'X-CSRFToken':token})
        assert r.status_code==200 and r.json['status']=='available',r.json
        row=r.json['reviews'][0]
        assert row['article_type']=='selection' and row['author']=='Jung Bae'
        assert row['url']=='https://www.hellokpop.com/review/2025-in-review-day-3-the-honorable-mentions/'
        assert '욕망주사기' in row['introduction'] and 'Rock and Alternative' in row['introduction']
        print('REAL SELECTION PASS:',row['author'],'/',row['title'],'/',row['article_type'],flush=True)
        with app.app_context():assert db.session.query(Review).count()==1
        with patch.object(izm,'find',side_effect=AssertionError('No network')),patch.object(hellokpop,'find',side_effect=AssertionError('No network')):
            assert c.post('/api/songs/1/reviews',json={},headers={'X-CSRFToken':token}).json['from_database']
            assert c.get('/api/songs/1').json['reviews'][0]['article_type']=='selection'
        print('REAL PERSISTENCE PASS: selection type and matching entry saved without changing user records')


if __name__=='__main__':main()
