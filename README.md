# 스포츠분석.kr

베트맨 공식 발매 경기를 매일 자동으로 분석해서 정적 사이트로 발행합니다.

- **계산**: GitHub Actions에서 하루 5번 실행 (수집 → 분석 → 채점 → 데이터 커밋)
- **호스팅**: Cloudflare Pages (무료, 서버 없음, 상업적 이용 가능)
- **비용**: 도메인 제외 0원
- Vercel이나 다른 프로젝트와 공유하는 것이 없습니다.

## 하루 흐름 (KST)

| 시각 | 하는 일 |
|---|---|
| 06:00 | 새 날짜 리포트 생성, 전날 경기 결과 채점, Elo·보정값 재계산 |
| 09:30, 13:00 | 발매 경기 재수집 (새로 열린 경기 반영) |
| 18:00 | 해외 배당 새로고침, 배당 변동 기록 |
| 22:30 | 심야 해외 경기 직전 재수집 |

킥오프가 지난 경기의 픽과 그 경기가 들어간 조합은 **절대 바뀌지 않습니다.**

## 처음 설정

### 1. Cloudflare Pages 연결
1. https://dash.cloudflare.com → Workers & Pages → Create → Pages → **Connect to Git**
2. `sports-report` 저장소 선택
3. 빌드 설정
   - Framework preset: `None`
   - Build command: `pip install -r requirements.txt && python -m engine build`
   - Build output directory: `dist`
   - Environment variables: `PYTHON_VERSION` = `3.12`
4. Save and Deploy
5. 배포가 끝나면 Custom domains → `스포츠분석.kr` 추가 (네임서버를 Cloudflare로 옮겨 둔 상태여야 합니다)

### 2. API 키 넣기 (선택, 무료)
GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret

| 이름 | 발급처 | 용도 |
|---|---|---|
| `ODDS_API_KEY` | https://the-odds-api.com (무료 월 500회) | 해외 배당 비교, 경기 결과 |
| `FOOTBALL_DATA_KEY` | https://www.football-data.org (무료) | 예비 |

키가 없어도 사이트는 돌아갑니다. 그 경우 베트맨 배당과 Elo만으로 분석합니다.

### 3. 애드센스 (승인 후)
Cloudflare Pages → 프로젝트 → Settings → Environment variables에 추가하고 다시 배포합니다.
- `ADSENSE_CLIENT` = `ca-pub-XXXXXXXXXXXXXXXX`

값을 넣으면 광고 스크립트, 광고 슬롯, `ads.txt`가 자동으로 생성됩니다. 값이 없으면 빈 광고 자리도 보이지 않습니다.

그 밖의 설정: `CONTACT_EMAIL`(문의 페이지), `COUPANG_NOTICE=1`(쿠팡 파트너스 고지).

### 4. 검색엔진 등록
- 구글 서치 콘솔: 속성 추가 → URL 접두어 `https://스포츠분석.kr` → HTML 태그 방식의 content 값을 Cloudflare 변수 `GOOGLE_SITE_VERIFICATION`에 넣고 재배포 → 확인 → Sitemaps에 `sitemap.xml` 제출
- 네이버 서치어드바이저: 사이트 등록 → HTML 태그 방식의 content 값을 `NAVER_SITE_VERIFICATION`에 넣고 재배포 → 확인 → 요청 → 사이트맵 제출(`sitemap.xml`), RSS 제출(`rss.xml`)
- IndexNow(네이버·빙 즉시 색인)는 자동 실행마다 새 페이지를 알아서 보냅니다. 키 파일은 사이트 루트에 자동 생성됩니다.

## 베트맨 수집이 막힐 때

베트맨은 공식 API가 없고, 해외 IP를 차단할 수 있습니다. 막히면 사이트가 멈추는 대신 아래 방법으로 이어갑니다.

**수동 입력**: `data/manual/2026-11-16.csv` 파일을 GitHub 웹에서 올리면, 그 즉시 분석과 발행이 자동으로 돌아갑니다. 형식은 `data/manual/_예시.csv`를 보세요.

```
pool,game_no,sport,league,kickoff,home,away,market,line,H,D,A
proto,1,soccer,EPL,2026-11-16 21:00,맨체스C,리버풀,1X2,,1.85,3.40,3.60
```
- `market`: `1X2`(승무패) `WL`(승패) `HANDICAP`(핸디캡, line 필수) `OU`(언더오버, H=오버 A=언더)
- 결과는 `data/results/manual/날짜.csv`로 넣습니다: `game_no,home,away,home_score,away_score,status`

**국내 서버**: 오라클 클라우드 무료 VM(서울/춘천 리전)에서 아래 명령을 크론으로 돌리고 push하면 국내 IP로 수집됩니다.

```bash
python -m engine run && git add data && git commit -m data && git push
```

## 팀 이름 매칭

해외 배당과 맞추려면 베트맨 한글 팀명이 영문명과 연결돼야 합니다. 주요 리그는 `engine/sources/aliases.py`에 들어 있고, 빠진 팀은 `data/aliases.json`에 추가합니다.

```json
{ "울산HD": "Ulsan HD", "전북": "Jeonbuk Motors" }
```

## 로컬에서 미리보기

```bash
pip install -r requirements.txt
DEMO=1 DATA_DIR=.demo python -m engine demo
DEMO=1 DATA_DIR=.demo python -m engine build
python -m http.server -d dist 8000
```

데모 데이터는 가상 팀 이름을 쓰고, 화면 상단에 "샘플 데이터" 띠가 붙습니다. 운영 데이터 폴더(`data/`)에는 섞이지 않습니다.

## 테스트

```bash
python -m unittest -q
```

## 구조

```
engine/
  sources/    베트맨 수집, 수동 입력, 해외 배당, 데모 데이터
  analysis/   마진 제거·확률 결합, Elo, 조합 최적화, 분석문, 채점
  site/       정적 사이트 생성기, 템플릿, CSS/JS, 3D 무대
data/
  reports/    날짜별 리포트 (발행 후 픽 고정)
  results/    경기 결과
  manual/     수동 입력
  state/      Elo, 보정값, 성과 집계, 배당 캐시
```
