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


MONTHLY = 500         # 무료 요금제 한 달 사용량
DAILY_NEED = 12       # 하루 기본 수집에 필요한 양(종목 4개 × 3)
COST = 3              # 종목 하나 조회(승패·핸디·합계 × 1지역)


def _remaining() -> float | None:
    st = read_json(config.STATE / "odds_api_quota.json", {}) or {}
    try:
        return float(st["remaining"]) if st.get("remaining") is not None else None
    except (TypeError, ValueError):
        return None


def _days_left() -> int:
    import calendar
    now = config.now_kst()
    return calendar.monthrange(now.year, now.month)[1] - now.day + 1


def _credits_ok(reserve: int | None = None, refresh: bool = False) -> bool:
    """무료 한도 안에서만 쓴다.
    - 기본 수집: 남은 양이 한 번 조회할 만큼 있으면 허용
    - 새로고침(이미 받은 배당 다시 받기): 월말까지 매일 기본 수집에 쓸 몫을 남겨 둘 수 있을 때만"""
    rem = _remaining()
    if rem is None:
        return True
    if reserve is not None and not refresh:
        return rem >= reserve
    if refresh:
        return rem - COST >= _days_left() * DAILY_NEED
    return rem >= COST


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


def active_sports() -> set[str] | None:
    """지금 제공되는 종목 키 목록(무료 호출). 하루 한 번만 확인."""
    path = config.STATE / "odds_api_sports.json"
    st = read_json(path, {}) or {}
    if st.get("date") == config.today_kst() and st.get("keys"):
        return set(st["keys"])
    try:
        r = http("GET", f"{BASE}/sports", params={"apiKey": config.ODDS_API_KEY}, retries=2)
        rows = r.json()
        keys = sorted(x["key"] for x in rows if x.get("active"))
        write_json(path, {"date": config.today_kst(), "keys": keys, "titles": {x["key"]: x.get("title") for x in rows if x.get("active")}})
        return set(keys)
    except Exception as e:  # noqa: BLE001
        log.warning("Odds API 종목 목록 실패: %s", type(e).__name__)
        return set(st["keys"]) if st.get("keys") else None


def _fetch_sport(sport_key: str, day: str, refresh: bool) -> list[dict]:
    path = CACHE / f"{day}_{sport_key}_m3.json"
    cached = read_json(path)
    if cached is not None and (not refresh or not _credits_ok(refresh=True)):
        return cached  # 새로고침은 월말까지 쓸 몫이 남을 때만
    if not _credits_ok():
        log.warning("Odds API 크레딧 부족, 캐시 사용")
        return cached or []
    r = http("GET", f"{BASE}/sports/{sport_key}/odds", params={
        "apiKey": config.ODDS_API_KEY, "regions": "eu", "markets": "h2h,spreads,totals", "oddsFormat": "decimal"})
    _save_quota(r)
    data = r.json()
    write_json(path, data)
    return data


def _two_way(rows: list[tuple[float, float, float]]) -> list | None:
    """[(기준점, 왼쪽 배당, 오른쪽 배당)] → [가장 흔한 기준점, 왼쪽 공정확률]."""
    if not rows:
        return None
    from collections import Counter
    line = Counter(r[0] for r in rows).most_common(1)[0][0]
    sel = [r for r in rows if r[0] == line]
    a, b = median(r[1] for r in sel), median(r[2] for r in sel)
    pa, pb = 1 / a, 1 / b
    return [line, round(pa / (pa + pb), 4)]


def parse_event(event: dict) -> dict:
    """해외 배당 요약: 승패 공정확률·원 배당, 홈 핸디 기준점과 커버 확률, 합계 기준점과 오버 확률."""
    if "_x" in event:
        return event["_x"]
    home, away = event["home_team"], event["away_team"]
    books = event.get("bookmakers") or []
    pick = [b for b in books if b.get("key") in SHARP] or books
    spreads, totals = [], []
    for b in pick:
        for mk in b.get("markets", []):
            oc = {o["name"]: o for o in mk.get("outcomes", [])}
            try:
                if mk.get("key") == "spreads" and home in oc and away in oc:
                    spreads.append((float(oc[home]["point"]), float(oc[home]["price"]), float(oc[away]["price"])))
                elif mk.get("key") == "totals" and "Over" in oc and "Under" in oc:
                    totals.append((float(oc["Over"]["point"]), float(oc["Over"]["price"]), float(oc["Under"]["price"])))
            except (KeyError, TypeError, ValueError):
                continue
    x = {"h2h": _fair(event), "h2h_odds": event.get("_med"), "spread": _two_way(spreads), "total": _two_way(totals)}
    if x["h2h"]:
        x["h2h"] = {k: round(v, 4) for k, v in x["h2h"].items()}
    event["_x"] = x
    return x


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
    event["_med"] = {k: round(v, 2) for k, v in med.items()}
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
    """{market_id: 해외 배당 기준 확률} 과 상태 문자열. 핸디캡·언더오버는 베트맨 기준점으로 환산한다."""
    if not config.ODDS_API_KEY:
        return {}, "키 없음"
    from ..analysis.derive import from_overseas
    amap = alias_map()
    out: dict[str, dict] = {}
    sports = {odds_api_key_for(m["league"]) for m in markets} - {None}
    active = active_sports()
    errors, skipped = 0, 0
    for sk in sorted(sports):
        if active is not None and sk not in active:
            skipped += 1  # 지금 해외 시장에 없는 대회
            continue
        try:
            events = _fetch_sport(sk, day, refresh)
        except Exception as e:  # noqa: BLE001
            log.warning("Odds API %s 실패: %s", sk, e)
            errors += 1
            continue
        for m in markets:
            if odds_api_key_for(m["league"]) != sk:
                continue
            e = _match(m, events, amap)
            if not e:
                continue
            x = parse_event(e)
            m["x"] = {k: v for k, v in x.items() if v}
            p = from_overseas(m)
            if not p:
                continue
            out[m["id"]] = p
            m["ref_event"] = e["id"]
            if m["market"] in ("1X2", "WL"):
                m["ref_odds"] = x.get("h2h_odds")
            m["ref_kind"] = "직접" if m["market"] in ("1X2", "WL") else "환산"
    status = f"{len(out)}개 매칭" + (f", 제공 안 됨 {skipped}" if skipped else "") + (f", 오류 {errors}" if errors else "")
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
