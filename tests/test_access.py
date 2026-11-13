from backend import create_app, db
from backend.models import Song, LyricVersion, Passage

def test_two_accounts(tmp_path):
 app=create_app({'TESTING':True,'SECRET_KEY':'test','SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'test.db')})
 with app.app_context():
  db.create_all()
  db.session.add(Song(id=1,provider='test',external_id='1',title='test',artist='test'))
  db.session.add(LyricVersion(id=1,song_id=1,provider='test',digest='a'*64,source_url='https://example.com'))
  db.session.add(Passage(id=1,version_id=1,position=0,text='test fixture'));db.session.commit()
 def send(c,path,method='POST',data=None):
  t=c.get('/api/session').json['csrf_token']
  return c.open('/api'+path,method=method,json=data,headers={'X-CSRFToken':t})
 a,b=app.test_client(),app.test_client()
 for c,name in [(a,'alice'),(b,'bobby')]:
  assert send(c,'/register',data=dict(email=name+'@example.com',username=name,name=name,password='secure-password-123')).status_code==201
  assert send(c,'/login',data=dict(identifier=name,password='secure-password-123')).status_code==200
 cid=send(a,'/comments',data=dict(passage_id=1,text='private',visibility='private')).json['id']
 assert b.get('/api/comments/'+str(cid)).status_code==404
 assert b.get('/api/songs/1/comments').json['items']==[]
 assert send(b,'/comments/'+str(cid),'DELETE').status_code==403
 assert send(a,'/friends/2').status_code==200
 assert send(a,'/friends/2','PATCH').status_code==403
 assert send(a,'/friends/2').status_code==409
 assert send(b,'/friends/1','PATCH').status_code==200
 assert b.get('/api/comments/'+str(cid)).status_code==404
 assert b.get('/api/songs/1/comments').json['items']==[]
 assert send(a,'/comments/'+str(cid),'PATCH',dict(text='shared',visibility='friends')).status_code==200
 assert len(b.get('/api/comments?scope=friends').json['items'])==1
 assert len(b.get('/api/songs/1/comments').json['items'])==1
 assert send(b,'/friends/1','DELETE').status_code==200
 assert b.get('/api/comments/'+str(cid)).status_code==404
 assert b.get('/api/songs/1/comments').json['items']==[]
 assert b.get('/api/comments?scope=friends').json['items']==[]
 assert send(a,'/records/1','PUT',dict(rating=5,saved=True)).status_code==200
 assert b.get('/api/records').json['items']==[]
 assert a.patch('/api/profile',json={}).status_code==400
 assert send(a,'/logout').status_code==200
 assert a.get('/api/records').status_code==401
 assert send(a,'/login',data=dict(identifier='alice',password='secure-password-123')).status_code==200
 assert a.get('/api/records').json['items'][0]['saved'] is True

def test_password_minimum_eight(tmp_path):
 app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'password_test_sessions','SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'password.db')})
 with app.app_context(): db.create_all()
 c=app.test_client()
 token=c.get('/api/session').json['csrf_token']
 def register(password):
  return c.post('/api/register',json=dict(email='eight@example.com',username='eight',name='Eight',password=password),headers={'X-CSRFToken':token})
 assert register('1234567').status_code==400
 assert register('12345678').status_code==201
 assert c.post('/api/login',json=dict(identifier='eight',password='12345678'),headers={'X-CSRFToken':token}).status_code==200
