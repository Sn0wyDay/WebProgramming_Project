import base64
from io import BytesIO
from unittest.mock import patch
from urllib.request import Request
import pytest
from backend import create_app,db,artwork_service
from backend.models import User,Song,Album,UserSong
from backend.providers import coverart
from backend.providers.http import ProviderError

IMAGE='https://coverartarchive.org/release/78429df2-86f4-432f-ac0d-28ee2991573e/42218573869-500.jpg'
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


@pytest.fixture
def app(tmp_path):
    import uuid
    app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'covers_'+uuid.uuid4().hex,
                    'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'test.db'),
                    'ARTWORK_CACHE_PATH':str(tmp_path/'covers'),'ARTWORK_DOWNLOAD_ENABLED':True,
                    'RESOURCE_JOB_PATH':str(tmp_path/'jobs.db'),'PROVIDER_CACHE_PATH':str(tmp_path/'cache.db')})
    with app.app_context():
        db.create_all()
        album=Album(id=1,provider='musicbrainz',external_id='78429df2-86f4-432f-ac0d-28ee2991573e',title='Album',artist='Artist')
        db.session.add(album);db.session.flush()
        db.session.add_all([Song(id=1,provider='fixture',external_id='one',title='Song',artist='Artist',album_id=1),
                           User(id=1,email='cover@example.com',username='cover',name='Test',password_hash='unused')]);db.session.commit()
    yield app
    app.extensions['resource_queue'].close()


def image_response(raw=PNG,mime='image/png'):
    result=BytesIO(raw);result.headers={'Content-Type':mime}
    return result


def test_verified_cover_download_is_persistent_and_browsable_without_external_http(app):
    c=app.test_client()
    with c.session_transaction() as session:session['user_id']=1
    token=c.get('/api/session').json['csrf_token']
    with patch.object(coverart,'find',return_value={'image':IMAGE}),patch.object(artwork_service.image_client,'open',return_value=image_response()) as download:
        result=c.post('/api/songs/1/artwork',json={},headers={'X-CSRFToken':token}).json
        assert result['status']=='available' and result['local_cached']
        assert result['image'].startswith('/api/media/artwork/') and download.call_count==1
    artwork_service.image_client.cache.clear()
    with patch.object(coverart,'find',side_effect=AssertionError('No metadata HTTP')),patch.object(artwork_service.image_client,'open',side_effect=AssertionError('No image HTTP')):
        assert c.get('/api/songs/1').json['image']==result['image']
        ready=c.post('/api/songs/1/resources/artwork',json={},headers={'X-CSRFToken':token}).json
        assert ready['status']=='completed' and ready['result']['local_cached']
        image=c.get(result['image'])
        assert image.status_code==200 and image.content_type=='image/png' and image.data==PNG
        assert image.headers['X-Content-Type-Options']=='nosniff'
    with app.app_context():assert db.session.query(UserSong).count()==0


@pytest.mark.parametrize('raw,mime',[(b'<script>unsafe()</script>','image/png'),(PNG,'text/html')])
def test_html_or_mislabeled_data_is_not_stored_as_cover(app,raw,mime):
    with app.app_context(),patch.object(artwork_service.image_client,'open',return_value=image_response(raw,mime)):
        with pytest.raises(ProviderError):artwork_service.image_client.get('/release/example/image.jpg')
        assert list(artwork_service.directory().glob('*.img'))==[]


def test_cover_redirects_cannot_reach_arbitrary_hosts_or_insecure_urls():
    request=Request(IMAGE)
    for url in ('http://127.0.0.1/x.jpg','https://127.0.0.1/x.jpg','https://evil-archive.org/x.jpg','https://coverartarchive.org.evil.test/x.jpg'):
        assert not artwork_service.allowed_url(url)
        with pytest.raises(ProviderError):artwork_service.CoverRedirects().redirect_request(request,None,302,'',{},url)
    assert artwork_service.allowed_url('https://ia800000.us.archive.org/x.jpg')
    assert artwork_service.allowed_url('https://archive.org/x.jpg')
    upgraded=artwork_service.CoverRedirects().redirect_request(request,None,302,'',{},'http://archive.org/x.jpg')
    assert upgraded.full_url=='https://archive.org/x.jpg'


def test_missing_local_file_can_be_downloaded_again(app):
    with app.app_context():
        path='/release/78429df2-86f4-432f-ac0d-28ee2991573e/42218573869-500.jpg'
        with patch.object(artwork_service.image_client,'open',side_effect=lambda *a,**k:image_response()) as download:
            first=artwork_service.image_client.get(path)
            (artwork_service.directory()/first['filename']).unlink()
            assert artwork_service.image_client.get(path)['filename']==first['filename']
            assert download.call_count==2


def test_cover_cache_is_bounded_without_touching_unrelated_files(tmp_path):
    for index in range(129):(tmp_path/(f'{index:064x}'+'.img')).write_bytes(PNG)
    unrelated=tmp_path/'notes.txt';unrelated.write_text('keep')
    artwork_service.prune(tmp_path)
    assert len(list(tmp_path.glob('*.img')))==128 and unrelated.read_text()=='keep'
