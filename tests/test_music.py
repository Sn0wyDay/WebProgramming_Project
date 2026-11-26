import json
from io import BytesIO
from unittest.mock import patch
import pytest
from backend import create_app, db
from backend.models import Song, Comment, Passage, LyricVersion
from backend.providers import musicbrainz, lrclib
from backend.providers.http import JsonClient, ProviderError

MBID='cf3b2fd9-e6cc-49bf-abf3-63a3af75a6dc'
META=dict(external_id=MBID,provider='musicbrainz',title='밤편지',artist='IU',album=None,album_id=None,duration_ms=253000)


def search_response(rows):
    return lambda path,params=None:rows if path=='/api/search' else None

@pytest.fixture(autouse=True)
def isolate_provider_memory():
    musicbrainz.client.cache.clear()
    lrclib.client.cache.clear()
    yield
    musicbrainz.client.cache.clear()
    lrclib.client.cache.clear()

@pytest.fixture(scope='module')
def app(tmp_path_factory):
    app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'music_test_sessions','SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path_factory.mktemp('music')/'test.db')})
    with app.app_context(): db.create_all()
    return app

def send(client,path,method='POST',data=None):
    token=client.get('/api/session').json['csrf_token']
    return client.open('/api'+path,method=method,json={} if data is None else data,headers={'X-CSRFToken':token})

def test_import_and_immutable_lyrics(app):
    c=app.test_client()
    assert send(c,'/register',data=dict(email='music@example.com',username='music',name='music',password='password8')).status_code==201
    assert send(c,'/login',data=dict(identifier='music',password='password8')).status_code==200
    assert send(c,'/catalog/import',data={'external_id':'https://evil.test'}).status_code==400
    with patch.object(musicbrainz,'lookup',return_value=META) as lookup:
        sid=send(c,'/catalog/import',data={'external_id':MBID,'title':'untrusted'}).json['id']
        assert send(c,'/catalog/import',data={'external_id':MBID}).json['id']==sid
        assert lookup.call_count==1
    detail=c.get('/api/songs/'+str(sid)).json
    assert detail['title']=='밤편지' and detail['lyrics_status']=='unqueried'
    original=dict(text='테스트 구절 A\n테스트 구절 B',source_url='https://lrclib.net/api/get/1')
    with patch.object(lrclib,'find',return_value=original):
        v1=send(c,f'/songs/{sid}/lyrics').json['version_id']
        assert send(c,f'/songs/{sid}/lyrics').json['version_id']==v1
    with patch.object(lrclib,'find',side_effect=AssertionError('Saved lyrics must not call an external API')):
        assert send(c,f'/songs/{sid}/lyrics').json['from_database'] is True
    p=c.get('/api/songs/'+str(sid)).json['passages'][0]
    cid=send(c,'/comments',data=dict(passage_id=p['id'],text='original comment',visibility='private')).json['id']
    changed=dict(text='테스트 구절 B\n테스트 구절 A',source_url='https://lrclib.net/api/get/2')
    with patch.object(lrclib,'find',return_value=changed):
        assert send(c,f'/songs/{sid}/lyrics',data={'refresh':True}).json['version_id']!=v1
    assert c.get('/api/comments/'+str(cid)).json['quote']=='테스트 구절 A'
    assert c.get(f'/api/songs/{sid}/comments').json['items'][0]['passage_id']==p['id']
    with patch.object(lrclib,'find',return_value=None), patch.object(musicbrainz,'exact_artists',return_value=[]), patch.object(musicbrainz,'recording_titles',return_value=[]):
        assert send(c,f'/songs/{sid}/lyrics',data={'refresh':True}).json['refresh_failed'] is True
    assert c.get('/api/comments/'+str(cid)).json['quote']=='테스트 구절 A'
    with patch.object(lrclib,'find',side_effect=ProviderError('timeout','provider_timeout',504)):
        r=send(c,f'/songs/{sid}/lyrics',data={'refresh':True})
        assert r.status_code==200 and r.json['refresh_failed'] is True and r.json['from_database'] is True
    with app.app_context():
        assert db.session.query(Song).count()==1
        assert db.session.query(LyricVersion).count()==2
        assert db.session.query(Passage).count()==4


def test_lyrics_matches_identity_and_duration():
    row=dict(id=1,trackName='Through the Night (밤편지)',artistName='IU',duration=253,plainLyrics='테스트',instrumental=False)
    with patch.object(lrclib.client,'get',side_effect=search_response([row])):
        assert lrclib.find('밤편지','IU',253000)['external_id']=='1'
        assert lrclib.find('밤편지','다른 가수',253000) is None
        assert lrclib.find('밤편지','IU',100000) is None
        assert lrclib.find('다른 노래','IU',253000) is None
        assert lrclib.find('밤편지 (Live)','IU',253000) is None


