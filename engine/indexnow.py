"""IndexNow: 새로 생기거나 바뀐 페이지를 네이버·빙에 즉시 알린다(구글은 사이트맵으로 수집).

오늘·어제 리포트와 그 경기 페이지, 홈, 보관함만 보낸다. 실패해도 파이프라인은 계속된다.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from urllib.parse import quote, urlparse

from . import config
from .util import http, read_json, write_json

log = logging.getLogger("engine.indexnow")
ENDPOINTS = ("https://searchadvisor.naver.com/indexnow", "https://api.indexnow.org/indexnow")


FIXED = ("/", "/schedule/", "/schedule/soccer/", "/schedule/nba/", "/schedule/kbl/", "/schedule/volleyball/", "/schedule/kleague/", "/reports/", "/performance/", "/analysis/", "/knowhow/", "/leagues/", "/rounds/", "/facts/", "/stories/today/", "/vs/", "/용어/")


def recent_urls() -> list[str]:
    """빅매치 → 고정 페이지 → 어제·오늘·내일(19시에 공개되는 다음 구매일) 페이지 순."""
    urls = read_json(config.DIST / "data" / "urls.json", []) or []
    hot = read_json(config.DIST / "data" / "hot.json", []) or []
    today = config.now_kst()
    days = {(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in (-1, 0, 1)}
    # 가장 새 회차 두 개(발매 직후 '프로토 ○○회차' 검색에 먼저 잡히게)
    rounds = sorted({u for u in urls if re.fullmatch(r"/rounds/\d{6}/", u)}, reverse=True)[:2]
    pick = list(dict.fromkeys(rounds + [u for u in hot if u in urls] + [u for u in FIXED if u in urls]
                              + [u for u in urls if any(d in u for d in days)]))
    return [config.SITE_URL + quote(u) for u in pick][:500]


def all_urls() -> list[str]:
    """사이트맵에 들어간 모든 주소(빅매치·고정 페이지 먼저)."""
    urls = read_json(config.DIST / "data" / "urls.json", []) or []
    head = recent_urls()
    return list(dict.fromkeys(head + [config.SITE_URL + quote(u) for u in urls]))[:10000]


def ping(full: bool | None = None) -> int:
    """평소엔 새 페이지만, 7일에 한 번은 전체 주소를 보낸다(네이버·빙이 사이트 전체를 빨리 다시 읽게)."""
    if not config.INDEXNOW_KEY:
        return 0
    stf = config.STATE / "indexnow.json"
    st = read_json(stf, {}) or {}
    today = config.now_kst().date()
    if full is None:
        last = st.get("full")
        full = not last or (today - date.fromisoformat(last)).days >= 7
    urls = all_urls() if full else recent_urls()
    if not urls:
        return 0
    host = urlparse(config.SITE_URL).hostname
    body = {"host": host, "key": config.INDEXNOW_KEY, "keyLocation": f"{config.SITE_URL}/{config.INDEXNOW_KEY}.txt", "urlList": urls}
    ok = 0
    for ep in ENDPOINTS:
        try:
            r = http("POST", ep, json=body, headers={"Content-Type": "application/json; charset=utf-8"}, retries=2)
            log.info("IndexNow %s → %s (%d개)", ep, r.status_code, len(urls))
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.warning("IndexNow %s 실패: %s", ep, e)
    if full and ok:
        st["full"] = today.isoformat()
        write_json(stf, st)
    return ok
