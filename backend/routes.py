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
    from .team import connect_team
    connect_team(user.id)
    db.session.commit()
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

from .models import now, Album, Song, Passage, LyricVersion, Comment, UserSong, Friendship, Review, ReviewSource
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
    song = db.session.get(Song, v.song_id)
    return dict(song_title=song.title, song_artist=song.artist,id=c.id,user=public(db.session.get(User,c.user_id)),song_id=v.song_id,passage_id=p.id,quote=p.text,text=c.text,visibility=c.visibility,created_at=c.created_at.isoformat()+'Z')

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
    items = []
    relations = db.session.scalars(db.select(Friendship).where(db.or_(Friendship.low_id==session['user_id'], Friendship.high_id==session['user_id']))).all()
    states = {(r.high_id if r.low_id==session['user_id'] else r.low_id): ('accepted' if r.accepted else 'outgoing' if r.requester_id==session['user_id'] else 'incoming') for r in relations}
    for u in result.items:
        items.append(dict(**public(u), status=states.get(u.id, 'none')))
    return jsonify(items=items,pages=result.pages)

@api.route('/friends/<int:other>',methods=['POST','PATCH','DELETE'])
@login_required
def friendship(other):
    if not db.session.get(User,other): abort(404)
    key=pair(other)
    if request.method=='PATCH':
        result=db.session.execute(db.update(Friendship).where(
            Friendship.low_id==key[0],Friendship.high_id==key[1],
            Friendship.requester_id!=session['user_id'],Friendship.accepted.is_(False),
        ).values(accepted=True))
        if not result.rowcount:
            abort(403 if db.session.get(Friendship,key) else 404)
    else:
        relation=db.session.get(Friendship,key)
        if request.method=='POST':
            if relation: return jsonify(error='이미 요청 또는 친구 관계가 있습니다.'),409
            db.session.add(Friendship(low_id=key[0],high_id=key[1],requester_id=session['user_id']))
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

from .lyric_service import availability,lookup as lookup_lyrics

def song_summary(s):
    from .providers.coverart import source_url as artwork_source
    from .artwork_service import image_for
    album=db.session.get(Album,s.album_id) if s.album_id else None
    own=db.session.get(UserSong,(session['user_id'],s.id))
    count=db.session.scalar(db.select(db.func.count(Comment.id)).join(Passage,Comment.passage_id==Passage.id).join(LyricVersion,Passage.version_id==LyricVersion.id).where(LyricVersion.song_id==s.id,Comment.user_id==session['user_id']))
    return dict(id=s.id,title=s.title,artist=s.artist,album=album.title if album else None,
                album_id=album.id if album else None,image=image_for(album),
                artwork_source=artwork_source(album.image) if album else None,rating=own.rating if own else None,
                saved=bool(own and own.saved),recorded=bool(own and own.recorded),
                home_hidden=bool(own and own.home_hidden),comment_count=count,**availability(s))


@api.get('/home')
@login_required
def home_data():
    uid=session['user_id']
    commented=db.select(LyricVersion.song_id).join(Passage,Passage.version_id==LyricVersion.id).join(Comment,Comment.passage_id==Passage.id).where(Comment.user_id==uid)
    stmt = (
        db.select(Song)
        .outerjoin(UserSong, db.and_(UserSong.song_id == Song.id, UserSong.user_id == uid))
        .where(
            UserSong.home_hidden.is_not(True),
            db.or_(UserSong.recorded.is_(True), Song.id.in_(commented)),
        )
        .order_by(UserSong.recorded_at.desc(), Song.id.desc())
    )
    result=page_query(stmt)
    note_count=db.session.scalar(db.select(db.func.count(Comment.id)).where(Comment.user_id==uid))
    return jsonify(items=[song_summary(s) for s in result.items],pages=result.pages,total=result.total,comment_count=note_count)


def search_options(data):
    field = data.get('field', 'all')
    if field not in ('all', 'title', 'artist', 'combined'):
        abort(400)
    if field == 'combined':
        for key in ('artist', 'q'):
            value = data.get(key)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
                abort(400)
        return {'field': field, 'artist': data['artist'].strip()}
    return {'field': field} if field != 'all' else {}


