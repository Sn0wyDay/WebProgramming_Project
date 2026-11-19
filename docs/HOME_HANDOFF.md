# 홈·곡 상세 담당 범위와 팀 통합

## 디자인 기준

API 연결 이전 커밋 `87e9b7c`의 `home`, `card`, `detail`, `editor` 레이아웃을 기준으로 복원했다.
기존 녹색 색상·반응형 CSS, 상단 메뉴, 홈 통계·앨범 카드·음악 추가 모달,
곡 상세의 앨범 영역·별점·줄 번호·구절별 작성창·평론 패널을 사용한다.
실제 계정 기록을 표시하며, 과거 가상 곡·평론·친구를 계정에 자동으로 넣지 않는다.
앨범 이미지가 없으면 같은 디자인의 기본 커버를 사용하며 실제 앨범 이미지라고 표시하지 않는다.

## 수정할 파일

| 파일 | 역할 |
| --- | --- |
| `dist/home.js` | 홈·음악 추가 모달·곡 상세·가사 작성 및 코멘트 CRUD |
| `dist/home.css` | 홈과 곡 상세에 적용하는 작은 추가 스타일 |
| `dist/style.css` | 이전 커밋의 공통 디자인, 이번 작업에서는 보존 |
| `dist/ui.js` | 공통 아이콘과 출력 이스케이프 함수 |
| `dist/script.js` | 인증·메뉴·라우팅, 기존 친구·AI·기록 연결부 |
| `backend/routes.py` | 서버 API: `/home`, 음악·가사·기록·코멘트 등 |
| `backend/providers/` | MusicBrainz·LRCLIB·Cover Art Archive 어댑터, 공개 응답 캐시·호출 제어 |

다른 페이지는 이번 작업의 디자인 복원 범위에 포함하지 않았다.
팀원은 `script.js`의 `#friends`, `#ai`, `#records` 라우트를 자기 페이지 모듈로 교체하면 된다.
공통 세션·CSRF와 DB 모델은 합의 후 함께 사용한다. 각자 `home.js`를 수정할 필요는 없다.

```js
// ui.js, home.js를 먼저 로드하고 공통 인증 초기화 후 호출한다.
REHome.configure({api, getUser: () => loggedInUser});
await REHome.renderHome();
await REHome.renderSong(songId);
// 다른 담당 페이지로 이동할 때 실행 중인 홈 렌더링을 취소한다.
REHome.leave();
```

`api(path, method='GET', data)`는 `/api`를 접두사로 붙이고 Fetch 결과 JSON을 반환한다.
변경 요청에는 현재 계정의 `X-CSRFToken`을 붙여야 한다.
실패 시 `Error`에 `code`, `retry_after`를 붙인다. 로그인 사용자는 `{id, username, name}`이다.
홈 전용 이벤트는 `data-home-action`, `data-home-form`을 사용해 다른 페이지 이벤트와 구분했다.

## 공유 API

| API | 홈에서의 용도 |
| --- | --- |
| `GET /api/home?page=1` | 현재 계정의 기록 음악·별점·저장 여부·코멘트 수·홈 통계 |
| `GET /api/songs?q=&page=1` | DB에 확보한 음악·가사 검색 |
| `GET /api/catalog/search?q=&page=1` | 외부 음악 검색 |
| `POST /api/catalog/search-jobs` | 홈의 비동기 외부 검색, `{q,page}` |
| `POST /api/catalog/import` | 서버가 확인한 외부 곡 ID로 메타데이터 가져오기 |
| `GET /api/songs/<id>` | DB에 저장된 가사와 곡 정보, 내 별점·저장 여부 |
| `POST /api/songs/<id>/artwork` | 앨범 표지 별도 조회: status, image, source_url, retry_after |
| `POST /api/songs/<id>/reviews` | 평론 별도 조회: status, reviews, retry_after |
| `POST /api/songs/<id>/lyrics` | 기본 `{}`은 저장 가사를 재사용; `{refresh:true}`만 새 조회 |
| `POST /api/songs/<id>/resources/<kind>` | 홈의 비동기 lyrics/reviews/artwork 조회 |
| `GET /api/resource-jobs/<job_id>` | 공개 자료 조회 상태·결과 확인 |
| `GET /api/media/artwork/<hash>.img` | 확보한 표지 파일 표시 |
| `PUT /api/records/<id>` | 내 별점·곡 저장·기록 추가 |
| `GET /api/songs/<id>/comments?page=1` | 작성자/친구 관계로 필터링한 구절별 코멘트 |
| `POST /api/comments` | `{passage_id, text, visibility}` 저장 |
| `GET/PATCH/DELETE /api/comments/<id>` | 조회·편집·삭제 |

