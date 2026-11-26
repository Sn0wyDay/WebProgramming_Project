from backend import create_app, db
from backend.models import Song, LyricVersion, Passage


def test_friend_workflow_and_search_pagination(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'friends.db'), 'SESSION_SQLALCHEMY_TABLE': 'friend_sessions'})
    with app.app_context():
        db.create_all()
        db.session.add(Song(id=1, provider='test', external_id='song', title='긴 제목의 음악', artist='테스트 아티스트'))
        db.session.add(LyricVersion(id=1, song_id=1, provider='test', digest='a'*64, source_url='https://example.com'))
        db.session.add(Passage(id=1, version_id=1, position=0, text='기억하고 싶은 구절'))
        db.session.commit()
    a,b = app.test_client(),app.test_client()
    def send(c,path,method='POST',data=None):
        token=c.get('/api/session').json['csrf_token']
        return c.open('/api'+path,method=method,json=data or {},headers={'X-CSRFToken':token})
    for c,name in [(a,'alice'),(b,'bobby')]:
        assert send(c,'/register',data=dict(email=name+'@test.com',username=name,name=name,password='password8')).status_code==201
        assert send(c,'/login',data=dict(identifier=name,password='password8')).status_code==200
    assert a.get('/api/users?q=alice').json['items']==[]
    def state(c,q): return c.get('/api/users?q='+q).json['items'][0]['status']
    assert state(a,'bobby')=='none'
    assert send(a,'/friends/1').status_code==400
    assert send(a,'/friends/999').status_code==404
    assert send(a,'/friends/2').status_code==200
    assert state(a,'bobby')=='outgoing' and state(b,'alice')=='incoming'
    assert send(a,'/friends/2').status_code==409
    assert send(a,'/friends/2','PATCH').status_code==403
    assert send(a,'/friends/2','DELETE').status_code==200
    assert state(a,'bobby')=='none'
    send(a,'/friends/2'); assert send(b,'/friends/1','DELETE').status_code==200
    send(a,'/friends/2'); assert send(b,'/friends/1','PATCH').status_code==200
    assert state(a,'bobby')=='accepted'
    shared=send(b,'/comments',data=dict(passage_id=1,text='<script>not executable</script>',visibility='friends')).json
    private=send(b,'/comments',data=dict(passage_id=1,text='secret',visibility='private')).json
    feed=a.get('/api/comments?scope=friends&user_id=2').json['items']
    assert len(feed)==1 and feed[0]['song_title']=='긴 제목의 음악' and feed[0]['song_artist']=='테스트 아티스트'
    assert a.get('/api/comments/'+str(private['id'])).status_code==404
    assert send(a,'/comments/'+str(shared['id']),'DELETE').status_code==403
    for i in range(22): send(b,'/comments',data=dict(passage_id=1,text=str(i),visibility='friends'))
    assert a.get('/api/comments?scope=friends').json['pages']==2
    assert len(a.get('/api/comments?scope=friends&page=2').json['items'])==3
    assert send(a,'/friends/2','DELETE').status_code==200
    assert a.get('/api/comments?scope=friends&user_id=2').json['items']==[]
    assert a.get('/api/comments/'+str(shared['id'])).status_code==404
    assert state(a,'bobby')=='none'
    send(a,'/logout'); send(a,'/login',data=dict(identifier='alice',password='password8'))
    assert a.get('/api/friends').json['items']==[]


def test_linked_song_comment_follows_friend_and_visibility_changes(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'sharing.db'), 'SESSION_SQLALCHEMY_TABLE': 'sharing_sessions'})
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Song(id=1, provider='test', external_id='song', title='가사가 있는 곡', artist='가수'),
            Song(id=2, provider='test', external_id='another-song', title='다른 곡', artist='다른 가수'),
            LyricVersion(id=1, song_id=1, provider='test', digest='a'*64, source_url=''),
            LyricVersion(id=2, song_id=1, provider='test', digest='b'*64, source_url=''),
            Passage(id=1, version_id=1, position=0, text='이전 가사의 구절'),
            Passage(id=2, version_id=2, position=0, text='현재 가사의 구절'),
        ])
        db.session.commit()

    def send(client, path, method='POST', data=None):
        token = client.get('/api/session').json['csrf_token']
        return client.open('/api' + path, method=method, json=data or {}, headers={'X-CSRFToken': token})

    a, b = app.test_client(), app.test_client()
    for client, username in [(a, 'listener_a'), (b, 'listener_b')]:
        assert send(client, '/register', data=dict(email=username+'@example.com', username=username, name=username, password='password8')).status_code == 201
        assert send(client, '/login', data=dict(identifier=username, password='password8')).status_code == 200
    shared = send(a, '/comments', data=dict(passage_id=1, text='공유한 감상', visibility='friends')).json
    private = send(a, '/comments', data=dict(passage_id=2, text='비공개 감상', visibility='private')).json

    def feed(page=1):
        return b.get(f'/api/comments?scope=friends&page={page}').json['items']

    def song_comments(client, comment, song=1):
        return client.get(f'/api/songs/{song}/comments?comment_id={comment["id"]}').json

    assert song_comments(a, private)['focused'] == private
    assert b.get('/api/users?q=listener_a').json['items'][0]['id'] == shared['user']['id']
    assert send(b, '/friends/1').status_code == 200
    assert send(b, '/friends/1', 'PATCH').status_code == 403
    assert feed() == [] and song_comments(b, shared)['focused'] is None
    assert send(a, '/friends/2', 'PATCH').status_code == 200
    assert feed() == [shared]
    assert song_comments(b, private)['focused'] is None
    assert song_comments(b, shared, song=2)['focused'] is None

    for i in range(20):
        assert send(a, '/comments', data=dict(passage_id=2, text=str(i), visibility='friends')).status_code == 201
    result = song_comments(b, shared)
    assert shared not in result['items'] and result['focused'] == shared
    assert result['focused']['quote'] == '이전 가사의 구절'

    for visibility in ('private', 'friends'):
        assert send(a, f'/comments/{shared["id"]}', 'PATCH', dict(text=shared['text'], visibility=visibility)).status_code == 200
        assert (song_comments(b, shared)['focused'] == shared) == (visibility == 'friends')
        assert feed(2) == ([shared] if visibility == 'friends' else [])
    assert send(a, '/friends/2', 'DELETE').status_code == 200
    assert feed() == [] and song_comments(b, shared)['focused'] is None
