# 최신 GitHub 기준 친구 기능 통합
기준: origin/main 7fca472.
홈과 곡 상세·검색·표지·평론 모듈은 원본 그대로 유지하고 친구 담당 UI와 관련 서버 기능만 추가했습니다.
기존 DB를 복사해 계정·감상·친구 관계·가사를 보존했습니다. 이전 reverse-friends 폴더는 그대로 남아 있습니다.
검증: 자동화 테스트 99개 통과. Edge와 실제 Flask 테스트 클라이언트로 홈/친구 왕복, LP 회전, 사이드바 4열, 프로필, 공유 알림, 모바일과 모션 감소를 검사했습니다.
외부 API 전체 곡의 실제 응답을 새로 검증하지는 않았습니다.
실행: python -m pip install -r requirements.txt 다음 python run.py.
주소: http://127.0.0.1:5001/#friends
GitHub 업로드는 하지 않았습니다.