@api.get('/songs')
@login_required
def songs():
    q=request.args.get('q','').strip()[:100]
    options=search_options(request.args)
    field=options.get('field','all')
    stmt=db.select(Song)
    if q:
        filters=[]
        if field in ('all','title','combined'):
            filters.append(Song.title.contains(q,autoescape=True))
            corrected_ids=musicbrainz.corrected_recording_ids(q,title_only=field!='all')
            if corrected_ids:
                filters.append(db.and_(Song.provider=='musicbrainz',Song.external_id.in_(corrected_ids)))
        if field in ('all','artist'):
            filters.append(Song.artist.contains(q,autoescape=True))
        if field=='all':
            filters.append(Song.id.in_(db.select(LyricVersion.song_id).join(Passage,Passage.version_id==LyricVersion.id).where(Passage.text.contains(q,autoescape=True))))
        stmt=stmt.where(db.or_(*filters))
        if field=='combined':
            stmt=stmt.where(Song.artist.contains(options['artist'],autoescape=True))
    result=page_query(stmt.order_by(Song.id))
    return jsonify(items=[song_summary(s) for s in result.items],pages=result.pages,notice='저장된 곡·가수·가사 검색입니다.')

@api.get('/songs/<int:sid>')
@login_required
def song_detail(sid):
    s=db.get_or_404(Song,sid)
    versions=db.session.scalars(db.select(LyricVersion).where(LyricVersion.song_id==sid).order_by(LyricVersion.id.desc())).all()
    version=versions[0] if versions else None
    passages=db.session.scalars(db.select(Passage).where(Passage.version_id==version.id).order_by(Passage.position)).all() if version else []
    from .reviews import for_song
    return jsonify(**song_summary(s),provider=s.provider,external_id=s.external_id,passages=[dict(id=p.id,text=p.text,version_id=p.version_id) for p in passages],source_url=version.source_url if version else None,lyrics_title=version.matched_title if version else None,lyrics_match=version.match_method if version else None,reviews=for_song(s))


def review_options(data):
    if set(data)-{'refresh'} or type(data.get('refresh',False)) is not bool:abort(400)
    return dict(refresh=data.get('refresh',False))


@api.post('/songs/<int:sid>/reviews')
@login_required
def song_reviews(sid):
    from .reviews import lookup
    data=body() if request.get_data() else {}
    return jsonify(lookup(db.get_or_404(Song,sid),**review_options(data)))


@api.post('/songs/<int:sid>/artwork')
@login_required
def song_artwork(sid):
    from .artwork_service import lookup
    return jsonify(lookup(db.get_or_404(Song,sid)))


@api.post('/songs/<int:sid>/resources/<kind>')
@login_required
def start_resource(sid,kind):
    from .resource_jobs import queue,response
    song=db.get_or_404(Song,sid)
    if kind not in ('lyrics','reviews','artwork'):abort(404)
    data=body();options={}
    if kind=='lyrics':
        if set(data)-{'refresh','candidate_id'}:abort(400)
        if 'refresh' in data and type(data['refresh']) is not bool:abort(400)
        if 'candidate_id' in data and (type(data['candidate_id']) is not int or data['candidate_id']<=0):abort(400)
        options=dict(refresh=data.get('refresh',False))
        if 'candidate_id' in data:options['candidate_id']=data['candidate_id']
        # Already-saved passages never wait for a queue or an external service.
        if not options['refresh'] and 'candidate_id' not in options:
            from .lyric_service import latest
            version=latest(song)
            if version:return jsonify(status='completed',result=dict(status='available',version_id=version.id,from_database=True))
    elif kind=='reviews':options=review_options(data)
    elif data:abort(400)
    if kind=='reviews':
        from .reviews import for_song
        items=for_song(song)
        if items:return jsonify(status='completed',result=dict(status='available',reviews=items,from_database=True))
    if kind=='artwork':
        from .artwork_service import cached
        item=cached(song)
        if item:return jsonify(status='completed',result=item)
    manager=queue()
    job=manager.store.submit(sid,kind,options,identity=song.album_id if kind=='artwork' else None)
    manager.start();manager.wake.set()
    result=response(job)
    return jsonify(result),202 if result['status']=='pending' else 200


@api.get('/resource-jobs/<job_id>')
@login_required
def resource_status(job_id):
    from .resource_jobs import queue,response
    if not re.fullmatch('[0-9a-f]{32}',job_id):abort(404)
    manager=queue();job=manager.store.get(job_id)
    if not job:abort(404)
    manager.start()
    return jsonify(response(job))


@api.get('/media/artwork/<name>')
def cached_artwork(name):
    from flask import send_file
    from .artwork_service import cached_file,image_type
    path=cached_file(name)
    if not path:abort(404)
    with path.open('rb') as source:mime=image_type(source.read(16))
    if not mime:abort(404)
    return send_file(path,mimetype=mime,conditional=True,max_age=86400)

