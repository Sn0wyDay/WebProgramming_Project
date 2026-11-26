import os
import secrets
import time
from pathlib import Path
from datetime import timedelta
from flask import Flask, jsonify, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_session import Session
from flask_wtf.csrf import CSRFProtect, CSRFError
from dotenv import load_dotenv

db = SQLAlchemy()

def create_app(config=None):
    load_dotenv()
    app = Flask(__name__, static_folder=str(Path(__file__).resolve().parent.parent/'dist'), static_url_path='')
    @app.get('/')
    def index():
        return app.send_static_file('index.html')
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY'),
        SQLALCHEMY_DATABASE_URI=database_url,
        SESSION_TYPE='sqlalchemy', SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('APP_ENV') == 'production',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12), MAX_CONTENT_LENGTH=16384)
    if config:
        app.config.update(config)
    production = os.getenv('APP_ENV') == 'production'
    if production and (not app.config['SECRET_KEY'] or not app.config['SQLALCHEMY_DATABASE_URI']):
        raise RuntimeError('운영 환경에서는 SECRET_KEY와 DATABASE_URL을 설정하세요.')
    if not app.config['SQLALCHEMY_DATABASE_URI']:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///preview.db'
    elif app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
        app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS', {'pool_pre_ping': True})
    if not app.config['SECRET_KEY']:
        # Keep the local signing key across restarts; never ship it in Git.
        instance = Path(app.instance_path)
        instance.mkdir(parents=True, exist_ok=True)
        key_path = instance / '.secret-key'
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as key_file:
                key_file.write(secrets.token_hex(32))
        app.config['SECRET_KEY'] = key_path.read_text().strip()
        if not app.config['SECRET_KEY']:
            raise RuntimeError('로컬 세션 키 파일이 비어 있습니다.')
    # Cache public provider data only; never sessions or personal comments.
    app.config.setdefault('PROVIDER_CACHE_PATH', None if app.testing else str(Path(app.instance_path)/'provider-cache.sqlite3'))
    app.config.setdefault('RESOURCE_JOB_PATH',str(Path(app.instance_path)/'resource-jobs.sqlite3'))
    app.config.setdefault('ARTWORK_CACHE_PATH',str(Path(app.instance_path)/'artwork'))
    app.config.setdefault('ARTWORK_DOWNLOAD_ENABLED',not app.testing)
    app.config.setdefault('LRCLIB_API_KEY',os.getenv('LRCLIB_API_KEY',''))
    from .resource_jobs import ResourceQueue
    app.extensions['resource_queue']=ResourceQueue(app)
    @app.before_request
    def provider_budget():
        g.provider_deadline=time.monotonic()+18
    db.init_app(app)
    from . import models
    app.config['SESSION_SQLALCHEMY'] = db
    Session(app)
    Migrate(app, db)
    CSRFProtect(app)
    from .routes import api
    app.register_blueprint(api, url_prefix='/api')
    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return jsonify(error='요청 보안 토큰이 만료되었습니다. 다시 로그인해 주세요.'), 400
    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        if getattr(g,'provider_status',None) and response.is_json:
            payload=response.get_json()
            if isinstance(payload,dict):
                payload['_provider_status']=g.provider_status
                response.set_data(app.json.dumps(payload))
        return response
    from werkzeug.exceptions import HTTPException
    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error={400:'입력을 확인하세요.',403:'권한이 없습니다.',404:'자료를 찾을 수 없습니다.'}.get(error.code,'요청을 처리할 수 없습니다.')), error.code
    return app
