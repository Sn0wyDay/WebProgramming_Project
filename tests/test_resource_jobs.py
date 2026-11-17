import json
import threading
import time
from unittest.mock import patch
import pytest
from backend import create_app,db
from backend.models import User,Song,UserSong
from backend.resource_jobs import JobStore,response
from backend.providers.http import ProviderError


@pytest.fixture
def app(tmp_path):
    import uuid
    app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'jobs_'+uuid.uuid4().hex,
                    'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'test.db'),
                    'RESOURCE_JOB_PATH':str(tmp_path/'jobs.db'),'ARTWORK_CACHE_PATH':str(tmp_path/'artwork')})
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id=n,email=f'u{n}@example.com',username=f'user{n}',name=f'User{n}',password_hash='unused') for n in (1,2)])
        db.session.add(Song(id=1,provider='fixture',external_id='one',title='Song',artist='Artist'));db.session.commit()
    yield app
    app.extensions['resource_queue'].close()


def client(app,uid=1):
    c=app.test_client()
    with c.session_transaction() as session:session['user_id']=uid
    return c


def submit(c,kind='lyrics',data=None):
    token=c.get('/api/session').json['csrf_token']
    return c.post('/api/songs/1/resources/'+kind,json=data or {},headers={'X-CSRFToken':token})


def wait(c,job_id):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        r=c.get('/api/resource-jobs/'+job_id)
        if r.json['status']!='pending':return r.json
        time.sleep(.02)
    pytest.fail('Worker did not finish')


def test_slow_resource_returns_immediately_and_two_accounts_share_one_job(app):
    first,other=client(app),client(app,2)
    entered,release=threading.Event(),threading.Event()
    def slow(job):
        entered.set();assert release.wait(3)
        return dict(status='missing',retry_after=300)
    with patch('backend.resource_jobs.perform',side_effect=slow) as network:
        try:
            r=submit(first)
            assert r.status_code==202 and entered.wait(2)
            second=submit(other)
            assert second.json['job_id']==r.json['job_id']
            assert first.get('/api/home').status_code==200
            assert first.get('/api/resource-jobs/'+r.json['job_id']).json['status']=='pending'
        finally:release.set()
        done=wait(first,r.json['job_id'])
        assert done['status']=='completed' and done['result']['status']=='missing'
        assert network.call_count==1
        repeated=submit(other)
        assert repeated.json['status']=='completed' and repeated.json['job_id']==r.json['job_id']
    with app.app_context():assert db.session.query(UserSong).count()==0


def test_resource_jobs_require_login_csrf_and_validated_options(app):
    c=app.test_client()
    assert submit(c).status_code==401
    assert c.get('/api/resource-jobs/'+'a'*32).status_code==401
    c=client(app)
    assert c.post('/api/songs/1/resources/lyrics',json={}).status_code==400
    for data in ({'refresh':'true'},{'candidate_id':True},{'candidate_id':-1},{'url':'https://other.test'},{'user_id':2}):
        assert submit(c,data=data).status_code==400
    assert submit(c,kind='unsupported').status_code==404
    assert submit(c,kind='reviews',data={'refresh':True}).status_code==400
    assert c.get('/api/resource-jobs/invalid').status_code==404


def test_lost_worker_is_recovered_and_stale_worker_cannot_overwrite(tmp_path):
    path=tmp_path/'jobs.db';store=JobStore(path)
    submitted=store.submit(1,'lyrics',{})
    old=store.claim();assert old['id']==submitted['id']
    restarted=JobStore(path)
    assert restarted.claim() is None
    with restarted.connection() as conn:conn.execute('UPDATE jobs SET lease=0')
    resumed=restarted.claim()
    assert resumed['id']==old['id'] and resumed['attempts']==2 and resumed['token']!=old['token']
    store.finish(old,dict(status='missing',retry_after=300))
    assert restarted.get(old['id'])['status']=='running'
    restarted.finish(resumed,dict(status='available',version_id=12))
    assert response(JobStore(path).get(old['id']))['result']['version_id']==12


def test_remaining_wait_is_not_reset_by_cached_job_result(tmp_path):
    store=JobStore(tmp_path/'jobs.db');submitted=store.submit(1,'reviews',{})
    running=store.claim();store.finish(running,dict(status='missing',retry_after=300))
    saved=store.get(submitted['id'])
    with patch('backend.resource_jobs.time.time',return_value=saved['reuse_until']-2):
        assert response(saved)['result']['retry_after']==2


def test_background_retry_is_bounded_and_respects_long_provider_cooldown(app):
    manager=app.extensions['resource_queue'];store=manager.store
    job=store.submit(1,'lyrics',{});running=store.claim()
    with patch('backend.resource_jobs.perform',side_effect=ProviderError('slow','provider_timeout',504,5)):
        manager.run(running)
        pending=store.get(job['id'])
        assert pending['status']=='queued' and pending['due']>=time.time()+4
        with store.connection() as conn:conn.execute('UPDATE jobs SET due=0')
        manager.run(store.claim())
        assert store.get(job['id'])['status']=='failed'
    long=store.submit(2,'lyrics',{});running=store.claim()
    with patch('backend.resource_jobs.perform',side_effect=ProviderError('limited','provider_rate_limited',503,90)):
        manager.run(running)
    result=response(store.get(long['id']))
    assert result['status']=='failed' and result['result']['retry_after']>=89


def test_queue_prioritizes_lyrics_and_caps_pending_work(tmp_path):
    store=JobStore(tmp_path/'jobs.db')
    store.submit(1,'artwork',{});store.submit(2,'reviews',{});lyrics=store.submit(3,'lyrics',{})
    assert store.claim()['id']==lyrics['id']
    for sid in range(4,129):store.submit(sid,'lyrics',{})
    with pytest.raises(ProviderError) as failure:store.submit(129,'lyrics',{})
    assert failure.value.code=='resource_busy'


def test_real_service_runs_in_worker_and_saved_passages_bypass_the_queue(app):
    from backend.providers import lrclib
    from backend.models import LyricVersion,Passage
    c=client(app)
    row=dict(id=77,trackName='Song',artistName='Artist',duration=100,plainLyrics='구절 A\n구절 B')
    with patch.object(lrclib.client,'get',return_value=row) as network:
        pending=submit(c)
        result=wait(c,pending.json['job_id'])
        assert result['status']=='completed' and result['result']['status']=='available'
        assert network.call_count==1
    with patch.object(lrclib.client,'get',side_effect=AssertionError('No HTTP for saved passages')):
        fast=submit(c)
        assert fast.status_code==200 and fast.json['result']['from_database']
        detail=c.get('/api/songs/1').json
        assert len(detail['passages'])==2 and detail['passages'][0]['text']=='구절 A'
    with app.app_context():
        assert db.session.query(LyricVersion).count()==1 and db.session.query(Passage).count()==2
        assert db.session.query(UserSong).count()==0


def test_second_lost_worker_reports_interruption_instead_of_loading_forever(tmp_path):
    store=JobStore(tmp_path/'jobs.db');first=store.submit(1,'lyrics',{})
    store.claim()
    with store.connection() as conn:conn.execute('UPDATE jobs SET lease=0')
    store.claim()
    with store.connection() as conn:conn.execute('UPDATE jobs SET lease=0')
    assert store.claim() is None
    failed=response(store.get(first['id']))
    assert failed['status']=='failed' and failed['result']['code']=='resource_interrupted'
