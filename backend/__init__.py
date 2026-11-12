import os
from pathlib import Path
from datetime import timedelta
from flask import Flask, jsonify
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
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL'),
        SESSION_TYPE='sqlalchemy', SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('APP_ENV') == 'production',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12), MAX_CONTENT_LENGTH=16384)
    if config:
        app.config.update(config)
    if not app.config['SECRET_KEY'] or not app.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError('SECRET_KEY와 DATABASE_URL을 설정하세요.')
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
        return response
    from werkzeug.exceptions import HTTPException
    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error={400:'입력을 확인하세요.',403:'권한이 없습니다.',404:'자료를 찾을 수 없습니다.'}.get(error.code,'요청을 처리할 수 없습니다.')), error.code
    return app
