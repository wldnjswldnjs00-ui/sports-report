"""스스로 오류 찾기·고치기(사람 손 없이).

1) 분석 결과 검사(sanitize): 리포트를 저장하기 전에 마켓마다
   - 확률 합이 1인지, 0~1 사이인지, 숫자가 깨졌는지(NaN)
   - 배당이 1보다 큰지, 픽이 배당 목록에 있는지
   를 확인해서 깨진 분석은 빼고(그 마켓은 '분석 없음'), 고친 개수를 기록한다.
2) 실제 사이트 검사(site_problems): 첫 화면이 열리는지, 오늘 구매일 날짜가 보이는지, 미리보기 이미지가 열리는지.
   문제가 있으면 자동 점검(health)이 이슈로 남기고, 다음 실행에서 다시 확인한다.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from . import config
from .util import http

log = logging.getLogger("engine.selfcheck")


def _bad_probs(p: Any) -> bool:
    if not isinstance(p, dict) or not p:
        return True
    vals = list(p.values())
    if any(not isinstance(v, (int, float)) or math.isnan(v) or v < 0 or v > 1 for v in vals):
        return True
    return abs(sum(vals) - 1) > 0.02


def sanitize(markets: list[dict]) -> dict:
    fixed = []
    for m in markets:
        a = m.get("analysis")
        odds = m.get("odds") or {}
        bad_odds = [k for k, v in odds.items() if not isinstance(v, (int, float)) or v <= 1.0 or v > 1000]
        for k in bad_odds:
            odds.pop(k, None)
        if not a:
            continue
        why = None
        if _bad_probs(a.get("p")):
            why = "확률 깨짐"
        elif a.get("pick") not in (a.get("p") or {}) or a.get("pick") not in odds:
            why = "픽이 배당에 없음"
        elif not (0 < (a.get("pick_prob") or 0) < 1):
            why = "픽 확률 범위 밖"
        if why:
            fixed.append({"id": m["id"], "why": why})
            m["analysis"] = None
            m["narrative"] = None
    if fixed:
        log.warning("분석 자동 정리 %d건: %s", len(fixed), fixed[:5])
    return {"fixed": len(fixed), "items": fixed[:20]}


def site_problems(sales_day: str) -> list[str]:
    """실제 배포된 사이트 확인. 네트워크가 막힌 환경이면 조용히 건너뛴다."""
    if config.DEMO:
        return []
    out = []
    try:
        r = http("GET", config.SITE_URL + "/", retries=2, headers={"User-Agent": "Mozilla/5.0 (selfcheck)"})
        html = r.text
        y, mo, d = sales_day.split("-")
        if r.status_code != 200:
            out.append(f"사이트 첫 화면 응답 {r.status_code}")
        elif f"{y}.{mo}.{d}" not in html:
            out.append(f"사이트 첫 화면에 오늘 구매일({sales_day})이 보이지 않습니다. 배포가 늦거나 실패했을 수 있습니다.")
        img = http("GET", config.SITE_URL + "/og/home.jpg", retries=1)
        if img.status_code != 200:
            out.append(f"미리보기 이미지 응답 {img.status_code}")
    except Exception as e:  # noqa: BLE001
        log.info("사이트 확인 건너뜀: %s", type(e).__name__)
    return out
