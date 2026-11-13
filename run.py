"""Local class-project runner: python run.py"""
import os
from pathlib import Path
from flask_migrate import upgrade
from backend import create_app


def prepare_app():
    app = create_app()
    with app.app_context():
        upgrade(directory=str(Path(__file__).resolve().parent / 'migrations'))
    return app


if __name__ == '__main__':
    prepare_app().run(host='127.0.0.1', port=int(os.environ.get('PORT', '5001')))
