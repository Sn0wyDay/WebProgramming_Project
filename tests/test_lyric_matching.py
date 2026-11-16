"""Regression cases use invented lyric text, not real copyrighted song lyrics."""
from unittest.mock import patch
import pytest
from backend import create_app,db
from backend.models import Song,Album,User
from backend.providers import lrclib,musicbrainz

TITLE='뜨거운 여름밤은 가고 남은 건 볼품없지만'
MBID='39c40d9b-a35a-4c68-9da2-7471121c5f16'


def row(rid=13007700,duration=243,album='MONKEY HOTEL',artist='JANNABI(잔나비)'):
    return dict(id=rid,trackName='Summer('+TITLE+')',artistName=artist,albumName=album,
                duration=duration,instrumental=False,plainLyrics='검증용 구절 A\n검증용 구절 B')


@pytest.mark.parametrize('catalog,provider,expected',[
    ('잔나비','JANNABI(잔나비)',True),('JANNABI','잔나비 (Jannabi)',True),
    ('JANNABI(잔나비)','JANNABI',True),('아이유','IU [아이유]',True),
    ('잔나비','Not JANNABI',False),('잔나비','Other (feat. 잔나비)',False),
    ('잔나비','Other & Guest (잔나비)',False),('잔나비','JANNABI(잔나비), Album, 2016',False),
    ('잔나비','JANNABI(잔나비]',False),('밴드','다른밴드',False),
])
def test_bilingual_artist_is_explicit_not_a_substring_or_feature(catalog,provider,expected):
    assert lrclib.artist_matches(provider,catalog,[]) is expected


def test_selects_right_duration_and_album_not_first_provider_result():
    rows=[row(1,200),row(2,170),row(3,243,album='Unrelated'),row(4,246),row()]
    with patch.object(lrclib.client,'get',return_value=rows):
        result=lrclib.find(TITLE,'잔나비',243000,album='MONKEY HOTEL')
        assert result['external_id']=='13007700' and result['duration']==243
        assert result['match_method']=='exact'


def test_title_only_fallback_retrieves_alias_but_keeps_identity_checks():
    with patch.object(lrclib.client,'get',side_effect=[[],[row(artist='JANNABI')]]) as get:
        assert lrclib.find(TITLE,'잔나비',243000,aliases=['JANNABI'],album='MONKEY HOTEL')
        assert get.call_count==2 and get.call_args_list[1].args[1]=={'track_name':TITLE}
    with patch.object(lrclib.client,'get',return_value=[row(artist='Wrong Artist')]):
        assert lrclib.find(TITLE,'잔나비',243000,album='MONKEY HOTEL') is None


def test_invalid_duration_and_other_versions_are_never_auto_attached():
    for duration in (None,True,'243',float('nan')):
        with patch.object(lrclib.client,'get',return_value=[row(duration=duration)]):
            assert lrclib.find(TITLE,'잔나비',243000,album='MONKEY HOTEL') is None
    for suffix in (' (Inst.)',' (Live)',' (Karaoke)',' (Slowed)',' (Cover)'):
        value=row();value['trackName']+=suffix
        with patch.object(lrclib.client,'get',return_value=[value]):
            assert lrclib.find(TITLE,'잔나비',243000,album='MONKEY HOTEL') is None


def test_lrc_cleanup_preserves_lyric_brackets_and_removes_only_timing():
    value=row();value['plainLyrics']='  '
    value['syncedLyrics']='[ar:Test]\n[00:01.00] [Chorus]\n[00:02.000]<00:02.001>검증용 <00:02.500>구절\n[00:03.00][00:05.00]다음 구절'
    parsed=lrclib.parse_row(value,'잔나비',243000)
    assert parsed['text']=='[Chorus]\n검증용 구절\n다음 구절'


def test_actual_failure_shape_resolves_without_musicbrainz_and_persists(tmp_path):
    app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'lyric_match_sessions','SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'test.db')})
    with app.app_context():
        db.create_all()
        a=Album(provider='fixture',external_id='monkey',title='MONKEY HOTEL',artist='잔나비')
        db.session.add(a);db.session.flush()
        db.session.add_all([User(id=1,email='match@example.com',username='match',name='Test',password_hash='unused'),Song(id=1,provider='musicbrainz',external_id=MBID,title=TITLE,artist='잔나비',album_id=a.id,duration_ms=243000)])
        db.session.commit()
    c=app.test_client()
    with c.session_transaction() as session:session['user_id']=1
    token=c.get('/api/session').json['csrf_token']
    def lookup():return c.post('/api/songs/1/lyrics',json={},headers={'X-CSRFToken':token})
    with patch.object(musicbrainz.client,'get',side_effect=AssertionError('Lyrics must not need metadata HTTP')),patch.object(lrclib.client,'get',return_value=[row(1,200),row(2,170),row()]):
        assert lookup().json['status']=='available'
    other=app.test_client()
    with other.session_transaction() as session:session['user_id']=1
    with patch.object(lrclib.client,'get',side_effect=AssertionError('Use the stored lyric version')):
        assert lookup().json['from_database'] is True
        detail=other.get('/api/songs/1').json
        assert len(detail['passages'])==2 and detail['lyrics_status']=='available'
