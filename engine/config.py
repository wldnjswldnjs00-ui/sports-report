"""전역 설정. 모든 값은 환경변수로 덮어쓸 수 있다."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("DATA_DIR") or (ROOT / "data")).resolve()
REPORTS = DATA / "reports"
RESULTS = DATA / "results"
MANUAL = DATA / "manual"
STATE = DATA / "state"
DIST = Path(os.getenv("DIST_DIR") or (ROOT / "dist")).resolve()

KST = timezone(timedelta(hours=9))

MODEL_VERSION = "aurora-1.0.0"

SITE_NAME = os.getenv("SITE_NAME", "스포츠분석")
SITE_URL = os.getenv("SITE_URL", "https://xn--sr3bw9dq7a9xy85g.kr").rstrip("/")
SITE_DOMAIN_DISPLAY = "스포츠분석.kr"
SITE_DESC = "베트맨 공식 발매 경기를 데이터로 분석하는 매일 스포츠 리포트"
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")
THREADS_URL = os.getenv("THREADS_URL", "https://www.threads.net/@sports_report.kr")

# 애드센스: 승인 후 ca-pub-XXXXXXXX 값을 넣으면 광고 슬롯이 자동 활성화된다.
# 애드센스 게시자 ID. 페이지 소스에 공개되는 값이라 비밀이 아니다(환경 변수로 바꿀 수 있음)
ADSENSE_CLIENT = os.getenv("ADSENSE_CLIENT", "ca-pub-6870676006996989").strip()
# 애드센스 디스플레이 광고 단위 ID(숫자). 없으면 페이지 안 광고 칸은 만들지 않고 자동 광고만 쓴다.
ADSENSE_SLOT = "".join(ch for ch in os.getenv("ADSENSE_SLOT", "") if ch.isdigit())
# 쿠팡 파트너스 다이나믹 배너(캐러셀 680×140): 배너 코드의 id 숫자와 trackingCode(AF...).
# 페이지 소스에 공개되는 값이라 비밀이 아니다. 환경 변수로 바꿀 수 있고, 빈 값을 넣으면 끈다.
# 텐핑 소문박스(공개 설치 코드의 값, 비밀 아님). 캠페인은 텐핑이 알아서 바꿔 보여준다
TENPING_CLIENT = os.getenv("TENPING_CLIENT", "39fmzsudfQ7bCsjS4P2pqUhoXTpTjMTQeifD3sGCZfXr5AmYqmvS8HHuezQ1sEpj").strip()
TENPING_TYPE = os.getenv("TENPING_TYPE", "1LawCE8FqKOhetXZhMopsQ%3d%3d").strip()
COUPANG_BANNER_ID = "".join(ch for ch in os.getenv("COUPANG_BANNER_ID", "1051068") if ch.isdigit())
COUPANG_TRACKING = "".join(ch for ch in os.getenv("COUPANG_TRACKING", "AF4576944").strip() if ch.isalnum())
COUPANG_TEMPLATE = os.getenv("COUPANG_TEMPLATE", "carousel").strip() or "carousel"
# 배너를 걸면 수수료 고지 문구는 자동으로 켠다(쿠팡 파트너스 의무 사항)
COUPANG_NOTICE = os.getenv("COUPANG_NOTICE", "") == "1" or bool(COUPANG_BANNER_ID and COUPANG_TRACKING)
SUPPORT_URL = os.getenv("SUPPORT_URL", "").strip()
# 후원: 카카오페이 송금 링크(https://qr.kakaopay.com/...), 토스 익명 송금 링크(https://toss.me/...)
SUPPORT_KAKAOPAY = os.getenv("SUPPORT_KAKAOPAY", "https://qr.kakaopay.com/Fc3KExJ1t").strip()
SUPPORT_TOSS = os.getenv("SUPPORT_TOSS", "").strip()
SLOGAN = "데이터와 수학으로, 분석을 똑똑하게"

# 검색엔진 소유 확인(서치 콘솔 / 네이버 서치어드바이저에서 받은 content 값)
GOOGLE_SITE_VERIFICATION = os.getenv("GOOGLE_SITE_VERIFICATION", "iXRqVBnVwoPNywIn7DYmi6t38IMQlf6xogGn4SVxiuw").strip()
NAVER_SITE_VERIFICATION = os.getenv("NAVER_SITE_VERIFICATION", "1ec76f6e2a7122fd85ae127eba6caca4a16db213").strip()
# IndexNow 키: 공개되어도 되는 값(사이트 루트의 /<키>.txt 로 소유를 증명). 네이버·빙에 새 페이지를 즉시 알린다.
# 이 확률 이상일 때만 '픽'으로 낸다(그 아래는 '박빙': 분석만 보여 주고 픽·적중률 집계에서 뺀다)
PICK_MIN = float(os.getenv("PICK_MIN", "0.55"))
INDEXNOW_KEY = os.getenv("INDEXNOW_KEY", "4dbd24d706c1c5983c3c93c5a0a18f2b").strip()

# 데모 모드: 실데이터가 없을 때 로컬 미리보기용 샘플을 만든다. 운영에서는 끈다.
DEMO = os.getenv("DEMO", "0") == "1"

# 외부 API 키 (없으면 해당 소스는 조용히 건너뛴다)
FOOTBALL_DATA_KEY = os.getenv("FOOTBALL_DATA_KEY", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
API_SPORTS_KEY = os.getenv("API_SPORTS_KEY", "").strip()

USER_AGENT = "Mozilla/5.0 (compatible; sports-report/1.0; +%s)" % SITE_URL
HTTP_TIMEOUT = 20


def now_kst() -> datetime:
    return datetime.now(KST)


# 프로토 구매 시간(08:00~23:00) 기준 '구매일'.
# - 밤 23시가 되면 다음 구매일로 넘어간다(그 뒤로는 오늘 경기를 살 수 없다).
# - 킥오프가 아침 8시 30분 전인 경기(유럽 새벽 경기 등)는 전날 밤 23시 전에 사야 하므로 전날 구매일에 속한다.
SALES_ROLL_HOUR = 23
DAY_START = timedelta(hours=8, minutes=30)


def today_kst() -> str:
    """지금의 구매일(YYYY-MM-DD). 23:00 부터는 다음 날."""
    return (now_kst() + timedelta(hours=24 - SALES_ROLL_HOUR)).strftime("%Y-%m-%d")


def sales_day(kickoff_iso: str) -> str:
    """경기가 속하는 구매일. 08:30 전 킥오프는 전날."""
    t = datetime.fromisoformat(kickoff_iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=KST)
    return (t.astimezone(KST) - DAY_START).strftime("%Y-%m-%d")
