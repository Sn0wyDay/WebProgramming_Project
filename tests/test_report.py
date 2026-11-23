from types import SimpleNamespace

from backend import create_app, db
from backend.models import Song, User
from backend.providers import musicbrainz


def test_report_uses_catalog_ids_and_falls_back_to_selected_genre(monkeypatch):
    seed = SimpleNamespace(external_id='00000000-0000-4000-8000-000000000001',
                           title='Original', artist='Test Artist')
    def row(number, title):
        return {'id': f'00000000-0000-4000-8000-{number:012d}', 'title': title,
                'artist-credit': [{'name': seed.artist}]}
    snapshots = {}
    monkeypatch.setattr(musicbrainz.client, 'remember', snapshots.__setitem__)
    queries = []
    def search(path, params):
        queries.append(params['query'])
        return {'recordings': [row(1, 'Original'), row(2, 'Another')] if len(queries) == 1
                else [row(3, 'Another'), row(4, 'Next')]}
    monkeypatch.setattr(musicbrainz.client, 'get', search)
    items = musicbrainz.report_candidates(seed, '재즈')
    assert queries == ['artist:"Test Artist" AND tag:"jazz" AND video:false',
                       'tag:"jazz" AND video:false']
    assert [item['title'] for item in items] == ['Another', 'Next']
    assert all(snapshots[item['external_id']] == item for item in items)


def test_report_requires_session_and_valid_seed_and_genre(tmp_path, monkeypatch):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test',
                      'SESSION_SQLALCHEMY_TABLE': 'report_sessions',
                      'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'report.db')})
    with app.app_context():
        db.create_all()
        db.session.add(User(id=1, username='report', name='Report', email='report@example.com', password_hash='unused'))
        db.session.add(Song(id=1, provider='test', external_id='seed', title='Seed', artist='Artist'))
        db.session.commit()
    client = app.test_client()
    endpoint = '/api/report/discovery'
    assert client.get(endpoint + '?seed=1').status_code == 401
    with client.session_transaction() as session:
        session['user_id'] = 1
    for query in ('', '?seed=x', '?seed=1&genre=unknown'):
        assert client.get(endpoint + query).status_code == 400
    assert client.get(endpoint + '?seed=12').status_code == 404
    monkeypatch.setattr(musicbrainz, 'report_candidates', lambda song, genre: [])
    assert client.get(endpoint + '?seed=1').get_json() == {'items': []}
