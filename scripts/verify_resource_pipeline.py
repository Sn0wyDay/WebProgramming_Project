"""Opt-in real resource requests in a temporary database, separate from unit tests."""
import tempfile
import time
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from flask_migrate import upgrade
from backend import create_app,db
from backend.models import Song,Album,UserSong,Comment
from backend.providers.http import JsonClient
from backend.artwork_service import ImageClient


def send(client,path,data):
    token=client.get('/api/session').json['csrf_token']
    return client.post('/api'+path,json=data,headers={'X-CSRFToken':token})


def wait(client,job):
    deadline=time.monotonic()+120
    while job['status']=='pending' and time.monotonic()<deadline:
        time.sleep(.4)
        job=client.get('/api/resource-jobs/'+job['job_id']).json
    assert job['status']!='pending','Resource queue did not finish'
    return job.get('result',{})


def restart_check(config,image_url):
    restarted=create_app(config)
    try:
        client=restarted.test_client()
        with patch.object(JsonClient,'open',side_effect=AssertionError('No external HTTP after restart')),patch.object(ImageClient,'open',side_effect=AssertionError('No image HTTP after restart')):
            assert send(client,'/login',dict(identifier='check1',password='temporary-pass8')).status_code==200
            assert send(client,'/songs/1/resources/lyrics',{}).json['result']['from_database']
            assert send(client,'/songs/2/resources/reviews',{}).json['result']['from_database']
            assert send(client,'/songs/1/resources/artwork',{}).json['result']['local_cached']
            assert client.get(image_url).status_code==200
        with restarted.app_context():
            assert db.session.query(UserSong).count()==0 and db.session.query(Comment).count()==0
        print('REAL RESTART PASS: fresh process reused lyrics, review and cover with external HTTP disabled; personal records unchanged',flush=True)
    finally:restarted.extensions['resource_queue'].close()


def main():
    with tempfile.TemporaryDirectory(prefix='re-resource-check-') as folder:
        config={'TESTING':True,'SECRET_KEY':'temporary-check','SESSION_SQLALCHEMY_TABLE':'resource_live_sessions',
                'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(Path(folder)/'catalog.db'),
                'RESOURCE_JOB_PATH':str(Path(folder)/'jobs.db'),'PROVIDER_CACHE_PATH':str(Path(folder)/'providers.db'),
                'ARTWORK_CACHE_PATH':str(Path(folder)/'artwork'),'ARTWORK_DOWNLOAD_ENABLED':True}
        app=create_app(config)
        with app.app_context():
            upgrade(directory=str(Path(__file__).resolve().parents[1]/'migrations'))
            db.session.add_all([
                Album(id=1,provider='musicbrainz',external_id='78429df2-86f4-432f-ac0d-28ee2991573e',title='Hospital',artist='Redoor'),
                Album(id=2,provider='musicbrainz',external_id='2cf9d49c-0101-4964-aa94-874e8d0d0f15',title='NO PAIN',artist='Silica Gel')])
            db.session.flush()
            db.session.add_all([
                Song(id=1,provider='musicbrainz',external_id='635b1cad-a0c2-465d-8208-fd9b897b9125',title='욕망주사기',artist='Redoor',duration_ms=263000,album_id=1),
                Song(id=2,provider='musicbrainz',external_id='d0ea4b20-5f4c-4e49-9fdb-e585d810d9da',title='NO PAIN',artist='Silica Gel',duration_ms=221000,album_id=2)])
            db.session.commit()
        first,other=app.test_client(),app.test_client()
        for index,client in enumerate((first,other),1):
            account=dict(email=f'check{index}@example.invalid',username=f'check{index}',name=f'Check {index}',password='temporary-pass8')
            assert send(client,'/register',account).status_code==201
            assert send(client,'/login',dict(identifier=account['username'],password=account['password'])).status_code==200
        try:
            started=time.monotonic()
            job=send(first,'/songs/1/resources/lyrics',{}).json
            duplicate=send(other,'/songs/1/resources/lyrics',{}).json
            assert duplicate['job_id']==job['job_id']
            print('REAL QUEUE PASS: two accounts share one job; submission seconds:',round(time.monotonic()-started,3),flush=True)
            result=wait(first,job)
            assert result.get('status')=='available',result
            detail=other.get('/api/songs/1').json
            assert detail['lyrics_title']=='Syringe' and len(detail['passages'])>5
            print('REAL LYRICS PASS: verified alias / Syringe /',len(detail['passages']),'passages',flush=True)
            review=wait(first,send(first,'/songs/2/resources/reviews',{}).json)
            assert review.get('status')=='available',review
            assert any(row['source']=='IZM' and row['author'] and row['article_type']=='review' for row in review['reviews'])
            print('REAL REVIEW PASS:',review['reviews'][0]['title'],'/',review['reviews'][0]['author'],flush=True)
            cover=wait(first,send(first,'/songs/1/resources/artwork',{}).json)
            assert cover.get('status')=='available' and cover.get('local_cached'),cover
            image=first.get(cover['image'])
            assert image.status_code==200 and image.content_type.startswith('image/') and len(image.data)>100
            print('REAL COVER PASS: local file /',len(image.data),'bytes',flush=True)
        finally:app.extensions['resource_queue'].close()
        command='import json,sys; from scripts.verify_resource_pipeline import restart_check; restart_check(json.loads(sys.argv[1]),sys.argv[2])'
        subprocess.run([sys.executable,'-c',command,json.dumps(config),cover['image']],check=True)
        if '--serve' in sys.argv:
            print('Temporary browser check: http://127.0.0.1:5003 / check1 / temporary-pass8',flush=True)
            command='import json,sys; from backend import create_app; create_app(json.loads(sys.argv[1])).run(host="127.0.0.1",port=5003)'
            subprocess.run([sys.executable,'-c',command,json.dumps(config)],check=True)


if __name__=='__main__':main()
