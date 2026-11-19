from unittest.mock import patch
import pytest
from backend import create_app,db
from backend.models import User,Album,Song,UserSong
from backend.music import verified_lyric_rule
from backend.providers import lrclib,musicbrainz

MBID='e1437f5a-0ccc-449d-8b17-5ddfa0b146b7'


def song():
    return Song(provider='musicbrainz',external_id=MBID,title='한시 오분 (1:05)',artist='검정치마',duration_ms=240000)


@pytest.mark.parametrize('field,value',[
    ('external_id','00000000-0000-0000-0000-000000000000'),('artist','다른 가수'),
    ('title','한시 오분 (1:05) (Live)'),('duration_ms',250000),
])
def test_verified_artist_and_numeric_title_are_bound_to_the_recording(field,value):
    target=song();setattr(target,field,value)
    assert verified_lyric_rule(target,'Team Baby')=={}
    assert verified_lyric_rule(song(),'Other Album')=={}


def test_uses_verified_provider_artist_in_signature_and_search_queries():
    row=dict(id=5228940,trackName='1:05',artistName='The Black Skirts',albumName='TEAM BABY',duration=240,plainLyrics='검증용 구절')
    def response(path,params):
        assert params['artist_name']=='The Black Skirts'
        return row if params['track_name']=='1:05' else None
    with patch.object(lrclib.client,'get',side_effect=response) as calls:
        result=lrclib.find('한시 오분 (1:05)','검정치마',240000,aliases=['The Black Skirts'],title_aliases=['1:05'],album='Team Baby')
        assert result['external_id']=='5228940' and calls.call_count==2
    assert lrclib.request_artist('검정치마',[])=='검정치마'


def test_korean_catalog_connects_real_provider_shape_without_metadata_http(tmp_path):
    import uuid
    app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'clock_'+uuid.uuid4().hex,
                    'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'test.db')})
    with app.app_context():
        db.create_all()
        album=Album(provider='fixture',external_id='team-baby',title='TEAM BABY',artist='검정치마')
        db.session.add(album);db.session.flush()
        track=song();track.id=1;track.album_id=album.id
        db.session.add_all([track,User(id=1,email='clock@example.com',username='clock',name='Test',password_hash='unused')]);db.session.commit()
    c=app.test_client()
    with c.session_transaction() as session:session['user_id']=1
    token=c.get('/api/session').json['csrf_token']
    row=dict(id=5228940,trackName='1:05',artistName='The Black Skirts',albumName='TEAM BABY',duration=240,plainLyrics='검증용 구절 A\n검증용 구절 B')
    def response(path,params):
        assert params['artist_name']=='The Black Skirts'
        return row if params['track_name']=='1:05' else None
    with patch.object(musicbrainz.client,'get',side_effect=AssertionError('No metadata network')),patch.object(lrclib.client,'get',side_effect=response):
        result=c.post('/api/songs/1/lyrics',json={},headers={'X-CSRFToken':token})
        assert result.status_code==200 and result.json['status']=='available'
    detail=c.get('/api/songs/1').json
    assert detail['lyrics_title']=='1:05' and detail['lyrics_match']=='exact' and len(detail['passages'])==2
    with app.app_context():assert db.session.query(UserSong).count()==0
