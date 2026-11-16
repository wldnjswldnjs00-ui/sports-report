"""수집 데이터의 표준 형식과 검증.

모든 소스(베트맨, 수동 입력, 샘플)는 아래 형식의 '마켓' dict 목록을 돌려준다.

{
  "id": "고유 문자열",
  "source": "betman" | "manual" | "sample",
  "pool": "proto" | "toto",
  "round": "회차 문자열" | None,
  "game_no": int | None,
  "sport": "soccer" | "basketball" | "baseball" | "volleyball" | "hockey" | "football" | "etc",
  "league": "리그명",
  "kickoff": "ISO8601 (+09:00)",
  "home": "홈팀", "away": "원정팀",
  "market": "1X2" | "WL" | "HANDICAP" | "OU",
  "line": float | None,
  "odds": {"H": 1.85, "D": 3.4, "A": 3.9}   # 결과 키별 배당. toto 는 비어 있을 수 있음
}
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

OUTCOMES = {
    "1X2": ("H", "D", "A"),
    "WL": ("H", "A"),
    "HANDICAP": ("H", "D", "A"),
    "OU": ("O", "U"),
}
SPORTS = {"soccer", "basketball", "baseball", "volleyball", "hockey", "football", "etc"}

OUTCOME_LABEL = {"H": "승", "D": "무", "A": "패", "O": "오버", "U": "언더"}
MARKET_LABEL = {"1X2": "승무패", "WL": "승패", "HANDICAP": "핸디캡", "OU": "언더오버"}
SPORT_LABEL = {
    "soccer": "축구", "basketball": "농구", "baseball": "야구", "volleyball": "배구",
    "hockey": "하키", "football": "미식축구", "etc": "기타",
}


class InvalidMarket(ValueError):
    pass


def validate(m: dict[str, Any]) -> dict[str, Any]:
    """검증 + 정리. 문제가 있으면 InvalidMarket. 조용히 이상한 데이터를 쓰지 않는다."""
    for k in ("id", "league", "home", "away", "market", "kickoff"):
        if not m.get(k):
            raise InvalidMarket(f"필수 필드 누락: {k} ({m.get('id')})")
    market = m["market"]
    if market not in OUTCOMES:
        raise InvalidMarket(f"알 수 없는 마켓 {market}")
    if m["home"].strip() == m["away"].strip():
        raise InvalidMarket(f"홈/원정이 같음: {m['home']}")
    try:
        datetime.fromisoformat(m["kickoff"])
    except ValueError as e:
        raise InvalidMarket(f"킥오프 시간 형식 오류 {m['kickoff']}") from e

    sport = m.get("sport") or "etc"
    m["sport"] = sport if sport in SPORTS else "etc"
    m.setdefault("pool", "proto")
    m.setdefault("round", None)
    m.setdefault("game_no", None)
    m.setdefault("line", None)
    m.setdefault("source", "manual")

    odds_in = m.get("odds") or {}
    odds: dict[str, float] = {}
    for key in OUTCOMES[market]:
        v = odds_in.get(key)
        if v in (None, "", 0):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError) as e:
            raise InvalidMarket(f"배당 숫자 아님 {key}={v}") from e
        # 1.0 이하 배당, 비현실적 배당은 오타로 본다.
        if not (1.01 <= f <= 500):
            raise InvalidMarket(f"비정상 배당 {key}={f} ({m['id']})")
        odds[key] = round(f, 2)
    if m["pool"] == "proto":
        required = {"H", "A"} if market == "HANDICAP" else set(OUTCOMES[market])  # 핸디캡은 2지·3지 모두 있음
        if not required <= set(odds):
            raise InvalidMarket(f"배당 일부 누락 ({m['id']}): {odds}")
        overround = sum(1 / o for o in odds.values())
        # 베트맨 환급률은 대략 60~95% 범위. 범위를 벗어나면 파싱 오류일 가능성.
        if not (1.0 <= overround <= 1.8):
            raise InvalidMarket(f"배당 합이 비정상 (overround={overround:.3f}, {m['id']})")
    m["odds"] = odds
    m["home"] = m["home"].strip()
    m["away"] = m["away"].strip()
    m["league"] = m["league"].strip()
    return m


def validate_all(markets: list[dict[str, Any]], log) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for m in markets:
        try:
            v = validate(dict(m))
        except InvalidMarket as e:
            log.warning("마켓 제외: %s", e)
            continue
        if v["id"] in seen:
            continue
        seen.add(v["id"])
        out.append(v)
    return out
