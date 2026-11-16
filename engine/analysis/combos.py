"""전략별 조합 생성.

원칙
- 한 조합에 같은 경기는 한 번만 (경기 키 기준, 마켓이 달라도 중복 금지).
- 같은 리그·같은 날 경기끼리는 상관관계를 보수적으로 반영해 결합 확률을 깎는다.
- 기대값(EV)이 마이너스인 조합은 숨기지 않고 표시한다. 대신 판정을 분명히 한다.
- 비슷한 조합만 반복되지 않게 겹침을 제한한다.
"""
from __future__ import annotations

import itertools
import math
from typing import Any

STAKE = 10_000  # 예시 금액(원)

STRATEGIES = {
    "safe": {
        "label": "안정형", "sizes": (2, 3), "min_leg_p": 0.66, "min_conf": 50,
        "odds_range": (1.2, 3.5), "min_joint": 0.40, "top": 4, "pool": 14,
        "desc": "확률이 높은 경기만 2~3개 묶습니다. 배당은 낮고 적중 가능성이 우선입니다.",
    },
    "balanced": {
        "label": "밸런스형", "sizes": (2, 3, 4), "min_leg_p": 0.50, "min_conf": 40,
        "odds_range": (2.5, 8.0), "min_joint": 0.15, "top": 6, "pool": 18,
        "desc": "적중 가능성과 배당을 함께 봅니다. 기대값이 덜 나쁜 조합을 위로 올립니다.",
    },
    "aggressive": {
        "label": "공격형", "sizes": (3, 4, 5), "min_leg_p": 0.38, "min_conf": 30,
        "odds_range": (7.0, 80.0), "min_joint": 0.03, "top": 6, "pool": 18,
        "desc": "배당을 크게 노립니다. 맞을 확률은 낮습니다. 소액 전용입니다.",
    },
}

CORR_PENALTY = 0.985  # 같은 리그·같은 날 한 쌍당 결합확률 감쇠


def match_key(m: dict[str, Any]) -> str:
    return f"{m['kickoff'][:10]}|{m['home']}|{m['away']}"


def legs_from(markets: list[dict[str, Any]], use_value: bool = False) -> list[dict[str, Any]]:
    legs = []
    for m in markets:
        a = m.get("analysis")
        if not a or m.get("pool") != "proto" or not m.get("odds"):
            continue
        key = a["value_key"] if use_value else a["pick"]
        if key is None or key not in m["odds"]:
            continue
        p = a["p"][key]
        o = m["odds"][key]
        legs.append({
            "market_id": m["id"], "match": match_key(m), "league": m["league"], "sport": m["sport"],
            "date": m["kickoff"][:10], "home": m["home"], "away": m["away"], "market": m["market"],
            "line": m.get("line"), "game_no": m.get("game_no"), "kickoff": m["kickoff"],
            "outcome": key, "p": p, "odds": o, "ev": p * o - 1, "confidence": a["confidence"],
            "upset_risk": a["upset_risk"],
        })
    return legs


def joint_prob(legs: list[dict[str, Any]]) -> float:
    p = math.prod(l["p"] for l in legs)
    pairs = sum(1 for a, b in itertools.combinations(legs, 2) if a["league"] == b["league"] and a["date"] == b["date"])
    return p * (CORR_PENALTY ** pairs)


def total_odds(legs: list[dict[str, Any]]) -> float:
    # 베트맨은 종합배당을 소수 둘째 자리에서 절사한다.
    return math.floor(math.prod(l["odds"] for l in legs) * 100) / 100


def kelly(p: float, o: float, frac: float = 0.25) -> float:
    if o <= 1:
        return 0.0
    f = (p * o - 1) / (o - 1)
    return max(0.0, f * frac)


def build_combo(legs: list[dict[str, Any]]) -> dict[str, Any]:
    jp = joint_prob(legs)
    to = total_odds(legs)
    ev = jp * to - 1
    payout = int(STAKE * to // 10 * 10)
    return {
        "legs": legs,
        "size": len(legs),
        "joint_p": round(jp, 4),
        "total_odds": to,
        "ev": round(ev, 4),
        "payout": payout,
        "stake": STAKE,
        "confidence": round(sum(l["confidence"] for l in legs) / len(legs)),
        "kelly": round(kelly(jp, to), 4),
        "key": "+".join(sorted(f"{l['market_id']}:{l['outcome']}" for l in legs)),
    }


def _valid(legs) -> bool:
    return len({l["match"] for l in legs}) == len(legs)


def _overlap(a: dict, b: dict) -> float:
    sa = {l["match"] for l in a["legs"]}
    sb = {l["match"] for l in b["legs"]}
    return len(sa & sb) / min(len(sa), len(sb))


def strategy_combos(legs: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    cfg = STRATEGIES[name]
    pool = [l for l in legs if l["p"] >= cfg["min_leg_p"] and l["confidence"] >= cfg["min_conf"]]
    if name == "safe":
        pool.sort(key=lambda l: -l["p"])
    else:
        pool.sort(key=lambda l: -(l["ev"] + 0.3 * l["p"]))
    pool = pool[: cfg["pool"]]
    lo, hi = cfg["odds_range"]
    cands = []
    for size in cfg["sizes"]:
        if size > len(pool):
            continue
        for combo in itertools.combinations(pool, size):
            if not _valid(combo):
                continue
            c = build_combo(list(combo))
            if not (lo <= c["total_odds"] <= hi) or c["joint_p"] < cfg["min_joint"]:
                continue
            cands.append(c)
    if name == "safe":
        cands.sort(key=lambda c: (-c["joint_p"], -c["ev"]))
    elif name == "balanced":
        cands.sort(key=lambda c: -(c["ev"] + 0.5 * c["joint_p"]))
    else:
        cands.sort(key=lambda c: -c["ev"])

    chosen: list[dict[str, Any]] = []
    for c in cands:
        if any(_overlap(c, x) > 0.67 for x in chosen):
            continue
        chosen.append(c)
        if len(chosen) >= cfg["top"]:
            break
    for i, c in enumerate(chosen, 1):
        c["strategy"] = name
        c["rank"] = i
    return chosen


def all_combos(markets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    legs = legs_from(markets)
    return {name: strategy_combos(legs, name) for name in STRATEGIES}


def value_legs(markets: list[dict[str, Any]], min_ev: float = 0.0) -> list[dict[str, Any]]:
    """기대값이 플러스인 개별 선택. 대개 해외 배당과 베트맨 배당이 어긋난 경기에서 나온다."""
    legs = [l for l in legs_from(markets, use_value=True) if l["ev"] > min_ev and l["confidence"] >= 45]
    legs.sort(key=lambda l: -l["ev"])
    for l in legs:
        l["kelly"] = round(kelly(l["p"], l["odds"]), 4)
    return legs[:10]
