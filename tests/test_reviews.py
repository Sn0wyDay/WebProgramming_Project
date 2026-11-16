from io import BytesIO
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from flask_migrate import upgrade
from backend import create_app,db
from backend.models import Album,Song,User,UserSong,Review,ReviewLink,ReviewSource
from backend.providers import izm,musicbrainz,hellokpop
from backend.providers.http import JsonClient,ProviderError
from backend import reviews


def raw_row(title='A',artist='Artist',kind='song',rid=100,content=None):
    return dict(id=rid,title=title,writer_name='Actual Writer',artists=[dict(kr_name=artist,en_name=None)],
                main_category='Review',content=content or '<p>A short critical sentence. A long copyrighted article must not be kept.</p>')


def search_response(rows,album_rows=None):
    return dict(contents={'single_review_contents':rows,'album_review_contents':album_rows or []})


def test_parse_retains_only_small_plain_excerpt_and_explicit_track_list():
    content='<script>unsafe()</script><p>Brief critical sentence.</p><p>'+('Long text '*150)+'</p><div>- 수록곡 -</div><div>1. A [추천]</div><div>2. B</div>'
    rows=izm.normalize_search(search_response([], [raw_row(kind='album',content=content)]))
    assert rows[0]['tracks']==['A','B']
    assert rows[0]['introduction']=='Brief critical sentence.'
    assert 'content' not in rows[0] and 'unsafe' not in str(rows) and 'Long text' not in str(rows)
    long=izm.short_excerpt(['word '*100]);assert len(long)<=111 and len(long.split())<=20
    # The provider cache stores the reduced response, not the entire article HTML.
    with patch('backend.providers.http.urlopen',return_value=BytesIO(json.dumps(search_response([raw_row(content=content)])).encode())):
        client=JsonClient('https://review.test',0,transform=izm.normalize_search)
        client.get('/search');assert 'Long text' not in str(client.cache)


def test_matching_rejects_homonyms_mentions_and_other_versions():
    song=izm.normalize_search(search_response([raw_row()]))[0]
    assert izm.match(song,'A',['Artist'])=='song'
    assert izm.match(song,'A',['Different']) is None
    assert izm.match(song,'A (Live)',['Artist']) is None
    assert izm.match(song,'A (instrumental)',['Artist'],instrumental=True) is None
    album=izm.normalize_search(search_response([], [raw_row(title='Album',content='<p>A is mentioned in prose.</p>')]))[0]
    assert izm.match(album,'A',['Artist'],'Different album') is None
    assert izm.match(album,'A',['Artist'],'Album')=='album'
    album['tracks']=['A (Feat. Guest)']
    assert izm.match(album,'A',['Artist'])=='album_track'
    assert izm.match(album,'A (instrumental)',['Artist'],instrumental=True) is None


def test_public_search_only_uses_artist_verified_korean_alias():
    row=izm.normalize_search(search_response([raw_row(artist='가수')]))[0]
    with patch.object(izm.client,'get',side_effect=[[],[row]]) as get:
        found=izm.find('A','Artist',resolve_aliases=lambda:['가수'])
        assert found[0]['relation']=='song'
        assert get.call_args_list[1].args[1]=={'keyword':'가수'}
    with patch.object(izm.client,'get',return_value=[row]):
        assert izm.find('A','Other')==[]
    with patch.object(izm.client,'get',side_effect=[[],[row]]),patch.object(musicbrainz,'recording_artist_aliases',side_effect=AssertionError('Korean artist needs no alias lookup')) as aliases:
        assert izm.find('A','가수',resolve_aliases=aliases)[0]['relation']=='song'


def test_artist_aliases_are_bound_to_recording_id_not_name_search():
    recording='d0ea4b20-5f4c-4e49-9fdb-e585d810d9da';artist='2c8b5bb2-6110-488d-bc15-abb08379d3c6'
    with patch.object(musicbrainz.client,'recall',return_value=None),patch.object(musicbrainz.client,'remember'),patch.object(musicbrainz.client,'get',side_effect=[{'id':recording,'artist-credit':[{'artist':{'id':artist,'name':'Silica Gel'}}]},{'id':artist,'name':'실리카겔','aliases':[]}]) as get:
        assert '실리카겔' in musicbrainz.recording_artist_aliases(recording)
        assert get.call_args_list[0].args[0]=='/recording/'+recording
        assert get.call_args_list[1].args[0]=='/artist/'+artist
    with patch.object(musicbrainz.client,'recall',return_value=None),patch.object(musicbrainz.client,'get',return_value={'id':artist}):
        with pytest.raises(ProviderError):musicbrainz.recording_artist_aliases(recording)


