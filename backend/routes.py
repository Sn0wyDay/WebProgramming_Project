import re
from functools import wraps
from flask import Blueprint, request, session, jsonify
from flask_wtf.csrf import generate_csrf
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from . import db
from .models import User

api = Blueprint('api', __name__)

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('user_id') or not db.session.get(User, session['user_id']):
            return jsonify(error='로그인이 필요합니다.'), 401
        return fn(*args, **kwargs)
    return wrapped

def public(user):
    return dict(id=user.id, username=user.username, name=user.name)

@api.get('/session')
def status():
    user = db.session.get(User, session['user_id']) if session.get('user_id') else None
    return jsonify(user=public(user) if user else None, csrf_token=generate_csrf())

@api.post('/register')
def register():
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip().lower()
    username = str(data.get('username', '')).strip().lower()
    name = str(data.get('name', '')).strip()
    password = data.get('password', '')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email)>254 or not re.fullmatch(r'[a-z0-9_]{3,32}', username) or not 1<=len(name)<=40 or not isinstance(password,str) or not 8<=len(password)<=128:
        return jsonify(error='이메일, 아이디(영문·숫자·밑줄 3~32자), 이름(1~40자), 비밀번호(8~128자)를 확인하세요.'),400
    user = User(email=email, username=username, name=name, password_hash=generate_password_hash(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='이미 사용 중인 이메일 또는 아이디입니다.'),409
    return jsonify(user=public(user)),201

@api.post('/login')
def login():
    data=request.get_json(silent=True) or {}
    identifier=str(data.get('identifier','')).strip().lower()
    password=data.get('password','')
    user=db.session.scalar(db.select(User).where(db.or_(User.email==identifier,User.username==identifier)))
    if not user or not isinstance(password,str) or len(password)>128 or not check_password_hash(user.password_hash,password):
        return jsonify(error='로그인 정보를 확인하세요.'),401
    session.clear()
    session['user_id']=user.id
    session.permanent=True
    from flask import current_app
    current_app.session_interface.regenerate(session)
    return jsonify(user=public(user),csrf_token=generate_csrf())

@api.post('/logout')
@login_required
def logout():
    session.clear()
    return jsonify(ok=True)

@api.patch('/profile')
@login_required
def profile():
    name=(request.get_json(silent=True) or {}).get('name')
    if not isinstance(name,str) or not 1<=len(name.strip())<=40:
        return jsonify(error='이름은 1~40자로 입력하세요.'),400
    user=db.session.get(User,session['user_id'])
    user.name=name.strip()
    db.session.commit()
    return jsonify(user=public(user))

from .models import Album, Song, Passage, LyricVersion, Comment, UserSong, Friendship, Review, ReviewSource
from flask import abort

def body():
    data=request.get_json(silent=True)
    if not isinstance(data,dict): abort(400)
    return data

def pair(other):
    uid=session['user_id']
    if uid==other: abort(400)
    return tuple(sorted((uid,other)))

def friends_with(other):
    if other==session['user_id']: return True
    relation=db.session.get(Friendship,pair(other))
    return bool(relation and relation.accepted)

def visible(comment):
    return comment.user_id==session['user_id'] or (comment.visibility=='friends' and friends_with(comment.user_id))

def comment_json(c):
    p=db.session.get(Passage,c.passage_id)
    v=db.session.get(LyricVersion,p.version_id)
    return dict(id=c.id,user=public(db.session.get(User,c.user_id)),song_id=v.song_id,passage_id=p.id,quote=p.text,text=c.text,visibility=c.visibility,created_at=c.created_at.isoformat()+'Z')

def page_query(stmt):
    try: page=max(1,int(request.args.get('page',1)))
    except ValueError: abort(400)
    result=db.paginate(stmt,page=page,per_page=20,error_out=False)
    return result

@api.get('/users')
@login_required
def users():
    q=request.args.get('q','').strip()[:100]
    stmt=db.select(User).where(User.id!=session['user_id'])
    if q: stmt=stmt.where(db.or_(User.name.contains(q,autoescape=True),User.username.contains(q,autoescape=True)))
    result=page_query(stmt.order_by(User.id))
    return jsonify(items=[public(u) for u in result.items],pages=result.pages)

@api.route('/friends/<int:other>',methods=['POST','PATCH','DELETE'])
@login_required
def friendship(other):
    if not db.session.get(User,other): abort(404)
    key=pair(other); relation=db.session.get(Friendship,key)
    if request.method=='POST':
        if relation: return jsonify(error='이미 요청 또는 친구 관계가 있습니다.'),409
        relation=Friendship(low_id=key[0],high_id=key[1],requester_id=session['user_id'])
        db.session.add(relation)
    elif request.method=='PATCH':
        if not relation: abort(404)
        if relation.requester_id==session['user_id'] or relation.accepted: abort(403)
        relation.accepted=True
    else:
        if not relation: abort(404)
        db.session.delete(relation)
    try: db.session.commit()
    except IntegrityError:
        db.session.rollback(); return jsonify(error='중복 요청입니다.'),409
    return jsonify(ok=True)

@api.get('/friends')
@login_required
def friend_list():
    uid=session['user_id']
    rows=db.session.scalars(db.select(Friendship).where(db.or_(Friendship.low_id==uid,Friendship.high_id==uid))).all()
    return jsonify(items=[dict(user=public(db.session.get(User,r.high_id if r.low_id==uid else r.low_id)),status='accepted' if r.accepted else ('outgoing' if r.requester_id==uid else 'incoming')) for r in rows])

@api.get('/songs')
@login_required
def songs():
    q=request.args.get('q','').strip()[:100]
    stmt=db.select(Song)
    if q: stmt=stmt.where(db.or_(Song.title.contains(q,autoescape=True),Song.artist.contains(q,autoescape=True),Song.id.in_(db.select(LyricVersion.song_id).join(Passage,Passage.version_id==LyricVersion.id).where(Passage.text.contains(q,autoescape=True)))))
    result=page_query(stmt.order_by(Song.id))
    return jsonify(items=[dict(id=s.id,title=s.title,artist=s.artist) for s in result.items],pages=result.pages,notice='저장된 곡·가수·가사 검색입니다.')

def album_cover(album):
    """앨범 표지 주소. 저장된 이미지가 없으면 MusicBrainz 발매 ID로 Cover Art Archive 표지를 씁니다."""
    if not album: return None
    if album.image: return album.image
    if album.provider=='musicbrainz' and album.external_id: return f'https://coverartarchive.org/release/{album.external_id}/front-500'
    return None

@api.get('/songs/<int:sid>')
@login_required
def song_detail(sid):
    s=db.get_or_404(Song,sid)
    versions=db.session.scalars(db.select(LyricVersion).where(LyricVersion.song_id==sid).order_by(LyricVersion.id.desc())).all()
    version=versions[0] if versions else None
    passages=db.session.scalars(db.select(Passage).where(Passage.version_id==version.id).order_by(Passage.position)).all() if version else []
    reviews=db.session.scalars(db.select(Review).where(Review.song_id==sid)).all()
    album=db.session.get(Album,s.album_id) if s.album_id else None
    return jsonify(id=s.id,title=s.title,artist=s.artist,album=album.title if album else None,cover=album_cover(album),provider=s.provider,external_id=s.external_id,lyrics_status='available' if passages else 'missing',passages=[dict(id=p.id,text=p.text,version_id=p.version_id) for p in passages],source_url=version.source_url if version else None,lyrics_title=version.matched_title if version else None,lyrics_match=version.match_method if version else None,reviews=[dict(title=r.title,author=r.author,url=r.url,source=db.session.get(ReviewSource,r.source_id).name,introduction=r.introduction) for r in reviews])

@api.route('/comments',methods=['GET','POST'])
@login_required
def comments():
    if request.method=='POST':
        data=body(); p=db.session.get(Passage,data.get('passage_id'))
        if not p: abort(404)
        text=data.get('text'); visibility=data.get('visibility','private')
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000 or visibility not in ('private','friends'): abort(400)
        c=Comment(user_id=session['user_id'],passage_id=p.id,text=text.strip(),visibility=visibility)
        db.session.add(c); db.session.commit()
        return jsonify(comment_json(c)),201
    uid=session['user_id']; scope=request.args.get('scope','mine')
    stmt=db.select(Comment)
    if scope=='mine': stmt=stmt.where(Comment.user_id==uid)
    elif scope=='friends':
        ids=db.select(Friendship.high_id).where(Friendship.low_id==uid,Friendship.accepted.is_(True)).union(db.select(Friendship.low_id).where(Friendship.high_id==uid,Friendship.accepted.is_(True)))
        stmt=stmt.where(Comment.user_id.in_(ids),Comment.visibility=='friends')
    else: abort(400)
    if request.args.get('user_id'): stmt=stmt.where(Comment.user_id==request.args['user_id'])
    result=page_query(stmt.order_by(Comment.id.desc()))
    return jsonify(items=[comment_json(c) for c in result.items],pages=result.pages)

@api.route('/comments/<int:cid>',methods=['GET','PATCH','DELETE'])
@login_required
def comment_item(cid):
    c=db.get_or_404(Comment,cid)
    if request.method=='GET':
        if not visible(c): abort(404)
        return jsonify(comment_json(c))
    if c.user_id!=session['user_id']: abort(403)
    if request.method=='DELETE': db.session.delete(c)
    else:
        data=body(); text=data.get('text'); visibility=data.get('visibility')
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000 or visibility not in ('private','friends'): abort(400)
        c.text=text.strip(); c.visibility=visibility
    db.session.commit(); return jsonify(ok=True)

@api.route('/records',methods=['GET'])
@login_required
def records():
    result=page_query(db.select(UserSong).where(UserSong.user_id==session['user_id']).order_by(UserSong.song_id))
    return jsonify(items=[dict(song_id=r.song_id,rating=r.rating,saved=r.saved,recorded=r.recorded) for r in result.items],pages=result.pages)

@api.put('/records/<int:sid>')
@login_required
def record_song(sid):
    db.get_or_404(Song,sid); data=body()
    if set(data)-{'rating','saved','recorded'}: abort(400)
    if 'rating' in data and (type(data['rating']) is not int or not 1<=data['rating']<=5): abort(400)
    for key in ('saved','recorded'):
        if key in data and type(data[key]) is not bool: abort(400)
    row=db.session.get(UserSong,(session['user_id'],sid))
    if not row: row=UserSong(user_id=session['user_id'],song_id=sid); db.session.add(row)
    for key,value in data.items(): setattr(row,key,value)
    db.session.commit(); return jsonify(ok=True)

@api.post('/recommendations')
@login_required
def recommend():
    return jsonify(error='Gemini 설정이 보류되었습니다. 실제 AI 연동은 검증되지 않았습니다.',code='configuration_required'),503


from .providers import musicbrainz
from .providers.http import ProviderError
from .music import import_song, fetch_lyrics, lyric_candidates

@api.errorhandler(ProviderError)
def provider_error(error):
    return jsonify(error=str(error),code=error.code),error.status

@api.get('/catalog/search')
@login_required
def catalog_search():
    query=request.args.get('q','').strip()
    try: page=int(request.args.get('page',1))
    except ValueError: abort(400)
    if not 1<=len(query)<=100 or not 1<=page<=100: abort(400)
    return jsonify(musicbrainz.search(query,page))

@api.post('/catalog/import')
@login_required
def catalog_import():
    data=body()
    external_id=data.get('external_id')
    if not isinstance(external_id,str) or not musicbrainz.MBID.fullmatch(external_id): abort(400)
    song=import_song(external_id)
    return jsonify(id=song.id)

@api.post('/songs/<int:sid>/lyrics')
@login_required
def song_lyrics(sid):
    song=db.get_or_404(Song,sid)
    data=body()
    candidate=data.get('candidate_id')
    if candidate is not None and (type(candidate) is not int or candidate<=0): abort(400)
    version=fetch_lyrics(song,candidate_id=candidate)
    if version:
        return jsonify(status='available',version_id=version.id)
    candidates=lyric_candidates(song)
    return jsonify(status='candidates' if candidates else 'missing',candidates=[dict(id=int(c['external_id']),title=c['title'],artist=c['artist'],album=c['album'],duration=c['duration'],preview='\n'.join(c['text'].splitlines()[:2])) for c in candidates])

@api.get('/songs/<int:sid>/comments')
@login_required
def song_comments(sid):
    db.get_or_404(Song,sid)
    uid=session['user_id']
    friend_ids=db.select(Friendship.high_id).where(Friendship.low_id==uid,Friendship.accepted.is_(True)).union(db.select(Friendship.low_id).where(Friendship.high_id==uid,Friendship.accepted.is_(True)))
    stmt=(db.select(Comment).join(Passage,Comment.passage_id==Passage.id)
          .join(LyricVersion,Passage.version_id==LyricVersion.id)
          .where(LyricVersion.song_id==sid,db.or_(Comment.user_id==uid,db.and_(Comment.visibility=='friends',Comment.user_id.in_(friend_ids))))
          .order_by(Comment.id.desc()))
    result=page_query(stmt)
    return jsonify(items=[comment_json(c) for c in result.items],pages=result.pages)
