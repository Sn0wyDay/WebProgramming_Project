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