def test_http_cache_and_duplicate_request():
    client=JsonClient('https://example.test',0)
    with patch('backend.providers.http.urlopen',return_value=BytesIO(json.dumps({'ok':True}).encode())) as transport:
        assert client.get('/test')=={'ok':True}
        assert client.get('/test')=={'ok':True}
        assert transport.call_count==1


def test_provider_failure_is_not_empty_search():
    with patch.object(musicbrainz.client,'get',return_value={'bad':'response'}):
        with pytest.raises(ProviderError): musicbrainz.search('IU')
    with patch.object(musicbrainz.client,'get',return_value={'recordings':[],'count':0,'artists':[]}):
        assert musicbrainz.search('unknown')['items']==[]


def test_korean_artist_alias_search_and_paging():
    artist_id='8f3555a1-d928-434b-9f16-49b07866430d'
    record={'id':MBID,'title':'Forever Has Always Been','artist-credit':[{'name':'Redoor'}]}
    artist={'id':artist_id,'name':'Redoor','aliases':[{'name':'리도어'}]}
    def response(path,params):
        if path=='/artist/': return {'artists':[artist]}
        if params['query']=='arid:'+artist_id:
            assert params['offset']==20
            return {'recordings':[record],'count':28}
        return {'recordings':[],'count':0}
    with patch.object(musicbrainz.client,'get',side_effect=response):
        result=musicbrainz.search('리도어',page=2)
        assert result['total']==28 and result['pages']==2
        assert result['items'][0]['artist']=='Redoor'
        assert result['matched_artists']==['Redoor']


def test_no_fuzzy_artist_substitution():
    with patch.object(musicbrainz.client,'get',return_value={'recordings':[],'count':0,'artists':[{'id':MBID,'name':'unrelated','aliases':[]}]}):
        assert musicbrainz.search('리도어')['items']==[]


def test_lyrics_bilingual_artist_requires_verified_alias():
    row=dict(id=1,trackName='Forever Has Always Been',artistName='Redoor 리도어',duration=240,plainLyrics='테스트',instrumental=False)
    with patch.object(lrclib.client,'get',side_effect=search_response([row])):
        assert lrclib.find('Forever Has Always Been','Redoor',240000) is None
        assert lrclib.find('Forever Has Always Been','Redoor',240000,aliases=['리도어'])['external_id']=='1'
        assert lrclib.find('Forever Has Always Been','different',240000,aliases=['다른 가수']) is None


def test_translated_title_requires_known_alias_and_album_duration():
    row=dict(id=37734953,trackName='Shadow of You',artistName='Redoor',albumName='Hospital - EP',duration=256,plainLyrics='테스트 가사')
    def response(path,params):
        if path=='/api/get':return None
        return [row] if params.get('track_name')=='Shadow of You' else []
    with patch.object(lrclib.client,'get',side_effect=response):
        assert lrclib.find('우리아픈이야기','Redoor',256000) is None
        assert lrclib.find('우리아픈이야기','Redoor',256000,title_aliases=['Shadow of You'],album='Hospital')['external_id']=='37734953'
        assert lrclib.find('우리아픈이야기','Redoor',256000,title_aliases=['Shadow of You'],album='Different') is None
        assert lrclib.find('우리아픈이야기','Redoor',260000,title_aliases=['Shadow of You'],album='Hospital') is None
        assert lrclib.find('우리아픈이야기','Redoor',None,title_aliases=['Shadow of You'],album='Hospital') is None


def test_candidates_are_not_automatic_translation():
    row=dict(id=1,trackName='Unknown English',artistName='Redoor',albumName='Hospital',duration=256,plainLyrics='테스트 가사')
    with patch.object(lrclib.client,'get',side_effect=search_response([row])):
        assert lrclib.find('다른 한글 제목','Redoor',256000) is None
        assert lrclib.candidates('다른 한글 제목','Redoor','Hospital',256000)[0]['external_id']=='1'
        assert lrclib.candidates('다른 한글 제목','Other Artist','Hospital',256000)==[]
        assert lrclib.candidates('다른 한글 제목','Redoor','Other Album',256000)==[]
        assert lrclib.candidates('다른 한글 제목 (Live)','Redoor','Hospital',256000)==[]


