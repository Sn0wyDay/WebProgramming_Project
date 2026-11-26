from backend.providers import musicbrainz
from backend.music import import_song, verified_lyric_rule
from backend.models import Song
from backend import db
from test_catalog_jobs import app, client, submit


RECORDING = '5f705a3e-43a4-44ed-909a-c2155499ba84'


def test_new_search_and_cached_import_share_the_correct_title(app, monkeypatch):
    raw = {'id': RECORDING, 'title': '눈사림', 'artist-credit': [{'name': '정승환'}],
           'length': 238000, 'releases': [{'title': 'Spring Again'}]}
    def search_recordings(path, params):
        assert path == '/recording/' and f'rid:{RECORDING}' in params['query']
        return {'count': 1, 'recordings': [raw]}
    monkeypatch.setattr(musicbrainz.client, 'get', search_recordings)
    with app.app_context():
        item = musicbrainz.search('정승환 눈사람')['items'][0]
        assert item['title'] == '눈사람'
        old = {**item, 'title': '눈사림'}
        musicbrainz.client.remember(RECORDING, old)
        musicbrainz.client.remember(musicbrainz.search_key('정승환',1), {'items':[old],'pages':1})
        song = import_song(RECORDING)
        assert song.title == '눈사람' and import_song(RECORDING).id == song.id
        assert verified_lyric_rule(song, 'Spring Again')['alternate_titles'] == ['The Snowman']
        db.session.add(Song(provider='fixture', external_id='unrelated', title='눈사림', artist='다른 가수'))
        db.session.commit()
    c = client(app)
    assert submit(c, {'q':'정승환'}).json['result']['items'][0]['title']=='눈사람'
    for q in ('눈사람','정승환 눈사림','The Snowman'):
        assert [s['title'] for s in c.get('/api/songs',query_string={'q':q}).json['items']]==['눈사람']
    assert musicbrainz.corrected_item({**old, 'external_id':'other'})['title']=='눈사림'
    assert musicbrainz.corrected_item({**old, 'title':'눈사림 (Live)'})['title']=='눈사림 (Live)'
