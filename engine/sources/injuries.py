"""NBA 부상자 현황(ESPN 공개 피드). 실패해도 분석은 계속된다.

베트맨 한글 팀명 → 영문 팀명(aliases) → ESPN 팀명으로 매칭한다.
"""
from __future__ import annotations

import logging
from typing import Any

from ..util import http, norm_team
from .aliases import alias_map, english

log = logging.getLogger("engine.injuries")
URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
STATUS_KO = {"Out": "결장", "Doubtful": "결장 유력", "Questionable": "출전 불투명", "Day-To-Day": "출전 미정", "Probable": "출전 유력"}


def fetch_nba() -> dict[str, list[dict[str, Any]]]:
    try:
        data = http("GET", URL, retries=2).json()
    except Exception as e:  # noqa: BLE001
        log.warning("NBA 부상자 조회 실패: %s", e)
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for t in data.get("injuries") or []:
        name = t.get("displayName") or ""
        rows = []
        for i in t.get("injuries") or []:
            ath = i.get("athlete") or {}
            st = i.get("status") or ""
            if st not in STATUS_KO:
                continue
            rows.append({"name": ath.get("displayName") or "", "pos": ((ath.get("position") or {}).get("abbreviation") or ""),
                         "status": STATUS_KO[st], "out": st in ("Out", "Doubtful"),
                         "note": (i.get("shortComment") or "")[:160]})
        if rows:
            out[norm_team(name)] = rows
    return out


def attach(markets: list[dict]) -> int:
    nba = [m for m in markets if m.get("league") == "NBA"]
    if not nba:
        return 0
    table = fetch_nba()
    if not table:
        return 0
    amap = alias_map()
    n = 0
    for m in nba:
        h = table.get(norm_team(english(m["home"], amap)))
        a = table.get(norm_team(english(m["away"], amap)))
        if h or a:
            m["injuries"] = {"home": h or [], "away": a or []}
            n += 1
    return n
