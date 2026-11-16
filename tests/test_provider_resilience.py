import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from email.utils import format_datetime
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
import pytest
from flask import Flask,g
from backend.providers.cache import DiskCache
from backend.providers.http import JsonClient,ProviderError,retry_seconds

BASE='https://provider.test'

def response(value):return BytesIO(json.dumps(value).encode())

def test_disk_cache_survives_client_restart_without_network(tmp_path):
    path=tmp_path/'cache.db'
    with patch('backend.providers.http.urlopen',return_value=response({'items':['real-response']})) as network:
        assert JsonClient(BASE,0,path).get('/search',{'q':'same'})=={'items':['real-response']}
        assert JsonClient(BASE,0,path).get('/search',{'q':'same'})=={'items':['real-response']}
        assert network.call_count==1


def test_failure_serves_stale_with_explicit_provenance(tmp_path):
    path=tmp_path/'cache.db';store=DiskCache(path)
    store.write(BASE+'/search',{'items':['previous-response']},-1,3600)
    error=HTTPError(BASE,503,'busy',{'Retry-After':'60'},None)
    app=Flask(__name__)
    with app.test_request_context(),patch('backend.providers.http.urlopen',side_effect=error) as network:
        result=JsonClient(BASE,0,path).get('/search')
        assert result=={'items':['previous-response']}
        assert g.provider_status['mode']=='stale' and g.provider_status['warnings']
        assert network.call_count==1
        # Another client/process must respect the persisted cooldown too.
        assert JsonClient(BASE,0,path).get('/search')==result
        assert network.call_count==1


def test_uncached_failure_cooldown_persists_and_returns_retry_after(tmp_path):
    path=tmp_path/'cache.db';error=HTTPError(BASE,429,'limited',{'Retry-After':'90'},None)
    with patch('backend.providers.http.urlopen',side_effect=error) as network:
        for _ in range(2):
            with pytest.raises(ProviderError) as failed:JsonClient(BASE,0,path).get('/uncached')
            assert failed.value.code=='provider_rate_limited'
            assert 88<=failed.value.retry_after<=90
        assert network.call_count==1


def test_transport_failure_retries_once_and_never_claims_success():
    with patch('backend.providers.http.urlopen',side_effect=TimeoutError),patch('backend.providers.http.time.sleep') as sleep:
        with pytest.raises(ProviderError) as failed:JsonClient(BASE,0).get('/timeout')
        assert failed.value.code=='provider_timeout'
        from backend.providers import http
        assert http.urlopen.call_count==2


def test_two_clients_share_lease_and_single_response(tmp_path):
    path=tmp_path/'cache.db';DiskCache(path)
    started=threading.Event();release=threading.Event()
    def network(*args,**kwargs):
        started.set();assert release.wait(2)
        return response({'items':['one']})
    with patch('backend.providers.http.urlopen',side_effect=network) as network_mock,ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(JsonClient(BASE,0,path).get,'/same')
        assert started.wait(2)
        second=pool.submit(JsonClient(BASE,0,path).get,'/same')
        release.set()
        assert first.result(timeout=3)==second.result(timeout=3)=={'items':['one']}
        assert network_mock.call_count==1


def test_expired_outside_stale_window_is_not_used(tmp_path):
    path=tmp_path/'cache.db'
    DiskCache(path).write(BASE+'/expired',{'items':['too-old']},-10,-1)
    with patch('backend.providers.http.urlopen',side_effect=HTTPError(BASE,503,'busy',{},None)):
        with pytest.raises(ProviderError):JsonClient(BASE,0,path).get('/expired')


def test_cache_filled_just_before_lease_does_not_repeat_request(tmp_path):
    path=tmp_path/'cache.db';DiskCache(path)
    reserve=DiskCache.reserve
    def filled_between_read_and_reserve(store,*args,**kwargs):
        result=reserve(store,*args,**kwargs)
        store.write(BASE+'/race',{'items':['already completed']},60,60)
        return result
    with patch.object(DiskCache,'reserve',filled_between_read_and_reserve),patch('backend.providers.http.urlopen',side_effect=AssertionError('Duplicate request')):
        assert JsonClient(BASE,0,path).get('/race')=={'items':['already completed']}


def test_http_date_retry_after_is_honored():
    date=format_datetime(datetime.now(timezone.utc)+timedelta(seconds=120))
    assert 118<=retry_seconds(date)<=120
    assert retry_seconds('invalid')==30


def test_resolved_artist_alias_skips_failed_title_query_after_restart(tmp_path):
    from urllib.parse import urlparse,parse_qs
    from backend.providers import musicbrainz
    artist_id='8f3555a1-d928-434b-9f16-49b07866430d'
    recording_id='f4577607-3b91-4be2-89e8-5a8967af2bd4'
    def network(req,**kwargs):
        query=parse_qs(urlparse(req.full_url).query)['query'][0]
        if '/artist/' in req.full_url:return response({'artists':[{'id':artist_id,'name':'Redoor','aliases':[{'name':'리도어'}]}]})
        if query.startswith('arid:'):return response({'count':1,'recordings':[{'id':recording_id,'title':'우리아픈이야기','artist-credit':[{'name':'Redoor'}]}]})
        return response({'count':0,'recordings':[]})
    path=tmp_path/'cache.db'
    with patch.object(musicbrainz,'client',JsonClient(BASE,0,path)),patch('backend.providers.http.urlopen',side_effect=network):
        assert musicbrainz.search('리도어')['total']==1
    with DiskCache(path).connection() as conn:
        conn.execute("UPDATE responses SET expires=0,stale_until=0 WHERE value LIKE '%\"recordings\": []%'")
    token,_,_=DiskCache(path).reserve(BASE)
    DiskCache(path).release(BASE,token,300)
    with patch.object(musicbrainz,'client',JsonClient(BASE,0,path)),patch('backend.providers.http.urlopen',side_effect=AssertionError('No external request should be needed')):
        assert musicbrainz.search('리도어')['items'][0]['artist']=='Redoor'


def test_disk_cache_is_read_by_a_fresh_python_process(tmp_path):
    import subprocess,sys
    path=tmp_path/'restart.db'
    with patch('backend.providers.http.urlopen',return_value=response({'items':['persisted']})):
        assert JsonClient(BASE,0,path).get('/restart')=={'items':['persisted']}
    script="""
import sys
from unittest.mock import patch
from backend.providers.http import JsonClient
with patch('backend.providers.http.urlopen',side_effect=AssertionError('No HTTP expected')):
    assert JsonClient('https://provider.test',0,sys.argv[1]).get('/restart')=={'items':['persisted']}
print('restart cache ok')
"""
    result=subprocess.run([sys.executable,'-c',script,str(path)],text=True,capture_output=True,timeout=5)
    assert result.returncode==0,result.stderr
    assert 'restart cache ok' in result.stdout
