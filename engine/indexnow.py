"""IndexNow: 새로 생기거나 바뀐 페이지를 네이버·빙에 즉시 알린다(구글은 사이트맵으로 수집).

오늘·어제 리포트와 그 경기 페이지, 홈, 보관함만 보낸다. 실패해도 파이프라인은 계속된다.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from urllib.parse import quote, urlparse

from . import config
from .util import http, read_json

log = logging.getLogger("engine.indexnow")
ENDPOINTS = ("https://searchadvisor.naver.com/indexnow", "https://api.indexnow.org/indexnow")


FIXED = ("/", "/reports/", "/performance/", "/analysis/", "/knowhow/", "/leagues/", "/rounds/", "/facts/", "/stories/today/")


def recent_urls() -> list[str]:
    """빅매치 → 고정 페이지 → 어제·오늘·내일(19시에 공개되는 다음 구매일) 페이지 순."""
    urls = read_json(config.DIST / "data" / "urls.json", []) or []
    hot = read_json(config.DIST / "data" / "hot.json", []) or []
    today = config.now_kst()
    days = {(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in (-1, 0, 1)}
    pick = list(dict.fromkeys([u for u in hot if u in urls] + [u for u in FIXED if u in urls]
                              + [u for u in urls if any(d in u for d in days)]))
    return [config.SITE_URL + quote(u) for u in pick][:500]


def ping() -> int:
    if not config.INDEXNOW_KEY:
        return 0
    urls = recent_urls()
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
    return ok
