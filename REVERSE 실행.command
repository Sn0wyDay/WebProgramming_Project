#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo '처음 실행에 필요한 환경을 준비합니다. Python 3.9 이상이 필요합니다.'
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import flask, flask_sqlalchemy, flask_migrate, flask_session, flask_wtf, dotenv, bs4' >/dev/null 2>&1; then
  echo '필요한 라이브러리를 설치합니다. 첫 실행에는 인터넷이 필요합니다.'
  if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    .venv/bin/python -m ensurepip --upgrade
  fi
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python launch.py
