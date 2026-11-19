from backend import create_app,db
from backend.models import User,Friendship,TeamProfile,Song,Comment,Passage,LyricVersion
from backend.team import seed_team
from werkzeug.security import generate_password_hash

def test_team_profile_privacy_and_seed(tmp_path):
 app=create_app({'TESTING':True,'SECRET_KEY':'test','SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'profiles.db'),'SESSION_SQLALCHEMY_TABLE':'profile_sessions'})
 with app.app_context():
  db.create_all()
  owner=User(name='손주희',username='juhee',email='juhee@test.com',password_hash=generate_password_hash('password8'))
  db.session.add(owner);db.session.commit();uid=owner.id
  seed_team();seed_team()
  assert db.session.query(TeamProfile).count()==4
  assert db.session.query(User).count()==4
  assert db.session.query(Friendship).count()==6
  target=db.session.scalar(db.select(User).where(User.name=='안민기'));tid=target.id
  profile=db.session.get(TeamProfile,tid);sid=profile.song_id
  db.session.add(LyricVersion(id=1,song_id=sid,provider='test',digest='a'*64,source_url='https://example.com'));db.session.add(Passage(id=1,version_id=1,position=0,text='test'))
  db.session.add(Comment(user_id=tid,passage_id=1,text='public',visibility='friends'));db.session.add(Comment(user_id=tid,passage_id=1,text='secret',visibility='private'));db.session.commit()
 c=app.test_client()
 assert c.get(f'/api/friends/{tid}/profile').status_code==401
 token=c.get('/api/session').json['csrf_token']
 assert c.post('/api/login',json={'identifier':'juhee','password':'password8'},headers={'X-CSRFToken':token}).status_code==200
 data=c.get(f'/api/friends/{tid}/profile').json
 assert data['featured_song']['title']=='0g' and data['featured_song']['artist']=='리도어'
 assert data['public_count']==1 and len(data['items'])==1 and data['items'][0]['text']=='public'
 token=c.get('/api/session').json['csrf_token'];assert c.delete(f'/api/friends/{tid}',headers={'X-CSRFToken':token}).status_code==200
 with app.app_context(): seed_team()
 assert c.get(f'/api/friends/{tid}/profile').status_code==404
 assert c.get(f'/api/friends/{uid}/profile').json['featured_song']['title']=='시간이 날 기다려'