def test_prior_album_results_are_rechecked_after_artist_alias_resolution():
    article=izm.normalize_search(search_response([], [raw_row(title='Album',artist='가수')]))[0]
    with patch.object(izm.client,'get',side_effect=[[],[article]]) as get:
        found=izm.find('Song','Artist','Album',resolve_aliases=lambda:['가수'])
        assert found[0]['title']=='Album' and found[0]['relation']=='album'
        assert get.call_count==2
    with patch.object(izm.client,'get',side_effect=[[],[article],[]]):
        assert izm.find('Song','Unrelated','Album',resolve_aliases=lambda:['다른 가수'])==[]


@pytest.fixture(scope='module')
def app(tmp_path_factory):
    app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'review_test_sessions','SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path_factory.mktemp('reviews')/'test.db')})
    with app.app_context():
        db.create_all()
        db.session.add(User(id=1,email='review@example.com',username='review',name='Test',password_hash='unused'))
        db.session.add_all([Song(id=n,provider='test',external_id=str(n),title='Song '+str(n),artist='Artist') for n in range(1,6)])
        db.session.commit()
    return app


@pytest.fixture(autouse=True)
def clear_memory():
    izm.client.cache.clear()
    with patch.object(hellokpop,'find',return_value=[]):yield
    izm.client.cache.clear()


def send(c,path):
    token=c.get('/api/session').json['csrf_token']
    return c.post('/api'+path,json={},headers={'X-CSRFToken':token})


def login(c):
    with c.session_transaction() as session:session['user_id']=1


def test_api_lazy_shared_review_dedup_and_no_user_record_mutation(app):
    c=app.test_client()
    assert send(c,'/songs/1/reviews').status_code==401
    login(c)
    assert c.post('/api/songs/1/reviews',json={}).status_code==400
    assert send(c,'/songs/999/reviews').status_code==404
    item=izm.normalize_search(search_response([raw_row()]))[0];item['relation']='album_track'
    with patch.object(izm,'find',return_value=[item]) as find:
        assert c.get('/api/songs/1').json['reviews']==[] and find.call_count==0
        assert send(c,'/songs/1/reviews').json['status']=='available'
        assert send(c,'/songs/1/reviews').json['from_database'] is True
        assert find.call_count==1
        assert send(c,'/songs/2/reviews').json['reviews'][0]['kind']=='album_track'
    with app.app_context():
        assert db.session.query(Review).count()==1 and db.session.query(ReviewLink).count()==2
        assert db.session.query(UserSong).count()==0
    other=app.test_client();login(other)
    with patch.object(izm,'find',side_effect=AssertionError('Saved reviews require no external call')):
        assert other.get('/api/songs/2').json['reviews'][0]['author']=='Actual Writer'
        assert other.get('/api/songs/3').json['reviews']==[]


def test_api_missing_and_failure_are_separate_and_both_throttled(app):
    c=app.test_client();login(c)
    with patch.object(izm,'find',return_value=[]) as find:
        for _ in range(2):assert send(c,'/songs/3/reviews').json['status']=='missing'
        assert find.call_count==1
    with patch.object(izm,'find',side_effect=ProviderError('timeout','provider_timeout',504)) as find:
        for _ in range(2):
            r=send(c,'/songs/4/reviews');assert r.json['status']=='unavailable' and r.json['retry_after']>=59
        assert find.call_count==1
        assert c.get('/api/songs/4').status_code==200


def test_migration_keeps_legacy_review_and_backfills_its_link(tmp_path):
    app=create_app({'TESTING':True,'SECRET_KEY':'migration','SESSION_SQLALCHEMY_TABLE':'review_migration_sessions','SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'migration.db')})
    with app.app_context():
        folder=str(Path(__file__).resolve().parents[1]/'migrations')
        upgrade(directory=folder,revision='55ea10177859')
        song=Song(provider='test',external_id='legacy',title='Legacy',artist='Artist');source=ReviewSource(name='Legacy Source')
        db.session.add_all([song,source]);db.session.flush()
        db.session.execute(db.text('INSERT INTO review(song_id,source_id,title,author,url,introduction) VALUES (:song,:source,:title,:author,:url,:intro)'),
                           dict(song=song.id,source=source.id,title='Legacy Article',author='Writer',url='https://example.com/legacy',intro='Existing excerpt'));db.session.commit()
        upgrade(directory=folder)
        assert reviews.for_song(song)[0]['title']=='Legacy Article'
        assert reviews.for_song(song)[0]['kind']=='song'
        assert reviews.for_song(song)[0]['article_type']=='review'
