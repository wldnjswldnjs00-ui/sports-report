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

# 애드센스: 승인 후 ca-pub-XXXXXXXX 값을 넣으면 광고 슬롯이 자동 활성화된다.
ADSENSE_CLIENT = os.getenv("ADSENSE_CLIENT", "").strip()
COUPANG_NOTICE = os.getenv("COUPANG_NOTICE", "") == "1"
SUPPORT_URL = os.getenv("SUPPORT_URL", "").strip()

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


def today_kst() -> str:
    return now_kst().strftime("%Y-%m-%d")