def test_unverified_titles_need_explicit_candidate_selection(app):
    from backend.models import Album
    with app.app_context():
        album=Album(provider='fixture',external_id='unknown',title='Test Album',artist='Test Artist')
        db.session.add(album);db.session.flush()
        s=Song(provider='fixture',external_id='unknown',title='한국어 제목',artist='Test Artist',album_id=album.id,duration_ms=100000)
        db.session.add(s);db.session.commit();sid=s.id
    c=app.test_client()
    assert send(c,'/login',data=dict(identifier='music',password='password8')).status_code==200
    row=dict(id=77,trackName='English title',artistName='Test Artist',albumName='Test Album',duration=100,plainLyrics='후보 테스트')
    def response(path,params):
        if path=='/api/get':return None
        return [row] if params.get('q') else []
    with patch.object(lrclib.client,'get',side_effect=response):
        r=send(c,f'/songs/{sid}/lyrics')
        assert r.json['status']=='candidates' and r.json['candidates'][0]['id']==77
        assert c.get(f'/api/songs/{sid}').json['lyrics_status']=='unmatched'
        assert send(c,f'/songs/{sid}/lyrics',data={'candidate_id':88}).status_code==400
        assert send(c,f'/songs/{sid}/lyrics',data={'candidate_id':77}).json['status']=='available'
        detail=c.get(f'/api/songs/{sid}').json
        assert detail['lyrics_title']=='English title' and detail['lyrics_match']=='user_confirmed'
        assert send(c,f'/songs/{sid}/lyrics',data={'candidate_id':77}).status_code==200
        with app.app_context():
            assert db.session.query(LyricVersion).filter_by(song_id=sid).count()==1


def test_verified_title_rule_is_bound_to_identity():
    from backend.music import alternate_titles
    song=Song(provider='musicbrainz',external_id='f4577607-3b91-4be2-89e8-5a8967af2bd4',title='우리아픈이야기',artist='Redoor',duration_ms=256000)
    with patch.object(musicbrainz,'recording_titles',return_value=[]):
        assert alternate_titles(song,'Hospital')==['Shadow of You']
        assert alternate_titles(song,'Other Album')==[]
        song.artist='Other Artist'
        assert alternate_titles(song,'Hospital')==[]


def lyric_test_client(app,name):
    c=app.test_client()
    assert send(c,'/register',data=dict(email=name+'@example.com',username=name,name=name,password='testpass8')).status_code==201
    assert send(c,'/login',data=dict(identifier=name,password='testpass8')).status_code==200
    return c


def lyric_test_song(app,title,artist='Redoor',external_id=None,album_title='Hospital',duration=263000,provider='fixture'):
    import uuid
    from backend.models import Album
    with app.app_context():
        album=Album(provider='fixture',external_id=uuid.uuid4().hex,title=album_title,artist=artist)
        db.session.add(album);db.session.flush()
        s=Song(provider=provider,external_id=external_id or uuid.uuid4().hex,title=title,artist=artist,album_id=album.id,duration_ms=duration)
        db.session.add(s);db.session.commit()
        return s.id


def test_syringe_resolves_without_musicbrainz_network(app):
    c=lyric_test_client(app,'lyric_syringe')
    sid=lyric_test_song(app,'욕망주사기',external_id='635b1cad-a0c2-465d-8208-fd9b897b9125',provider='musicbrainz')
    row=dict(id=35646335,trackName='Syringe',artistName='Redoor',albumName='Hospital - EP',duration=264,plainLyrics='검증용 가사')
    def response(path,params):
        assert params.get('q') or params.get('track_name'),'LRCLIB requires q or track_name'
        if path=='/api/get':return row if params.get('track_name')=='Syringe' else None
        return [row] if params.get('track_name')=='Syringe' else []
    with patch.object(musicbrainz.client,'get',side_effect=ProviderError('MB unavailable','provider_rate_limited',503,30)) as mb,patch.object(lrclib.client,'get',side_effect=response):
        r=send(c,f'/songs/{sid}/lyrics')
        assert r.status_code==200 and r.json['status']=='available'
        assert mb.call_count==0
        detail=c.get(f'/api/songs/{sid}').json
        assert detail['lyrics_title']=='Syringe' and detail['lyrics_status']=='available'


def test_candidate_query_satisfies_provider_contract_even_when_metadata_down(app):
    c=lyric_test_client(app,'lyric_candidate')
    sid=lyric_test_song(app,'번역 미확인 제목',provider='musicbrainz')
    row=dict(id=12345,trackName='Unverified English',artistName='Redoor',albumName='Hospital',duration=263,plainLyrics='후보 검증')
    def response(path,params):
        assert params.get('q') or params.get('track_name')
        if path=='/api/get':return None
        return [row] if params.get('q')=='Redoor Hospital' else []
    with patch.object(musicbrainz.client,'get',side_effect=AssertionError('No MusicBrainz HTTP needed')) as mb,patch.object(lrclib.client,'get',side_effect=response):
        r=send(c,f'/songs/{sid}/lyrics')
        assert r.status_code==200 and r.json['status']=='candidates'
        assert r.json['candidates'][0]['id']==12345
        assert mb.call_count==0
        assert c.get(f'/api/songs/{sid}').json['passages']==[]


