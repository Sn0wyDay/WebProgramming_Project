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
    assert izm.match(album,'A',['Artist']) is None
    assert izm.match(album,'A',['Artist'],release_names=['Album'])=='album_track'
    assert izm.match(album,'A (instrumental)',['Artist'],instrumental=True,release_names=['Album']) is None


def test_album_track_credits_do_not_hide_review_or_change_recording_version():
    content=('리메이크 앨범 평론. <br> -수록곡- <br> '
             '1. 제주도의 푸른밤 (작사: 최성원 / 작곡: 최성원) <br> '
             '2. 별이 진다네 (조병석 / 조병석) <br> '
             '3. 세 번째 곡 (Live) (작사: 홍길동 / 작곡: 홍길동)')
    reviewed=izm.normalize_search(search_response([], [raw_row(title='제주도의 푸른밤',artist='성시경',rid=3017,content=content)]))[0]
    releases=['제주도의 푸른 밤']
    with patch.object(izm.client,'get',side_effect=AssertionError('Already in artist search cache')):
        def cached(path,params):
            return [reviewed] if params['keyword']=='성시경' else None
        with patch.object(izm.client,'cached',side_effect=cached):
            linked=izm.find('제주도의 푸른 밤','성시경','푸른밤의 꿈',release_names=releases)
    assert linked[0]['relation']=='album_track' and linked[0]['url']=='https://www.izm.co.kr/posts?id=3017'
    assert izm.match(reviewed,'별이 진다네',['성시경'],release_names=releases)=='album_track'
    assert izm.match(reviewed,'별이 진다네',['성시경'],release_names=['다른 앨범']) is None
    assert izm.match(reviewed,'제주도의 푸른 밤',['최성원'],release_names=releases) is None
    assert izm.match(reviewed,'제주도의 푸른 밤 (Inst.)',['성시경'],instrumental=True,release_names=releases) is None
    assert izm.match(reviewed,'세 번째 곡',['성시경'],release_names=releases) is None
    assert izm.match(reviewed,'세 번째 곡 (Live)',['성시경'],release_names=releases)=='album_track'
    assert izm.match({**reviewed,'tracks':['곡 (사랑 / 슬픔)']},'곡',['성시경'],release_names=releases) is None


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


def test_metadata_failure_does_not_skip_review_search_with_known_artist_name():
    article=izm.normalize_search(search_response([raw_row(title='Song',artist='Artist')]))[0]
    resolver=lambda:(_ for _ in ()).throw(ProviderError('metadata unavailable','provider_rate_limited',503,30))
    with patch.object(izm.client,'get',side_effect=[[],[article]]) as get:
        assert izm.find('Song','Artist',resolve_aliases=resolver)[0]['relation']=='song'
        assert get.call_args_list[-1].args[1]=={'keyword':'Artist'}


def test_unresolved_artist_failure_is_not_reported_as_no_review():
    resolver=lambda:(_ for _ in ()).throw(ProviderError('metadata unavailable','provider_rate_limited',503,30))
    with patch.object(izm.client,'get',return_value=[]),pytest.raises(ProviderError) as error:
        izm.find('Song','Artist',resolve_aliases=resolver)
    assert error.value.retry_after==30


@pytest.fixture(scope='module')
def app(tmp_path_factory):
    folder=tmp_path_factory.mktemp('reviews')
    app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'review_test_sessions',
                    'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(folder/'test.db'),'RESOURCE_JOB_PATH':str(folder/'review-jobs.db')})
    with app.app_context():
        db.create_all()
        db.session.add(User(id=1,email='review@example.com',username='review',name='Test',password_hash='unused'))
        db.session.add_all([Song(id=n,provider='test',external_id=str(n),title='Song '+str(n),artist='Artist') for n in range(1,6)])
        db.session.commit()
    yield app
    app.extensions['resource_queue'].close()


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
            r=send(c,'/songs/4/reviews');assert r.json['status']=='unavailable' and r.json['retry_after']==3
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


def test_verified_album_review_can_be_reused_for_another_track_offline():
    row=izm.normalize_search(search_response([], [raw_row(title='Album',artist='Artist')]))[0]
    def cached(path,params):
        return [row] if params['keyword']=='Album' else None
    with patch.object(izm.client,'cached',side_effect=cached),patch.object(izm.client,'get',side_effect=AssertionError('Offline')):
        assert izm.find('Other Song','Artist','Album')[0]['relation']=='album'


def test_homonymous_recordings_recheck_saved_track_links_by_recording_id(app):
    matching_id='d0ea4b20-5f4c-4e49-9fdb-e585d810d9da'
    other_id='a56d8553-96f4-4943-b29a-e6913cc7f800'
    row=izm.normalize_search(search_response([], [
        raw_row(title='Reviewed Album',artist='가수',rid=1234,
                content='<p>Review excerpt.</p><p>-수록곡-</p><p>1. 동명곡 (작사: 홍길동)</p>'),
    ]))[0]
    with app.app_context():
        first=Song(id=6,provider='musicbrainz',external_id=matching_id,title='동명곡',artist='가수')
        second=Song(id=7,provider='musicbrainz',external_id=other_id,title='동명곡',artist='가수')
        db.session.add_all([first,second]);db.session.commit()
        reviews.save(first,[{**row,'relation':'album_track'}])
        reviews.save(second,[{**row,'relation':'album_track'}])
        review=db.session.scalar(db.select(Review).where(Review.url==row['url']))
        for song in (first,second):
            db.session.get(ReviewLink,(song.id,review.id)).match_version=0
        db.session.commit()
        review_id=review.id

    store=app.extensions['resource_queue'].store
    with patch.object(reviews,'MATCH_RULE_VERSION',3):
        old_job=store.submit(7,'reviews',{})
    store.finish(store.claim(),dict(status='available',reviews=[row]))

    def recording(path,params):
        recording_id=path.rsplit('/',1)[1]
        assert params=={'inc':'artists+releases','fmt':'json'}
        official='Reviewed Album' if recording_id==matching_id else 'Different Album'
        return dict(id=recording_id,releases=[
            dict(title=official,status='Official'),
            dict(title='Reviewed Album',status='Bootleg'),
        ])

    c=app.test_client();login(c)
    assert c.get('/api/resource-jobs/'+old_job['id']).json['result']['reviews']==[]
    assert c.get('/api/songs/6').json['reviews']==[]
    assert c.get('/api/songs/7').json['reviews']==[]
    with patch.object(izm.client,'get',return_value=[row]),patch.object(musicbrainz.client,'get',side_effect=recording):
        assert send(c,'/songs/6/reviews').json['reviews'][0]['id']==review_id
        assert send(c,'/songs/7/reviews').json['status']=='missing'
    assert c.get('/api/songs/6').json['reviews'][0]['kind']=='album_track'
    assert c.get('/api/songs/7').json['reviews']==[]
    assert store.submit(7,'reviews',{})['id']!=old_job['id']
