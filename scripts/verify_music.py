"""Opt-in REAL external integration check; never inserts into the user's DB.
Run: .venv/bin/python -m scripts.verify_music
"""
import tempfile
from pathlib import Path
from flask_migrate import upgrade
from backend import create_app


def main():
    with tempfile.TemporaryDirectory(prefix='reverse-live-') as folder:
        app=create_app({'TESTING':True,'SECRET_KEY':'temporary-live-check','SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(Path(folder)/'live.db')})
        with app.app_context():
            upgrade(directory=str(Path(__file__).resolve().parents[1]/'migrations'))
        c=app.test_client()
        def send(path,data):
            token=c.get('/api/session').json['csrf_token']
            return c.post('/api'+path,json=data,headers={'X-CSRFToken':token})
        assert send('/register',dict(email='live@example.com',username='live',name='live',password='testpass8')).status_code==201
        assert send('/login',dict(identifier='live',password='testpass8')).status_code==200
        r=c.get('/api/catalog/search',query_string={'q':'밤편지'})
        assert r.status_code==200,r.json
        item=next(i for i in r.json['items'] if i['artist']=='IU' and i['title']=='밤편지')
        r=send('/catalog/import',{'external_id':item['external_id']})
        assert r.status_code==200,r.json
        sid=r.json['id']
        assert send('/catalog/import',{'external_id':item['external_id']}).json['id']==sid
        r=send(f'/songs/{sid}/lyrics',{})
        assert r.status_code==200 and r.json['status']=='available',r.json
        detail=c.get(f'/api/songs/{sid}').json
        assert any(any('\uac00'<=ch<='\ud7a3' for ch in p['text']) for p in detail['passages'])
        r=send('/comments',dict(passage_id=detail['passages'][0]['id'],text='실제 연동 검증용 기록',visibility='private'))
        assert r.status_code==201,r.json
        assert len(c.get(f'/api/songs/{sid}/comments').json['items'])==1
        print('REAL API PASS: MusicBrainz search/import/dedup + LRCLIB Korean lyric passages + comment persistence')
        print('Song:',detail['title'],'/',detail['artist'],'/ lyric lines:',len(detail['passages']))
        print('Lyrics source:',detail['source_url'])
        for query in ('아이유','Dynamite BTS','리도어'):
            r=c.get('/api/catalog/search',query_string={'q':query})
            assert r.status_code==200,r.json
            print('REAL SEARCH:',query,':',len(r.json['items']),'results')
            if query=='리도어':
                assert r.json['matched_artists']==['Redoor'] and r.json['total']>0
                item=next(i for i in r.json['items'] if i['title']=='Forever Has Always Been')
                imported=send('/catalog/import',{'external_id':item['external_id']})
                assert imported.status_code==200,imported.json
                lyric=send('/songs/'+str(imported.json['id'])+'/lyrics',{})
                assert lyric.status_code==200 and lyric.json['status']=='available',lyric.json
                print('REAL REDOOR PASS: Korean artist alias -> artist ID -> recording -> bilingual artist lyrics')
        # Verified Korean/English title pair, with artist/album/duration checks.
        imported=send('/catalog/import',{'external_id':'f4577607-3b91-4be2-89e8-5a8967af2bd4'})
        assert imported.status_code==200,imported.json
        sid=imported.json['id']
        lyric=send('/songs/'+str(sid)+'/lyrics',{})
        assert lyric.status_code==200 and lyric.json['status']=='available',lyric.json
        detail=c.get('/api/songs/'+str(sid)).json
        assert detail['title']=='우리아픈이야기' and detail['lyrics_title']=='Shadow of You'
        assert detail['lyrics_match']=='title_alias' and detail['passages']
        print('REAL TITLE ALIAS PASS: 우리아픈이야기 -> Shadow of You; lines:',len(detail['passages']))



if __name__=='__main__':
    main()
