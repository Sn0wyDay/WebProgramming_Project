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


def test_local_title_and_artist_filters_do_not_cross_fields(app):
    from backend.models import Song
    with app.app_context():
        db.session.add_all([
            Song(id=1,title='Echo',artist='Band A',provider='test',external_id='a'),
            Song(id=2,title='Another Song',artist='Echo',provider='test',external_id='b'),
        ])
        db.session.commit()
    c=client(app)
    for field,expected in [('all',[1,2]),('title',[1]),('artist',[2])]:
        r=c.get('/api/songs',query_string={'q':'Echo','field':field})
        assert [song['id'] for song in r.json['items']]==expected
    assert c.get('/api/songs?q=x&field=invalid').status_code==400
    assert submit(c,{'q':'Echo','field':['artist']}).status_code==400


def test_external_fields_have_separate_searches_and_cached_results(app):
    c=client(app)
    def upstream(path,params):
        assert path=='/recording/'
        q=params['query']
        title=q=='recording:("Echo")'
        assert title or q=='(artist:("Echo") OR artistname:("Echo"))'
        assert params['offset']==20
        return {'count':21,'recordings':[{'id':'00000000-0000-4000-8000-000000000001',
                'title':'Echo' if title else 'Another Song','artist-credit':[{'name':'Band A' if title else 'Echo'}]}]}
    with patch.object(musicbrainz.client,'get',side_effect=upstream) as calls:
        for field in ('title','artist'):
            assert c.get('/api/catalog/search',query_string={'q':'Echo','field':field,'page':2}).status_code==200
        for field,title in [('artist','Another Song'),('title','Echo')]:
            result=submit(c,{'q':'Echo','field':field,'page':2})
            assert result.json['status']=='completed' and result.json['result']['items'][0]['title']==title
        assert calls.call_count==2


def test_combined_search_requires_both_fields_and_matches_the_same_song(app):
    from backend.models import Song
    with app.app_context():
        for i, (title, artist) in enumerate([('눈사람','정승환'), ('눈사람','다른 가수'), ('다른 곡','정승환')], 1):
            db.session.add(Song(id=i, title=title, artist=artist, provider='test', external_id=str(i)))
        db.session.commit()
    c = client(app)
    params = {'field':'combined', 'q':'눈사람', 'artist':'정승환'}
    result = c.get('/api/songs', query_string=params)
    assert [song['id'] for song in result.json['items']] == [1]
    for invalid in ({'artist':'  '}, {'q':''}, {'artist':'a'*101}):
        data = {**params, **invalid}
        assert c.get('/api/songs', query_string=data).status_code == 400
        assert c.get('/api/catalog/search', query_string=data).status_code == 400
        assert submit(c, data).status_code == 400


def test_combined_alias_retry_and_cache_keep_artist_and_title(app):
    c = client(app)
    artist_id = '00000000-0000-4000-8000-000000000002'
    def upstream(path, params):
        if path == '/artist/':
            assert params['query'] == '"리도어"'
            return {'artists':[{'name':'Redoor', 'id':artist_id, 'aliases':[{'name':'리도어'}]}]}
        assert params['offset'] == 20
        assert 'recording:("Hospital")' in params['query']
        if 'arid:'+artist_id in params['query']:
            return {'recordings':[{'id':'00000000-0000-4000-8000-000000000001',
                                   'title':'Hospital', 'artist-credit':[{'name':'Redoor'}]}], 'count':21}
        assert ' AND ' in params['query'] and 'artist:("리도어")' in params['query']
        return {'recordings':[], 'count':0}

    params = {'q':'Hospital', 'artist':'리도어', 'field':'combined', 'page':2}
    with patch.object(musicbrainz.client, 'get', side_effect=upstream) as calls:
        result = c.get('/api/catalog/search', query_string=params)
        assert result.json['items'][0]['artist'] == 'Redoor'
        assert submit(c, params).json['result']['items'] == result.json['items']
        assert calls.call_count == 3
        with app.app_context():
            assert musicbrainz.cached_search('Hospital', 2, 'combined', '다른 가수') is None