@api.route('/comments',methods=['GET','POST'])
@login_required
def comments():
    if request.method=='POST':
        data=body(); p=db.session.get(Passage,data.get('passage_id'))
        if not p: abort(404)
        text=data.get('text'); visibility=data.get('visibility','private')
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000 or visibility not in ('private','friends'): abort(400)
        c=Comment(user_id=session['user_id'],passage_id=p.id,text=text.strip(),visibility=visibility)
        db.session.add(c)
        version=db.session.get(LyricVersion,p.version_id)
        row=db.session.get(UserSong,(session['user_id'],version.song_id))
        if row is None:
            row=UserSong(user_id=session['user_id'],song_id=version.song_id)
            db.session.add(row)
        if not row.recorded:row.recorded=True;row.recorded_at=now()
        db.session.commit()
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
    if set(data)-{'rating','saved','recorded','home_hidden'}: abort(400)
    if 'rating' in data and (type(data['rating']) is not int or not 1<=data['rating']<=5): abort(400)
    for key in ('saved','recorded','home_hidden'):
        if key in data and type(data[key]) is not bool: abort(400)
    row=db.session.get(UserSong,(session['user_id'],sid))
    if not row: row=UserSong(user_id=session['user_id'],song_id=sid); db.session.add(row)
    if data.get('recorded') and (not row.recorded or (row.home_hidden and data.get('home_hidden') is False)):
        row.recorded_at = now()
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
    response=jsonify(error=str(error),code=error.code,retry_after=error.retry_after)
    if error.retry_after:response.headers['Retry-After']=str(error.retry_after)
    return response,error.status

@api.get('/catalog/search')
@login_required
def catalog_search():
    query=request.args.get('q','').strip()
    try: page=int(request.args.get('page',1))
    except ValueError: abort(400)
    if not 1<=len(query)<=100 or not 1<=page<=100: abort(400)
    return jsonify(musicbrainz.search(query,page,**search_options(request.args)))


@api.post('/catalog/search-jobs')
@login_required
def catalog_search_job():
    from flask import g
    from .resource_jobs import queue,response
    data=body()
    if set(data)-{'q','page','field','artist'}:abort(400)
    query=data.get('q');page=data.get('page',1)
    if not isinstance(query,str) or not 1<=len(query.strip())<=100 or type(page) is not int or not 1<=page<=100:abort(400)
    options=dict(query=query.strip(),page=page)
    options.update(search_options(data))
    saved=musicbrainz.cached_search(**options)
    if saved is not None:
        info=getattr(g,'provider_status',{})
        if info.get('mode')=='stale':
            manager=queue();manager.store.submit(0,'catalog',options);manager.start();manager.wake.set()
        return jsonify(status='completed',result={**saved,'_provider_status':info})
    manager=queue();job=manager.store.submit(0,'catalog',options);manager.start();manager.wake.set()
    result=response(job)
    return jsonify(result),202 if result['status']=='pending' else 200

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
    if 'refresh' in data and type(data['refresh']) is not bool:abort(400)
    candidate=data.get('candidate_id')
    if candidate is not None and (type(candidate) is not int or candidate<=0): abort(400)
    return jsonify(lookup_lyrics(song,refresh=data.get('refresh',False),candidate_id=candidate))

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
    payload=dict(items=[comment_json(c) for c in result.items],pages=result.pages)
    if 'comment_id' in request.args:
        comment_id=request.args.get('comment_id',type=int)
        if comment_id is None or not 1<=comment_id<=2**63-1: abort(400)
        focused=db.session.scalar(stmt.where(Comment.id==comment_id))
        payload['focused']=comment_json(focused) if focused else None
    return jsonify(payload)


@api.get('/friends/<int:uid>/profile')
@login_required
def friend_profile(uid):
    from .models import TeamProfile
    if uid != session['user_id'] and not friends_with(uid):
        abort(404)
    person = db.get_or_404(User, uid)
    showcase = db.session.get(TeamProfile, uid)
    track = db.session.get(Song, showcase.song_id) if showcase else None
    stmt = db.select(Comment).where(Comment.user_id == uid, Comment.visibility == 'friends')
    result = page_query(stmt.order_by(Comment.id.desc()))
    count = db.session.scalar(db.select(db.func.count()).select_from(Comment).where(Comment.user_id == uid, Comment.visibility == 'friends'))
    return jsonify(user=public(person), featured_song=dict(id=track.id, title=track.title, artist=track.artist) if track else None,
                   items=[comment_json(c) for c in result.items], pages=result.pages, public_count=count)


@api.get('/report/discovery')
@login_required
def report_discovery():
    seed = request.args.get('seed', type=int)
    genre = request.args.get('genre', '')
    if not seed or (genre and genre not in musicbrainz.REPORT_GENRES):
        abort(400)
    song = db.get_or_404(Song, seed)
    return jsonify(items=musicbrainz.report_candidates(song, genre))