def test_instrumental_is_explained_without_external_lookup(app):
    c=lyric_test_client(app,'lyric_instrumental')
    sid=lyric_test_song(app,'Tik Tak Tok (instrumental)',artist='Silica Gel')
    with patch('backend.lyric_service.fetch_lyrics',side_effect=AssertionError('Instrumentals must not fetch lyrics')):
        r=send(c,f'/songs/{sid}/lyrics')
        assert r.status_code==200 and r.json['status']=='instrumental'
        assert '반주' in r.json['message']
        assert c.get(f'/api/songs/{sid}').json['lyrics_status']=='instrumental'


def test_temporary_failure_is_not_missing_and_cooldown_is_preserved(app):
    from backend.models import LyricLookup
    from datetime import datetime,timedelta
    c=lyric_test_client(app,'lyric_error')
    sid=lyric_test_song(app,'오류와 미등록 구분')
    with patch.object(lrclib,'find',side_effect=ProviderError('temporary','provider_timeout',504)) as provider:
        r=send(c,f'/songs/{sid}/lyrics')
        assert r.status_code==504 and r.json['retry_after']==3
        assert c.get(f'/api/songs/{sid}').json['lyrics_status']=='error'
        repeated=send(c,f'/songs/{sid}/lyrics',data={'refresh':True})
        assert repeated.status_code==503 and repeated.json['retry_after']>0
        assert provider.call_count==1
    with app.app_context():
        db.session.get(LyricLookup,sid).retry_at=datetime.utcnow()-timedelta(seconds=1);db.session.commit()
    result=dict(text='복구된 가사',source_url='https://lrclib.net/api/get/54321',title='오류와 미등록 구분')
    with patch.object(lrclib,'find',return_value=result):
        assert send(c,f'/songs/{sid}/lyrics').json['status']=='available'
    with patch.object(lrclib,'find',side_effect=ProviderError('temporary','provider_timeout',504)):
        refreshed=send(c,f'/songs/{sid}/lyrics',data={'refresh':True})
        assert refreshed.status_code==200 and refreshed.json['from_database'] is True
        assert refreshed.json['refresh_failed'] is True and refreshed.json['message']
        assert c.get(f'/api/songs/{sid}').json['lyrics_status']=='available'


def test_confirmed_no_match_is_distinct_and_cached(app):
    c=lyric_test_client(app,'lyric_missing')
    sid=lyric_test_song(app,'일치 결과 없는 곡')
    with patch.object(lrclib,'find',return_value=None) as find,patch.object(lrclib,'candidates',return_value=[]) as candidates:
        first=send(c,f'/songs/{sid}/lyrics')
        assert first.status_code==200 and first.json['status']=='missing'
        assert '표기' in first.json['message']
        assert c.get(f'/api/songs/{sid}').json['lyrics_status']=='missing'
        assert send(c,f'/songs/{sid}/lyrics').json['cached'] is True
        refreshed=send(c,f'/songs/{sid}/lyrics',data={'refresh':True})
        assert refreshed.json['cached'] is True and refreshed.json['retry_after']>0
        assert c.get(f'/api/songs/{sid}').json['lyrics_retry_after']>0
        assert find.call_count==1 and candidates.call_count==1


@pytest.mark.parametrize('title,expected',[
    ('Tik Tak Tok (instrumental)',True),('Tik Tak Tok (Inst.)',True),
    ('Instrumental Love',False),('Tik Tak Tok (feat. So!YoON!)',False)
])
def test_only_version_qualifiers_mark_instrumental(title,expected):
    from backend.providers.versions import is_instrumental
    assert is_instrumental(title)==expected


def test_manual_retry_reaches_provider_while_automatic_miss_is_cached(app):
    from datetime import timedelta
    from backend.lyric_service import now
    from backend.models import LyricLookup
    c=lyric_test_client(app,'manual_miss')
    sid=lyric_test_song(app,'수동 재조회')
    with patch.object(lrclib,'find',return_value=None),patch.object(lrclib,'candidates',return_value=[]):
        assert send(c,f'/songs/{sid}/lyrics').json['retry_after']==8
    with app.app_context():
        db.session.get(LyricLookup,sid).checked_at=now()-timedelta(seconds=9)
        db.session.commit()
    detail=c.get(f'/api/songs/{sid}').json
    assert detail['lyrics_retry_after']==0 and detail['lyrics_auto_retry_after']>200
    with patch.object(lrclib,'find',return_value=dict(text='테스트',source_url='https://lrclib.net/api/get/77')) as lookup:
        assert send(c,f'/songs/{sid}/lyrics').json['cached']
        assert send(c,f'/songs/{sid}/lyrics',data={'refresh':True}).json['status']=='available'
        assert lookup.call_count==1
