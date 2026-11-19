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
    assert detail['title']=='밤편지' and detail['lyrics_status']=='missing'
    original=dict(text='테스트 구절 A\n테스트 구절 B',source_url='https://lrclib.net/api/get/1')
    with patch.object(lrclib,'find',return_value=original):
        v1=send(c,f'/songs/{sid}/lyrics').json['version_id']
        assert send(c,f'/songs/{sid}/lyrics').json['version_id']==v1
    p=c.get('/api/songs/'+str(sid)).json['passages'][0]
    cid=send(c,'/comments',data=dict(passage_id=p['id'],text='original comment',visibility='private')).json['id']
    changed=dict(text='테스트 구절 B\n테스트 구절 A',source_url='https://lrclib.net/api/get/2')
    with patch.object(lrclib,'find',return_value=changed):
        assert send(c,f'/songs/{sid}/lyrics').json['version_id']!=v1
    assert c.get('/api/comments/'+str(cid)).json['quote']=='테스트 구절 A'
    assert c.get(f'/api/songs/{sid}/comments').json['items'][0]['passage_id']==p['id']
    with patch.object(lrclib,'find',return_value=None), patch.object(musicbrainz,'exact_artists',return_value=[]), patch.object(musicbrainz,'recording_titles',return_value=[]):
        assert send(c,f'/songs/{sid}/lyrics').json['status']=='missing'
    assert c.get('/api/comments/'+str(cid)).json['quote']=='테스트 구절 A'
    with patch.object(lrclib,'find',side_effect=ProviderError('timeout','provider_timeout',504)):
        r=send(c,f'/songs/{sid}/lyrics')
        assert r.status_code==504 and r.json['code']=='provider_timeout'
    with app.app_context():
        assert db.session.query(Song).count()==1
        assert db.session.query(LyricVersion).count()==2
        assert db.session.query(Passage).count()==4


def test_lyrics_matches_identity_and_duration():
    row=dict(id=1,trackName='Through the Night (밤편지)',artistName='IU',duration=253,plainLyrics='테스트',instrumental=False)
    with patch.object(lrclib.client,'get',return_value=[row]):
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
    with patch.object(lrclib.client,'get',return_value=[row]):
        assert lrclib.find('Forever Has Always Been','Redoor',240000) is None
        assert lrclib.find('Forever Has Always Been','Redoor',240000,aliases=['리도어'])['external_id']=='1'
        assert lrclib.find('Forever Has Always Been','different',240000,aliases=['다른 가수']) is None


def test_translated_title_requires_known_alias_and_album_duration():
    row=dict(id=37734953,trackName='Shadow of You',artistName='Redoor',albumName='Hospital - EP',duration=256,plainLyrics='테스트 가사')
    def response(path,params):
        return [row] if params.get('track_name')=='Shadow of You' else []
    with patch.object(lrclib.client,'get',side_effect=response):
        assert lrclib.find('우리아픈이야기','Redoor',256000) is None
        assert lrclib.find('우리아픈이야기','Redoor',256000,title_aliases=['Shadow of You'],album='Hospital')['external_id']=='37734953'
        assert lrclib.find('우리아픈이야기','Redoor',256000,title_aliases=['Shadow of You'],album='Different') is None
        assert lrclib.find('우리아픈이야기','Redoor',260000,title_aliases=['Shadow of You'],album='Hospital') is None
        assert lrclib.find('우리아픈이야기','Redoor',None,title_aliases=['Shadow of You'],album='Hospital') is None


def test_candidates_are_not_automatic_translation():
    row=dict(id=1,trackName='Unknown English',artistName='Redoor',albumName='Hospital',duration=256,plainLyrics='테스트 가사')
    with patch.object(lrclib.client,'get',return_value=[row]):
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
        return [row] if params.get('album_name') else []
    with patch.object(lrclib.client,'get',side_effect=response):
        r=send(c,f'/songs/{sid}/lyrics')
        assert r.json['status']=='candidates' and r.json['candidates'][0]['id']==77
        assert c.get(f'/api/songs/{sid}').json['lyrics_status']=='missing'
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

def test_album_cover_prefers_stored_image_then_cover_art_archive():
    from backend.models import Album
    from backend.routes import album_cover
    assert album_cover(None) is None
    release=Album(provider='musicbrainz',external_id='0f1e2d3c-0000-4000-8000-000000000000',title='Blue Hour',artist='유월')
    assert album_cover(release)=='https://coverartarchive.org/release/0f1e2d3c-0000-4000-8000-000000000000/front-500'
    release.image='https://example.test/cover.jpg'
    assert album_cover(release)=='https://example.test/cover.jpg'
    assert album_cover(Album(provider='fixture',external_id='x',title='t',artist='a')) is None
