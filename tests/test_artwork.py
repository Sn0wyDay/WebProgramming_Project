"""Artwork is optional public metadata, not a dependency of music or user records."""
from unittest.mock import patch
import pytest
from backend import create_app, db
from backend.models import Album, Song, User, UserSong
from backend.providers import coverart, musicbrainz
from backend.providers.http import ProviderError

RELEASE='78429df2-86f4-432f-ac0d-28ee2991573e'
EDITION='733405be-94ce-4f1d-9475-9c12c4e3be10'
GROUP='ea0cd80a-eabb-4c58-bfda-8c7ec948b58d'
IMAGE='https://coverartarchive.org/release/'+RELEASE+'/42218573869-500.jpg'


def metadata(release=RELEASE):
    return dict(release='https://musicbrainz.org/release/'+release,images=[dict(id=42218573869,front=True,approved=True,thumbnails={'large':IMAGE.replace('https:','http:')})])


@pytest.fixture(scope='module')
def app(tmp_path_factory):
    folder=tmp_path_factory.mktemp('artwork')
    app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'artwork_test_sessions',
                    'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(folder/'test.db'),'ARTWORK_CACHE_PATH':str(folder/'covers')})
    with app.app_context():
        db.create_all()
        db.session.add(User(id=1,email='artwork@example.com',username='artwork',name='Art',password_hash='unused'))
        db.session.commit()
    return app


@pytest.fixture(autouse=True)
def isolate_cache():
    coverart.client.cache.clear()
    musicbrainz.client.cache.clear()
    yield
    coverart.client.cache.clear()
    musicbrainz.client.cache.clear()


def test_front_identity_approved_and_safe_url():
    assert coverart.front(metadata(),RELEASE)['image']==IMAGE
    with pytest.raises(ProviderError):coverart.front(metadata(),EDITION)
    for field in ('front','approved'):
        data=metadata();data['images'][0][field]=False
        assert coverart.front(data,RELEASE) is None
    for url in ('javascript:alert(1)','https://evil.test/image.jpg',IMAGE.replace(RELEASE,EDITION),IMAGE.replace('42218573869','123')):
        data=metadata();data['images'][0]['thumbnails']={'500':url}
        assert coverart.front(data,RELEASE) is None


def test_group_fallback_requires_confirmed_release_identity():
    with patch.object(coverart.client,'get',side_effect=[None,metadata()]) as caa,patch.object(musicbrainz.client,'get',return_value={'id':EDITION,'release-group':{'id':GROUP}}):
        assert coverart.find(EDITION)['image']==IMAGE
        assert caa.call_args_list[1].args==('/release-group/'+GROUP,)
    with patch.object(coverart.client,'get',return_value=None) as caa,patch.object(musicbrainz.client,'get',return_value={'id':RELEASE,'release-group':{'id':GROUP}}):
        with pytest.raises(ProviderError):coverart.find(EDITION)
        assert caa.call_count==1


def test_missing_is_distinct_from_failure_and_error_has_cooldown():
    with patch.object(coverart.client,'get',return_value=None),patch.object(musicbrainz.client,'get',return_value={'id':RELEASE,'release-group':{'id':GROUP}}):
        assert coverart.find(RELEASE) is None
    with patch.object(coverart.client,'get',side_effect=ProviderError('timeout','provider_timeout',504)) as transport:
        for _ in range(2):
            with pytest.raises(ProviderError):coverart.find(RELEASE)
        assert transport.call_count==1


def send(c,path):
    token=c.get('/api/session').json['csrf_token']
    return c.post('/api'+path,json={},headers={'X-CSRFToken':token})


def test_api_lazy_lookup_persists_shared_album_without_changing_records(app):
    with app.app_context():
        album=Album(provider='musicbrainz',external_id=RELEASE,title='Hospital',artist='Redoor')
        db.session.add(album);db.session.flush()
        db.session.add_all([Song(id=1,provider='test',external_id='1',title='A',artist='Redoor',album_id=album.id),Song(id=2,provider='test',external_id='2',title='B',artist='Redoor',album_id=album.id)])
        db.session.commit()
    c=app.test_client()
    assert send(c,'/songs/1/artwork').status_code==401
    with c.session_transaction() as session:session['user_id']=1
    with patch.object(coverart,'find',return_value={'image':IMAGE,'source_url':coverart.source_url(IMAGE),'provider':'Cover Art Archive'}) as lookup:
        assert c.get('/api/home').status_code==200
        assert c.get('/api/songs/1').json['image'] is None
        assert lookup.call_count==0
        assert send(c,'/songs/1/artwork').json['status']=='available'
        assert send(c,'/songs/2/artwork').json['image']==IMAGE
        assert lookup.call_count==1
    # A new client/session also reads the saved album artwork without network.
    other=app.test_client()
    with other.session_transaction() as session:session['user_id']=1
    with patch.object(coverart,'find',side_effect=AssertionError('No external call')):
        assert other.get('/api/songs/2').json['image']==IMAGE
        assert other.get('/api/songs/2').json['artwork_source']==coverart.source_url(IMAGE)
    with app.app_context():assert db.session.query(UserSong).count()==0


def test_api_cover_failure_keeps_music_available(app):
    with app.app_context():
        album=Album(provider='musicbrainz',external_id=EDITION,title='Hospital',artist='Redoor')
        db.session.add(album);db.session.flush()
        db.session.add(Song(id=3,provider='test',external_id='3',title='C',artist='Redoor',album_id=album.id));db.session.commit()
    c=app.test_client()
    with c.session_transaction() as session:session['user_id']=1
    with patch.object(coverart,'find',side_effect=ProviderError('timeout')):
        result=send(c,'/songs/3/artwork')
        assert result.status_code==200 and result.json['status']=='unavailable' and result.json['image'] is None
        assert result.json['retry_after']>=60
        assert c.get('/api/songs/3').status_code==200
    with patch.object(coverart,'find',return_value=None):
        assert send(c,'/songs/3/artwork').json['status']=='missing'