곡 추가 후 `recorded:true`로 내 기록에 등록한다. 코멘트 작성 시에도 서버가 내 기록에 등록한다.
홈은 다른 사람의 기록이나 개인 코멘트가 아닌 현재 계정의 기록을 집계한다.
가사 구절 ID와 코멘트 연결은 유지한다. 예전 가사 버전 코멘트는 작성 당시 구절과 별도 보관한다.
작성창은 같은 구절 재클릭으로 닫히며, 저장된 코멘트는 구절 아래 계속 표시된다.

## API 안정성 대책

문제는 두 부분이다. MusicBrainz가 실제로 반환하는 503/호출 제한과,
성공한 응답을 메모리에만 보관해서 재시작 후 다시 요청하던 앱 구조다.
제공처 서버 장애는 앱 코드에서 없앨 수 없다. 캐시·DB 우선 사용으로 영향을 줄였다.

- 실제 계정 데이터는 `instance/preview.db`, 공개 API 응답만 별도의 `instance/provider-cache.sqlite3`에 저장한다.
- 공개 응답은 기본 24시간 재사용한다. 장애 때는 최대 7일 이내 기존 응답을 사용하고 화면에 표시한다.
- 빈 결과·404는 5분만 캐시한다. 첫 검색부터 실패했고 캐시도 없으면 성공으로 꾸미지 않는다.
- 가사·구절이 이미 DB에 있으면 페이지 이동·새로고침에 외부 API를 호출하지 않는다.
- 검색은 입력할 때마다 실행하지 않고 검색 버튼으로 요청한다.
- 같은 프로세스의 잠금과 SQLite의 요청 임대로 중복 요청을 줄인다. 여러 로컬 프로세스의 호출 간격·대기 시간을 공유한다.
- MusicBrainz 1.05초, LRCLIB 0.5초의 호출 간격을 지킨다.
- 429/503은 즉시 반복하지 않고 `Retry-After`의 초/HTTP 날짜를 존중한다. 이 대기 상태도 재시작 후 유지한다.
- 네트워크 오류·일부 502/504는 최대 한 번만 재시도한다. API 요청의 외부 조회 예산은 18초, 각 HTTP 요청은 최대 5초다.
- 이미 확인한 가수 별칭을 재사용해 `리도어 → Redoor` 변환에 매번 여러 요청을 보내지 않는다.
- 검색으로 서버가 확인한 곡 정보도 캐시해, 선택 시 불필요한 곡 재조회를 줄인다.
- 외부 검색이 실패하면 모달에서 대기 시간을 안내하고 ‘저장된 음악 보기’로 전환할 수 있다.

캐시 사용 JSON에는 `_provider_status.mode`가 `cache` 또는 `stale`로 붙는다.
가사 DB 재사용은 `from_database:true`로 구분한다. 캐시를 새로운 실시간 응답이라고 표시하지 않는다.

## 시연과 제공처 선택

수업 전에 사용할 곡을 검색하고 선택해서 가사까지 확보해 두는 구성이 가장 가볍다.
이후 해당 곡의 별점·저장·코멘트 시연은 DB를 사용한다.
캐시가 없는 새 곡을 인터넷 장애 중에도 검색할 수 있다고 보장하지 않는다.

