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
    "lotto": {
        "label": "로또폴더", "sizes": (5, 6, 7, 8), "min_leg_p": 0.30, "min_conf": 25,
        "odds_range": (40.0, 5000.0), "min_joint": 0.0008, "top": 3, "pool": 16,
        "desc": "5~8경기를 묶어 수십~수백 배를 노리는 한 장. 커피값으로 즐기는 용도입니다.",
    },
}

CORR_PENALTY = 0.985  # 같은 리그·같은 날 한 쌍당 결합확률 감쇠


def match_key(m: dict[str, Any]) -> str:
    return f"{m['kickoff'][:10]}|{m['home']}|{m['away']}"


def legs_from(markets: list[dict[str, Any]], use_value: bool = False, all_outcomes: bool = False) -> list[dict[str, Any]]:
    legs = []
    for m in markets:
        a = m.get("analysis")
        if not a or m.get("pool") != "proto" or not m.get("odds"):
            continue
        keys = list(m["odds"]) if all_outcomes else [a["value_key"] if use_value else a["pick"]]
        for key in keys:
            if key is None or key not in m["odds"] or key not in a["p"]:
                continue
            legs.append(_leg(m, a, key))
    return legs


def _leg(m: dict[str, Any], a: dict[str, Any], key: str) -> dict[str, Any]:
    if True:
        p = a["p"][key]
        o = m["odds"][key]
        return ({
            "market_id": m["id"], "match": match_key(m), "league": m["league"], "sport": m["sport"],
            "date": m["kickoff"][:10], "home": m["home"], "away": m["away"], "market": m["market"],
            "line": m.get("line"), "game_no": m.get("game_no"), "kickoff": m["kickoff"],
            "outcome": key, "p": p, "odds": o, "ev": p * o - 1, "confidence": a["confidence"],
            "upset_risk": a["upset_risk"],
        })


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
    elif name in ("aggressive", "lotto"):
        # 큰 배당을 노리므로 1.45배 미만 정배는 빼고, 기대값이 덜 나쁜(배당이 공정한) 선택부터
        pool = [l for l in pool if l["odds"] >= 1.45]
        pool.sort(key=lambda l: -(l["ev"] + 0.15 * l["p"]))
    else:
        pool.sort(key=lambda l: -(l["ev"] + 0.3 * l["p"]))
    # 한 경기의 여러 마켓이 후보를 독식하지 않게 경기당 최대 2개까지만 남긴다
    per: dict[str, int] = {}
    diverse = []
    for l in pool:
        if per.get(l["match"], 0) < (1 if name in ("aggressive", "lotto") else 2):
            diverse.append(l)
            per[l["match"]] = per.get(l["match"], 0) + 1
    pool = diverse[: cfg["pool"]]
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
    elif name == "lotto":
        cands.sort(key=lambda c: -(c["ev"] + 2 * c["joint_p"]))
    else:
        cands.sort(key=lambda c: -c["ev"])

    chosen: list[dict[str, Any]] = []
    for c in cands:
        if any(_overlap(c, x) > (0.8 if name == "lotto" else 0.67) for x in chosen):
            continue
        chosen.append(c)
        if len(chosen) >= cfg["top"]:
            break
    for i, c in enumerate(chosen, 1):
        c["strategy"] = name
        c["rank"] = i
    return chosen


def all_combos(markets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    picks = legs_from(markets)
    every = legs_from(markets, all_outcomes=True)  # 공격형·로또는 확률이 충분한 역배도 후보
    return {name: strategy_combos(every if name in ("aggressive", "lotto") else picks, name) for name in STRATEGIES}


def value_legs(markets: list[dict[str, Any]], min_ev: float = 0.0) -> list[dict[str, Any]]:
    """기대값이 플러스인 개별 선택. 대개 해외 배당과 베트맨 배당이 어긋난 경기에서 나온다."""
    legs = [l for l in legs_from(markets, use_value=True) if l["ev"] > min_ev and l["confidence"] >= 45]
    legs.sort(key=lambda l: -l["ev"])
    for l in legs:
        l["kelly"] = round(kelly(l["p"], l["odds"]), 4)
    return legs[:10]


def _flow_drop(m: dict[str, Any], key: str) -> float:
    fl = m.get("flow") or {}
    f0, f1 = (fl.get("from") or {}).get(key), (fl.get("to") or {}).get(key)
    return (f0 - f1) / f0 if f0 and f1 else 0.0


def upset_legs(markets: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """역배 후보: 배당 2.2배 이상이면서 근거가 겹치는 선택.

    점수 = (모델 확률 − 베트맨 내재확률)  +  배당 하락폭(구매 쏠림)  +  같은 배당 구간 과거 수익률.
    정배만 사서 잃는 것을 막기 위한 목록이다. 근거가 하나도 없으면 싣지 않는다.
    """
    out = []
    for m in markets:
        a = m.get("analysis")
        if not a or m["market"] not in ("1X2", "WL", "HANDICAP"):
            continue
        for k, o in (m.get("odds") or {}).items():
            if k == a["pick"] or o < 2.2 or o > 9 or k not in a["p"]:
                continue
            p = a["p"][k]
            edge = p - (a.get("p_betman") or {}).get(k, p)
            drop = _flow_drop(m, k)
            hist = (a.get("hist") or {}).get(k) or {}
            hroi = hist.get("roi", -0.2)
            reasons = []
            if edge >= 0.015:
                reasons.append(f"모델 확률이 베트맨 내재확률보다 {edge * 100:.1f}%p 높음")
            if drop >= 0.02:
                reasons.append(f"배당 {drop * 100:.0f}% 하락(구매 쏠림)")
            if hist and hroi > -0.05 and hist.get("n", 0) >= 100:
                reasons.append(f"같은 배당 구간 과거 수익률 {hroi * 100:+.1f}%")
            ref = (a.get("p_ref") or {}).get(k)
            if ref and ref * o > 0.97:
                reasons.append("해외 시장 기준 배당이 후함")
            if not reasons or p < 0.2:
                continue
            leg = _leg(m, a, k)
            leg["score"] = round(edge * 3 + drop * 2 + max(hroi, -0.3) + p * 0.3, 4)
            leg["reasons"] = reasons
            out.append(leg)
    out.sort(key=lambda l: -l["score"])
    seen, uniq = set(), []
    for l in out:
        if l["match"] in seen:
            continue
        seen.add(l["match"])
        uniq.append(l)
    return uniq[:limit]


def market_legs(markets: list[dict[str, Any]], market: str, limit: int = 6) -> list[dict[str, Any]]:
    """핸디캡·언더오버에서 가장 근거가 좋은 선택."""
    out = []
    for m in markets:
        a = m.get("analysis")
        if not a or m["market"] != market:
            continue
        k = a["pick"]
        if k not in (m.get("odds") or {}):
            continue
        leg = _leg(m, a, k)
        hist = (a.get("hist") or {}).get(k) or {}
        drop = _flow_drop(m, k)
        leg["hist_hit"] = hist.get("hit")
        leg["hist_n"] = hist.get("n")
        leg["drop"] = round(drop, 4)
        leg["score"] = round(leg["p"] - 1 / leg["odds"] * 0.9 + drop * 1.5 + (hist.get("roi", -0.15) if hist else -0.15) * 0.5, 4)
        out.append(leg)
    out.sort(key=lambda l: -l["score"])
    seen, uniq = set(), []
    for l in out:
        if l["match"] in seen:
            continue
        seen.add(l["match"])
        uniq.append(l)
    return uniq[:limit]
