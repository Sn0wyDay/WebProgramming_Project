import time
from unittest.mock import patch
import pytest
from backend import create_app,db
from backend.models import User
from backend.providers import musicbrainz
from backend.providers.cache import DiskCache
from backend.providers.http import JsonClient


@pytest.fixture
def app(tmp_path):
    import uuid
    app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'search_'+uuid.uuid4().hex,
                    'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'test.db'),
                    'RESOURCE_JOB_PATH':str(tmp_path/'jobs.db'),'PROVIDER_CACHE_PATH':str(tmp_path/'cache.db')})
    with app.app_context():
        db.create_all();db.session.add(User(id=1,email='search@example.com',username='search',name='Test',password_hash='unused'));db.session.commit()
    yield app
    app.extensions['resource_queue'].close()


def client(app):
    c=app.test_client()
    with c.session_transaction() as session:session['user_id']=1
    return c


def submit(c,data):
    token=c.get('/api/session').json['csrf_token']
    return c.post('/api/catalog/search-jobs',json=data,headers={'X-CSRFToken':token})


def test_cached_search_is_instant_and_stale_refresh_runs_only_in_background(app):
    data=dict(items=[dict(title='Song',artist='Artist')],page=1,pages=1,total=1)
    with app.app_context():musicbrainz.client.remember(musicbrainz.search_key('Artist',1),data)
    c=client(app)
    with patch.object(musicbrainz,'search',side_effect=AssertionError('No HTTP for fresh cache')):
        ready=submit(c,{'q':'Artist'})
        assert ready.status_code==200 and ready.json['result']['items']==data['items']
        assert ready.json['result']['_provider_status']['mode']=='cache'
    with DiskCache(app.config['PROVIDER_CACHE_PATH']).connection() as conn:conn.execute('UPDATE responses SET expires=0')
    with patch('backend.resource_jobs.perform',return_value={**data,'status':'available'}) as work:
        stale=submit(c,{'q':'Artist'})
        assert stale.status_code==200 and stale.json['result']['_provider_status']['mode']=='stale'
        deadline=time.monotonic()+2
        while not work.called and time.monotonic()<deadline:time.sleep(.01)
        assert work.call_count==1


def test_new_search_is_queued_and_request_validation_is_strict(app):
    c=client(app)
    for data in ({'q':''},{'q':3},{'q':'Song','page':True},{'q':'Song','page':101},{'q':'Song','url':'https://other.test'}):
        assert submit(c,data).status_code==400
    with patch('backend.resource_jobs.perform',return_value=dict(items=[],page=1,pages=0,total=0,status='missing',retry_after=300)) as work:
        pending=submit(c,{'q':'Unknown'})
        assert pending.status_code==202
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            done=c.get('/api/resource-jobs/'+pending.json['job_id']).json
            if done['status']=='completed':break
            time.sleep(.01)
        assert done['result']['items']==[] and work.call_count==1


def test_empty_search_snapshot_has_short_ttl_instead_of_a_day(tmp_path):
    client=JsonClient('https://provider.test',0,tmp_path/'cache.db')
    client.remember('search',dict(items=[],total=0))
    row=DiskCache(tmp_path/'cache.db').read('https://provider.testsnapshot:search')
    assert 299<=row['expires']-row['saved']<=301
    assert row['stale_until']==row['expires']