MusicBrainz는 [비상업용 공개 API](https://musicbrainz.org/doc/MusicBrainz_API)이며,
[호출 제한 문서](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting)에서 503이 혼잡과 호출 제한 모두에 사용됨을 설명한다.
LRCLIB는 [공개 API 문서](https://lrclib.net/docs)를 제공하지만 곡별 가사 등록을 보장하지 않는다.

추가 대안으로 Apple의 [iTunes Search API](https://performance-partners.apple.com/search-api)를 검토했다.
공식 검색·조회 API지만 오픈소스 제공처는 아니며 자체 호출 제한과 이미지 이용 조건이 있다.
기존 오픈소스 제공처 선택을 유지하기 위해 이번에는 추가하지 않았다.
나중에 보조 제공처를 넣으면 제공처별 외부 ID와 중복 곡 연결 기준도 별도로 정해야 한다.

## 검증 (2026-11-17)

- 자동화 테스트 36개: 인증·권한·불변 구절·후보 확인, 계정별 홈 집계, 영구 캐시,
  실제 Python 프로세스 재시작 후 캐시 읽기, 장애 시 캐시 표시, 대기 유지,
  두 클라이언트의 중복 호출 억제, 제한된 재시도 등을 확인했다. 외부 장애 응답은 모의 응답이다.
- 실제 제공처: 최초 MusicBrainz 조회는 503. 이후 재검증에서 리도어 녹음 24건과
  LRCLIB Shadow of You 응답을 실제로 받았다. 새 클라이언트의 동일 LRCLIB 요청은 HTTP 호출 없이 디스크 캐시에서 반환됐다.
- 격리된 브라우저/임시 DB: 이전 홈 카드·모달·상세·가사 레이아웃,
  구절 작성·저장·재클릭 닫기·새로고침 유지, 제공처 오류 안내와 저장된 음악 전환을 확인했다.
- 현재 브라우저 실측은 데스크톱 기준이다. 원래 반응형 CSS는 유지했다.

테스트 데이터는 실제 계정 DB에 추가하지 않았다. 현재 변경은 로컬 작업이며 원격 배포를 포함하지 않는다.


## 가사 조회 후속 수정 (2026-11-17)

가사 조회 실패 원인을 실제 요청으로 재현해 아래를 수정했습니다.

1. 가사가 안 맞을 때 MusicBrainz의 추가 별칭 조회가 503을 반환하면 LRCLIB 후보 검색까지 중단되던 문제:
   가사 경로에서는 MusicBrainz HTTP를 호출하지 않습니다. 별칭은 이미 저장된 캐시와 출처 확인 대응표만 사용합니다.
2. 후보 검색에 `q` 또는 `track_name`이 필요한데 가수·앨범 필드만 보낸 문제:
   현재 `q=가수 앨범`을 보내고 응답의 가수·앨범·재생시간을 서버에서 다시 검증합니다.
3. 아직 조회 전·반주 버전·일치 결과 없음·후보 확인 필요·일시적 실패를 한 문구로 처리하던 문제:
   `lyrics_status`를 세분화하고 `lyrics_message`, `lyrics_retry_after`를 함께 반환합니다.
4. 반복 실패 버튼: 조회 중 중복 클릭을 막고, 실패 시 서버의 대기 시간에 맞춰 카운트다운합니다.

새 `lyric_lookup` 테이블에는 곡의 공개 조회 상태만 저장합니다. 댓글의 공개 범위나 소유권은 변경하지 않습니다.
새 마이그레이션은 `python run.py`가 적용합니다. 저장된 가사를 갱신하다 실패하면 `from_database:true`,
`refresh_failed:true`와 안내 문구를 반환하고 원래 구절·코멘트를 보존합니다.

실제 `욕망주사기`의 영문명 `Syringe`를 [공식 앨범 페이지](https://www.joox.com/th/album/fl6A3PmEZzmV0L8rXFZrNA%3D%3D)에서 확인해 대응표에 추가했습니다.
실제 LRCLIB 응답으로 한국어 가사 30구절을 저장했고, MusicBrainz 네트워크 호출을 차단한 상태에서도 연결을 확인했습니다.
브라우저에서도 실제 가사 표시 및 `Tik Tak Tok (instrumental)` 반주 안내·조회 버튼 비활성화를 확인했습니다.
반주 버전이라는 판정과 ‘제공처에 일치 결과가 없다’는 판정은 별개입니다.
외부 LRCLIB 자체 장애나 모든 곡의 가사 등록을 보장하지는 않습니다.

## 앨범 표지와 저장 아이콘

곡 응답의 `album_id`, `image`, `artwork_source`를 사용합니다. 홈·목록·상세를 읽는 API는
표지 제공처에 요청하지 않습니다. `home.js`가 이미지 없는 앨범을 모아
`POST /songs/<id>/artwork`를 하나씩 요청하고 같은 앨범의 중복 요청을 합칩니다.
결과의 상태는 `available`, `missing`, `unavailable`입니다. 실패해도 음악 화면은 유지합니다.

`backend/providers/coverart.py`는 CAA 발매 ID → 승인된 앞표지 → HTTPS URL을 확인합니다.
해당 발매판 표지가 없으면 MusicBrainz의 정확한 release → release-group 관계로만 보완합니다.
제목이 비슷한 다른 앨범 표지를 선택하지 않습니다. 성공한 URL은 기존 `Album.image`에 저장합니다.
내부 출처 정보는 이미지의 실제 발매판으로 연결합니다. 표지를 위한 새 마이그레이션은 필요하지 않습니다.

표지 메타데이터는 기존 디스크 캐시·호출 간격·타임아웃·제한된 재시도를 사용합니다.
404/빈 결과는 5분, 일시 실패는 최소 60초 재요청 대기입니다. 이미지 다운로드 오류나
12초 초과는 기본 커버로 되돌아갑니다. 실제 표지를 읽은 경우 색상 필터와 가상 앨범명 오버레이를 제거합니다.

북마크는 서버 응답의 `saved`에 따라 `.saved`와 `aria-pressed`를 설정하며,
홈과 곡 상세에서 아이콘 내부도 초록색으로 채웁니다. 저장 취소 시 윤곽선만 남깁니다.

개발 문서 출처: [공식 API](https://musicbrainz.org/doc/Cover_Art_Archive/API),
[MIT 오픈소스 서버](https://github.com/metabrainz/artwork-redirect).
서버 코드 라이선스가 앨범 이미지 자체의 라이선스를 의미하지는 않습니다.
실제 브라우저 검증: Hospital 두 곡과 NO PAIN 표지 표시, 상세 화면 저장 취소/재저장 색 변화.
표지의 외부 응답 모의 테스트 5개를 포함해 전체 36개 테스트가 통과했습니다.

화면 정리: 홈 카드·곡 상세의 표지 출처 링크, 가사 출처·다른 제목 안내,
서비스 안내의 음악·가사 제공처 이름을 제거했습니다. 출처 메타데이터와 API 연동은 유지합니다.

## 실제 평론 모듈

`backend/providers/izm.py`는 사이트가 공개 검색에서 사용하는 JSON 경로
`https://api.izm.co.kr/api/content/search/?keyword=...`를 읽습니다.
Beautiful Soup으로 HTML을 정리해 짧은 발췌와 명시된 수록곡 목록만 유지합니다.
`JsonClient.transform`이 디스크에 쓰기 전에 원문 HTML·아티클·개인 연락처 등을 버립니다.
필요한 검색은 최대 곡명·앨범명·가수명 3개이며 같은 검색어는 중복 호출하지 않습니다.
HTTP 간격·잠금·429/503 대기·한 번의 재시도·18초 예산은 기존 제공처 클라이언트를 공유합니다.

가수 표기가 맞고, 곡명/앨범명/번호가 붙은 수록곡 목록이 일치하는 리뷰만 채택합니다.
영문 가수 별칭을 확장할 때에는 recording ID → 단일 artist ID → aliases로 확인합니다.
공동 아티스트나 동명이인 이름 검색을 임의의 솔로 가수로 대체하지 않습니다.
한글 가수명이나 직접 일치하는 리뷰가 있으면 별칭 조회를 생략합니다.

`backend/reviews.py`가 실제 메타데이터를 저장하고 `ReviewLink`로 여러 곡에 연결합니다.
기존 `Review.song_id`는 최초 연결의 호환 필드로 남으며, 상세 조회는 `ReviewLink`를 사용합니다.
마이그레이션 `7c49e8a0f21d`가 기존 평론의 연결도 보존합니다. `python run.py`에서 자동 적용됩니다.
`GET /songs/<id>`는 저장된 평론만 읽고, 조회 API는 로그인·CSRF가 필요합니다.
조회에는 공개 음악 정보만 전달하며 계정의 코멘트·이메일 등은 전송하지 않습니다.

프론트엔드는 곡 상세를 연 뒤 별도로 평론을 조회합니다. 계정별 기록을 추가하거나 변경하지 않습니다.
작성자, 곡/앨범 평론 구분, 제목, 짧은 발췌, 원문 읽기만 표시하고 제공처 이름은 숨깁니다.
없음(5분)과 장애(최소 60초)를 구분하고 중복 요청을 막습니다. 가사 작성창은 다시 그리지 않습니다.

실제 임시 DB 검증: 밤편지 / 홍은솔 / 곡 평론 / IZM 28308,
NO PAIN → Power Andre 99 / 김태훈 / 수록 앨범 평론 / IZM 32362.
원문 URL과 작성자, 연결 방식, 발췌 길이를 검증했으며 외부 조회를 막아도 저장 결과를 읽었습니다.
재검증: `python -m scripts.verify_reviews`. 자동화 테스트 43개에는 모의 응답 기반 평론 테스트 7개가 포함됩니다.
리도어 Hospital 관련 검색에서는 현재 적합한 평론을 찾지 못했습니다. 발매 보도나 상품평을 평론으로 표시하지 않습니다.

## 가사 병기 회귀 수정

원인: 잔나비 곡의 LRCLIB 검색에는 실제 결과가 있었지만 `JANNABI(잔나비)`가 내부 가수명 `잔나비`와
다르다고 판단해 모두 제외했습니다. 현재 `bilingual_artist_keys`가 괄호·대괄호 안의 한글/영문 병기를 인식합니다.
임의 부분 문자열, 피처링, 쉼표 뒤의 앨범 정보 등은 병기 이름으로 확장하지 않습니다.

`find`는 가수 필터 결과가 없으면 곡명 단독 검색을 추가합니다. 검증을 완화하지 않고 조회 범위만 넓힙니다.
동일 검색 결과에서는 앨범 일치 → 재생시간 차이 → 제목/ID 순서로 선택합니다.
재생시간 없는 결과나 Inst./Live/Cover/Slowed 등 다른 버전은 자동 연결하지 않습니다.
기존 공식 제목 대응표는 앨범·재생시간까지 맞아야 사용하며, 모르는 번역은 확인 후보로 남깁니다.
`music.artist_aliases`는 recording ID에 묶여 이미 확보한 이름을 먼저 읽으며 새 MusicBrainz HTTP 요청은 하지 않습니다.

미등록 결과의 5분 대기는 `refresh:true`도 지키며 API의 `retry_after`와 상세의 `lyrics_retry_after`로 전달합니다.
확인이 필요한 후보는 새로 열어도 볼 수 있게 대기로 숨기지 않습니다. 저장 가사는 기본 조회에서 DB를 우선합니다.
프론트엔드는 미저장 가사를 자동 조회하며, 화면을 바꾸기 전 요청이 새 화면의 로딩 상태를 해제하지 않게 했습니다.

자동화 58개 통과(가사 병기·잘못된 재생시간·다른 버전·검색 확장·동기화 태그·DB 재조회 회귀 포함).
실제 임시 DB: 잔나비 곡 / 243초 / LRCLIB 13007700 / 한국어 36구절, MusicBrainz HTTP 없이 성공.
실제 연동 재검증: `python -m scripts.verify_lyrics`. 자동화의 모의 응답과 실제 검증은 구분합니다.
실행 중인 실제 브라우저에서도 기존 잔나비 곡 상세의 자동 조회와 36구절 표시를 확인했습니다.

평론 보완: 별칭 확인 후 앞서 받은 곡명·앨범명 결과를 다시 검사합니다. 곡명/앨범명 검색에서
맞는 리뷰를 받았어도 초기 영문 가수명과 다르다는 이유로 버리던 누락을 방지했습니다.
이 회귀 검사를 포함한 최신 자동화 결과는 59개 통과입니다.

## 복수 제공처와 선정 기사

일반 평론은 IZM을 먼저 조회합니다. 적합한 결과가 없거나 조회가 실패하면 HELLOKPOP의
`/wp-json/wp/v2/posts` 공개 검색 응답에서 연말 결산 Honorable Mentions의 명시된 항목을 대조합니다.
연말 기사 제목, 공개 필자 ID와 이름, Songs/Albums 구분, 항목의 가수와 제목을 모두 확인합니다.
단순 본문 언급·뉴스·공연 안내는 선정 자료로 연결하지 않습니다.

`backend/providers/review_matching.py`는 명확한 한글·영문 병기와 EP/Single 표기를 처리합니다.
곡의 확인된 다른 제목은 기존 대응표·캐시에서만 읽으며, 버전이나 동명이인을 임의로 합치지 않습니다.
서버의 기본 18초 예산 중 IZM은 최대 9초, 추가 제공처는 최대 8초를 사용합니다.
기존 결과 없음 캐시는 검색 개정 키로 분리해 새 조회를 막지 않습니다. 대기는 실제 남은 시간입니다.

`Review.article_type`은 review/selection, `ReviewLink.context`는 곡별 선정 정보입니다.
마이그레이션 a91f378c20e4가 기존 평론·연결을 보존합니다. 상세 API는 article_type과 해당 곡의 context를 반환합니다.
화면에서는 평론은 짧은 발췌로, 선정 자료는 연말 선정 기사/선정 정보로 구분하며 매체 이름은 숨깁니다.

실제 확인: 욕망주사기 / Redoor / Jung Bae / 2025 In Review: Day 3 – The Honorable Mentions /
Rock and Alternative → Songs. 단독 평론은 확보하지 못했으며 선정 기사로 연결합니다.
실제 임시 DB 검사: `python -m scripts.verify_editorial_sources`. 모의 응답 회귀 검사와 별개입니다.
자동화 73개 통과. 캐시를 읽은 직후 다른 클라이언트가 완료하는 경우에도 외부 요청을 반복하지 않도록 수정했습니다.

## 공개 자료 대기열과 직접 조회

기존 동기 API는 유지하며 REHome은 비동기 API를 사용합니다. 추가 의존 서비스는 없습니다.
`resource_jobs.py`가 SQLite 작업 파일과 스레드 2개를 사용합니다. 요청마다 새 스레드를 만들지 않습니다.
본문은 가사 조회의 `refresh`/`candidate_id` 또는 음악 검색의 `q`/`page`만 허용합니다.
상태 조회도 로그인이 필요하며 개인 코멘트·세션·계정 정보는 작업 파일에 넣지 않습니다.

제출 응답은 `202 {status:'pending',job_id,state,poll_after_ms}` 또는
`200 {status:'completed',result}`입니다. `GET /resource-jobs/<job_id>`도 같은 형식이며,
실패한 작업은 `{status:'failed',result:{error,code,retry_after}}`입니다.
정상 결과 내부의 available/missing/candidates/unavailable 상태는 기존 서비스와 같습니다.
클라이언트는 표시할 때 작업 결과의 retry_after를 사용하며, 저장 결과를 조회해도 대기 시간이 초기화되지 않습니다.

가사는 DB, 이전 가사 ID, 메타데이터 직접 조회, 제한된 검색 순서입니다.
원문 가사 버전과 구절 ID는 계속 불변이며 새 자료도 기존 코멘트를 다른 구절에 옮기지 않습니다.
평론은 계속 IZM 우선이며 선정 자료와 구분합니다.
검색의 저장된 결과는 바로 반환하고, 만료 결과에는 이전 자료 안내와 백그라운드 갱신을 적용합니다.
외부 검색 실패 시에도 오류를 알리고 별도 영역에 저장된 음악을 표시합니다.

표지 원래 URL은 Album.image에 유지됩니다. 확보한 파일이 있으면 API의 image는
`/api/media/artwork/<sha256>.img`입니다. 따라서 클라이언트는 검증된 이 상대 경로도 허용해야 합니다.
허용한 원본·이동 호스트, HTTPS, 이미지 헤더·형식, 파일 크기를 확인합니다.
공개 자료용 파일: `instance/resource-jobs.sqlite3`, `instance/provider-cache.sqlite3`, `instance/artwork/`.
실제 계정 DB와 분리하며 모두 Git 제외 대상입니다.

시연 준비: `python -m scripts.prepare_catalog --fetch --limit 10`.
이 명령은 계정에 곡이나 기록을 자동 배정하지 않습니다. `--fetch`가 없으면 확보 상태만 확인합니다.
실제 외부 검증: `python -m scripts.verify_resource_pipeline`.
자동화는 97개가 통과했으며 실제 가사·평론·표지 및 새 프로세스에서 HTTP 없는 재사용도 별도로 확인했습니다.
390×844 브라우저에서 실제 가사 조회·구절 아래 코멘트 저장·북마크·로컬 표지와 평론 표시를 확인했습니다.

한시 오분 (1:05) 후속 보완: 곡 ID e1437f5a-0ccc-449d-8b17-5ddfa0b146b7에 한해
검증된 제목 1:05와 가수 이름 The Black Skirts를 대응표에 추가했습니다.
대응표의 가수 이름도 곡·가수·앨범·재생시간을 대조한 뒤 사용합니다. 다른 곡이나 라이브에는 적용하지 않습니다.
가사 요청은 검증된 영문 가수 이름이 있으면 그 표기를 우선 사용하며 응답의 소유 가수·버전 검사는 유지합니다.
실제 TEAM BABY/240초/LRCLIB 5228940의 20구절을 확인했고 전체 자동화 103개가 통과했습니다.
