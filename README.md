# RE:VERSE — Flask 서비스 구현 중

기존 HTML/CSS 디자인 위에 같은 출처의 Flask JSON API를 연결했습니다.
사용자 데이터는 SQLAlchemy DB와 서버 저장 세션에 보관하며 localStorage에 저장하지 않습니다.

## 실행

Python 3.9 이상 및 MySQL 8 이상을 준비합니다.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

MySQL에서 전용 DB와 사용자 권한을 생성하고 `.env`의 DATABASE_URL을 설정하세요.
SECRET_KEY에는 충분히 긴 무작위 값을 설정하세요. 실제 `.env`는 커밋하지 않습니다.

```sql
CREATE DATABASE reverse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 're'@'localhost' IDENTIFIED BY 'replace-with-your-password';
GRANT ALL PRIVILEGES ON reverse.* TO 're'@'localhost';
```

```sh
flask --app backend:create_app db upgrade
flask --app backend:create_app run --port 5001
```

http://127.0.0.1:5001 에 접속합니다. 신규 계정은 빈 상태로 시작합니다.
운영 환경에서는 APP_ENV=production, HTTPS 및 운영 WSGI 서버를 사용해야 합니다.
현재 운영 배포 준비가 완료된 상태는 아닙니다. 로그인 호출 제한 등 추가 보강이 필요합니다.

## 구현

- 회원가입, 로그인·로그아웃, 세션 조회, 프로필 수정
- 비밀번호 해시, SQLAlchemy 서버 세션, HttpOnly/SameSite 쿠키, CSRF
- 사용자 검색, 친구 요청·취소·수락·거절·해제
- DB 곡·가수·확보한 가사 검색, 곡 상세
- 구절 코멘트 작성·수정·삭제, 공개 범위, 서버 권한 검사
- 별점·곡 기록·저장, 나의 기록 화면
- 외부 곡 ID·가사 버전·구절·평론 관계 모델과 초기 Alembic 마이그레이션

가사 버전과 구절은 별도 테이블입니다. 기존 버전 변경 없이 새 버전을 추가해야 합니다.
현재 외부 자료 수집·관리 기능은 없습니다. 따라서 신규 DB에는 음악이 없습니다.
평론은 실제 자료를 DB에 등록한 경우만 표시하며, 기존 가상 자료는 불러오지 않습니다.

## API

`GET /api/session`에서 CSRF 토큰을 받고 변경 요청에 `X-CSRFToken` 헤더를 전달합니다.

- POST /api/register, /api/login, /api/logout
- PATCH /api/profile
- GET /api/users?q=검색어&page=1
- GET /api/friends
- POST/PATCH/DELETE /api/friends/<사용자ID>
- GET /api/songs?q=검색어&page=1, /api/songs/<곡ID>
- GET/POST /api/comments
- GET/PATCH/DELETE /api/comments/<코멘트ID>
- GET /api/comments?scope=friends&user_id=사용자ID&page=1
- GET /api/records?page=1, PUT /api/records/<곡ID>
- POST /api/recommendations: 설정 보류 오류(503)

목록 API는 페이지당 20개입니다. 화면 페이지 이동 UI는 아직 구현되지 않았습니다.

## 검증과 제한

```sh
python -m pytest -q
```

SQLite 임시 DB에서 두 독립 클라이언트의 가입·로그인, 비공개 조회 차단,
타인 삭제 차단, 친구 수락 권한·중복 방지, 친구 해제 후 공유 차단,
별점·저장 계정 분리, CSRF, 로그아웃·재로그인 유지 테스트가 통과했습니다.
테스트 가사와 곡은 테스트 DB에만 생성됩니다. 외부 연동 검증이 아닙니다.

현재 MySQL 서버와 Docker 엔진이 실행되어 있지 않아 실제 MySQL 검증은 못 했습니다.
마이그레이션은 SQLite 기준으로 생성했으며 MySQL 적용 검증이 필요합니다.
브라우저 두 개·모바일 시연도 아직 검증되지 않았습니다.

외부 제공처·키 설정은 사용자 요청으로 보류했습니다. 실제 음악 검색,
가사 수집, Gemini 후보 추천, 실제 평론 수집은 미구현입니다.
기존 UI의 일부 세부 흐름(앨범 이미지·전체 목록 페이지 이동·곡 상세의 기존 코멘트 표시 등)은
추가 연결이 필요합니다. 최종 완료 상태로 보고하지 않습니다.
원격 저장소 반영 및 배포는 하지 않았습니다.
