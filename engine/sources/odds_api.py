"""The Odds API: 해외 배당(기준 확률)과 경기 결과.

무료 플랜은 월 500 크레딧. 크레딧을 아끼기 위해
- 그날 베트맨 경기에 실제로 등장한 리그만 호출한다.
- 같은 날 같은 종목은 캐시(data/state/odds_cache/)를 재사용한다(하루 최대 2회 갱신).
- 남은 크레딧이 60 미만이면 호출을 멈춘다.
"""
from __future__ import annotations

import difflib
import logging
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from .. import config
from ..util import http, norm_team, read_json, write_json
from .aliases import alias_map, english, odds_api_key_for

log = logging.getLogger("engine.odds_api")
BASE = "https://api.the-odds-api.com/v4"
CACHE = config.STATE / "odds_cache"
SHARP = ("pinnacle", "betfair_ex_eu", "matchbook")


def _credits_ok(reserve: int = 60) -> bool:
    st = read_json(config.STATE / "odds_api_quota.json", {}) or {}
    rem = st.get("remaining")
    try:
        return rem is None or float(rem) >= reserve
    except (TypeError, ValueError):
        return True


def prune_cache(keep_days: int = 3) -> None:
    """오래된 배당 캐시 삭제(저장소 비대화 방지)."""
    if not CACHE.exists():
        return
    cutoff = (config.now_kst() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    for p in CACHE.glob("*.json"):
        if p.name[:10] < cutoff:
            p.unlink()


def _save_quota(r) -> None:
    rem = r.headers.get("x-requests-remaining")
    if rem is not None:
        write_json(config.STATE / "odds_api_quota.json", {"remaining": rem, "used": r.headers.get("x-requests-used"),
                                                          "at": config.now_kst().isoformat(timespec="seconds")})


def _fetch_sport(sport_key: str, day: str, refresh: bool) -> list[dict]:
    path = CACHE / f"{day}_{sport_key}.json"
    cached = read_json(path)
    if cached is not None and (not refresh or not _credits_ok(200)):
        return cached  # 갱신은 크레딧 여유가 있을 때만
    if not _credits_ok():
        log.warning("Odds API 크레딧 부족, 캐시 사용")
        return cached or []
    r = http("GET", f"{BASE}/sports/{sport_key}/odds", params={
        "apiKey": config.ODDS_API_KEY, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"})
    _save_quota(r)
    data = r.json()
    write_json(path, data)
    return data


def _fair(event: dict) -> dict[str, float] | None:
    """샤프 북메이커 우선, 없으면 전체 중앙값. 비례 방식으로 마진 제거."""
    home, away = event["home_team"], event["away_team"]
    books = event.get("bookmakers") or []
    pick = [b for b in books if b.get("key") in SHARP] or books
    rows = []
    for b in pick:
        for mk in b.get("markets", []):
            if mk.get("key") != "h2h":
                continue
            o = {}
            for oc in mk.get("outcomes", []):
                if oc["name"] == home:
                    o["H"] = oc["price"]
                elif oc["name"] == away:
                    o["A"] = oc["price"]
                elif oc["name"].lower() == "draw":
                    o["D"] = oc["price"]
            if "H" in o and "A" in o:
                rows.append(o)
    if not rows:
        return None
    keys = set(rows[0])
    for r in rows:
        keys &= set(r)
    med = {k: median(r[k] for r in rows) for k in keys}
    s = sum(1 / v for v in med.values())
    return {k: (1 / v) / s for k, v in med.items()}


def _match(m: dict, events: list[dict], amap: dict[str, str]) -> dict | None:
    h, a = norm_team(english(m["home"], amap)), norm_team(english(m["away"], amap))
    ko = datetime.fromisoformat(m["kickoff"])
    best, score = None, 0.0
    for e in events:
        t = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
        if abs(t - ko) > timedelta(hours=14):
            continue
        sh = difflib.SequenceMatcher(None, h, norm_team(e["home_team"])).ratio()
        sa = difflib.SequenceMatcher(None, a, norm_team(e["away_team"])).ratio()
        s = min(sh, sa)
        if s > score:
            best, score = e, s
    return best if score >= 0.82 else None


def reference(markets: list[dict[str, Any]], day: str, refresh: bool = False) -> tuple[dict[str, dict], str]:
    """{market_id: 공정확률} 과 상태 문자열."""
    if not config.ODDS_API_KEY:
        return {}, "키 없음"
    amap = alias_map()
    out: dict[str, dict] = {}
    sports = {odds_api_key_for(m["league"]) for m in markets if m["market"] in ("1X2", "WL")} - {None}
    errors = 0
    for sk in sorted(sports):
        try:
            events = _fetch_sport(sk, day, refresh)
        except Exception as e:  # noqa: BLE001
            log.warning("Odds API %s 실패: %s", sk, e)
            errors += 1
            continue
        for m in markets:
            if odds_api_key_for(m["league"]) != sk or m["market"] not in ("1X2", "WL"):
                continue
            e = _match(m, events, amap)
            if not e:
                continue
            fair = _fair(e)
            if not fair:
                continue
            if m["market"] == "WL" and "D" in fair:
                # 승패 마켓(연장 포함)에는 무승부를 비례 배분
                d = fair.pop("D")
                t = fair["H"] + fair["A"]
                fair = {"H": fair["H"] + d * fair["H"] / t, "A": fair["A"] + d * fair["A"] / t}
            if set(fair) == set(m["odds"]):
                out[m["id"]] = fair
                m["ref_event"] = e["id"]
    status = f"{len(out)}개 매칭" + (f", 오류 {errors}" if errors else "")
    return out, status


def scores(sport_keys: set[str]) -> list[dict]:
    """최근 3일 결과. 종목당 2 크레딧."""
    if not config.ODDS_API_KEY or not _credits_ok():
        return []
    res = []
    for sk in sorted(sport_keys):
        try:
            r = http("GET", f"{BASE}/sports/{sk}/scores", params={"apiKey": config.ODDS_API_KEY, "daysFrom": 3})
            _save_quota(r)
            res.extend(r.json())
        except Exception as e:  # noqa: BLE001
            log.warning("Odds API 결과 %s 실패: %s", sk, e)
    return res


def result_for(m: dict, events: list[dict], amap: dict[str, str]) -> dict | None:
    e = None
    if m.get("ref_event"):
        e = next((x for x in events if x.get("id") == m["ref_event"]), None)
    if e is None:
        e = _match(m, events, amap)
    if not e or not e.get("completed") or not e.get("scores"):
        return None
    sc = {s["name"]: s["score"] for s in e["scores"]}
    try:
        return {"home_score": float(sc[e["home_team"]]), "away_score": float(sc[e["away_team"]]), "status": "FT", "src": "odds_api"}
    except (KeyError, TypeError, ValueError):
        return None
