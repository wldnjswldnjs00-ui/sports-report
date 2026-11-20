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

from .xbook import x_hist

STAKE = 10_000  # 예시 금액(원)

STRATEGIES = {
    "safe": {
        "label": "안정형", "sizes": (2, 3), "min_leg_p": 0.66, "min_conf": 50, "min_leg_odds": 1.12,
        "odds_range": (1.2, 3.5), "min_joint": 0.40, "top": 10, "pool": 16,
        "desc": "확률이 높은 경기만 2~3개 묶습니다.",
    },
    "single": {
        "label": "단폴더", "sizes": (1,), "min_leg_p": 0.55, "min_conf": 40,
        "odds_range": (1.5, 4.0), "min_joint": 0.0, "top": 8, "pool": 40,
        "desc": "베트맨에서 한 경기만 살 수 있는 경기 중, 확률 55% 이상이고 배당 1.5배 이상인 선택입니다. 승패·핸디캡·언오버 모두 봅니다.",
    },
    "balanced": {
        "label": "밸런스형", "sizes": (2, 3, 4), "min_leg_p": 0.55, "min_conf": 40, "min_leg_odds": 1.3,
        "odds_range": (2.5, 8.0), "min_joint": 0.10, "top": 12, "pool": 18,
        "desc": "적중 가능성과 배당의 균형을 맞춘 3~4경기 조합입니다.",
    },
    "aggressive": {
        "label": "공격형", "sizes": (3, 4, 5), "min_leg_p": 0.38, "min_conf": 30,
        "odds_range": (7.0, 80.0), "min_joint": 0.012, "top": 12, "pool": 18,
        "desc": "역배를 섞어 7배 이상을 노리는 조합입니다.",
    },
    "upset": {
        "label": "역배 조합", "sizes": (2, 3), "min_leg_p": 0.22, "min_conf": 25,
        "odds_range": (4.0, 60.0), "min_joint": 0.025, "top": 10, "pool": 14,
        "desc": "배당이 더 높은 쪽만 2~3경기 묶은 조합입니다.",
    },
    "lotto": {
        "label": "로또폴더", "sizes": (5, 6, 7, 8), "min_leg_p": 0.22, "min_conf": 25,
        "odds_range": (40.0, 5000.0), "min_joint": 0.0003, "top": 6, "pool": 16,
        "desc": "5~8경기를 묶어 수십 배 이상을 노리는 한 장입니다.",
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
            leg = _leg(m, a, key)
            leg["dog"] = _is_dog(m, a, key)  # 그 경기에서 해외 배당이 더 높은 쪽
            legs.append(leg)
    return legs


def _leg(m: dict[str, Any], a: dict[str, Any], key: str) -> dict[str, Any]:
    if True:
        p = a["p"][key]
        o = m["odds"][key]
        return ({
            "market_id": m["id"], "match": match_key(m), "league": m["league"], "sport": m["sport"],
            "date": m["kickoff"][:10], "home": m["home"], "away": m["away"], "market": m["market"],
            "line": m.get("line"), "game_no": m.get("game_no"), "round": m.get("round"), "kickoff": m["kickoff"],
            "outcome": key, "p": p, "odds": o, "x_odds": (a.get("x_odds") or {}).get(key), "x_kind": a.get("x_kind"),
            "ev": p * o - 1, "confidence": a["confidence"],
            # 후보 정렬은 해외 배당 기준: 해외 기준 추정 확률 × 해외 배당 − 1 (베트맨 배당이 후한지는 보지 않는다)
            "xev": p * ((a.get("x_odds") or {}).get(key) or (1 / p if p else 1)) - 1,
            "xo": (a.get("x_odds") or {}).get(key) or o,
            "upset_risk": a["upset_risk"],
            "single": bool(m.get("single")),
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
        "xev": round(jp * math.prod(l.get("xo") or l["odds"] for l in legs) - 1, 4),
        "payout": payout,
        "stake": STAKE,
        "confidence": round(sum(l["confidence"] for l in legs) / len(legs)),
        "kelly": round(kelly(jp, to), 4),
        "key": "+".join(sorted(f"{l['market_id']}:{l['outcome']}" for l in legs)),
    }


def _valid(legs) -> bool:
    """같은 경기 중복 금지 + 같은 회차끼리만(베트맨은 회차가 다른 경기를 한 장으로 살 수 없다)."""
    if len({l["match"] for l in legs}) != len(legs):
        return False
    return len({str(l.get("round") or "") for l in legs}) <= 1


def _overlap(a: dict, b: dict) -> float:
    sa = {l["match"] for l in a["legs"]}
    sb = {l["match"] for l in b["legs"]}
    return len(sa & sb) / min(len(sa), len(sb))


def strategy_combos(legs: list[dict[str, Any]], name: str, used_all: dict[str, int] | None = None) -> list[dict[str, Any]]:
    cfg = STRATEGIES[name]
    pool = [l for l in legs if l["p"] >= cfg["min_leg_p"] and l["confidence"] >= cfg["min_conf"]]
    # 조합 배당 범위에 닿을 수 있는 경기만 후보로(1.01~1.1 같은 초저배당이 후보 자리를 다 차지하면 조합이 0개가 된다)
    lo_leg = cfg.get("min_leg_odds")
    low = []
    if lo_leg:
        low = [l for l in pool if l["odds"] < lo_leg]
        pool = [l for l in pool if l["odds"] >= lo_leg]
    if name == "safe":
        pool.sort(key=lambda l: -l["p"])
    elif name == "single":
        # 단폴 가능 경기만, 해외 기준 값이 좋고 확률이 높은 순
        pool = [l for l in pool if l.get("single")]
        pool.sort(key=lambda l: -(l["xev"] + 0.5 * l["p"]))
    elif name == "upset":
        pool = [l for l in pool if l.get("dog")]
        pool.sort(key=lambda l: -(l["xev"] + 0.2 * l["p"]))
    elif name in ("aggressive", "lotto"):
        # 큰 배당을 노리므로 해외 배당 1.45배 미만 정배는 빼고, 해외 기준 값이 좋은 선택부터
        pool = [l for l in pool if (l.get("xo") or l["odds"]) >= 1.45]
        pool.sort(key=lambda l: -(l["xev"] + 0.15 * l["p"]))
    else:
        pool.sort(key=lambda l: -(l["xev"] + 0.3 * l["p"]))
    # 한 경기의 여러 마켓이 후보를 독식하지 않게 경기당 최대 2개까지만 남긴다
    per: dict[str, int] = {}
    diverse = []
    for l in pool:
        if per.get(l["match"], 0) < (1 if name in ("aggressive", "lotto", "upset", "single") else 2):
            diverse.append(l)
            per[l["match"]] = per.get(l["match"], 0) + 1
    if name in ("aggressive", "lotto"):
        # 점수 좋은 선택 절반 + 배당 큰 선택 절반을 섞어야 높은 배당 구간 조합이 나온다
        half = cfg["pool"] // 2
        by_odds = sorted(diverse, key=lambda l: -(l.get("xo") or l["odds"]))
        pool, used = [], set()
        for l in diverse[:half] + by_odds:
            if l["match"] in used:
                continue
            used.add(l["match"])
            pool.append(l)
            if len(pool) >= cfg["pool"]:
                break
    else:
        pool = diverse[: cfg["pool"]]
        if lo_leg and len(pool) < cfg["pool"]:
            # 배당이 맞는 경기가 모자라는 날(경기 적은 날)만 낮은 배당 경기로 채운다
            low.sort(key=lambda l: -l["odds"])
            seen = {l["match"]: 0 for l in pool}
            for l in pool:
                seen[l["match"]] += 1
            for l in low:
                if len(pool) >= cfg["pool"]:
                    break
                if seen.get(l["match"], 0) < 2:
                    pool.append(l)
                    seen[l["match"]] = seen.get(l["match"], 0) + 1
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
        cands.sort(key=lambda c: (-c["joint_p"], -c["xev"]))
    elif name == "single":
        cands.sort(key=lambda c: -(c["xev"] + 0.5 * c["joint_p"]))
    elif name == "balanced":
        cands.sort(key=lambda c: -(c["xev"] + 0.5 * c["joint_p"]))
    elif name == "upset":
        cands.sort(key=lambda c: -(c["xev"] + c["joint_p"]))
    elif name == "lotto":
        cands.sort(key=lambda c: -(c["xev"] + 2 * c["joint_p"]))
    else:
        cands.sort(key=lambda c: -c["xev"])

    chosen: list[dict[str, Any]] = []
    max_overlap = 0.8 if name == "lotto" else 0.67

    used: dict[str, int] = {}
    used_all = used_all if used_all is not None else {}
    n_matches = len({l["match"] for l in legs})
    # 경기가 적은 날은 조합 수를 줄인다(억지로 채우면 같은 경기만 반복된다)
    top_n = cfg["top"]  # 개수 상한. 실제 개수는 확률 기준(min_joint)과 겹침 제한을 통과한 만큼만 나온다
    bonus = 3 if name == "lotto" else 0   # 로또폴더는 폴더 수가 많아 합계 한도를 넉넉히

    def take(pool_c, n, cap=1, cap_all=3):
        """cap: 한 전략 안에서 같은 경기가 들어갈 수 있는 횟수, cap_all: 전 전략 합계."""
        for c in pool_c:
            if len(chosen) >= top_n or n <= 0:
                break
            ms = [l["match"] for l in c["legs"]]
            if c in chosen or any(used.get(k, 0) >= cap or used_all.get(k, 0) >= cap_all + bonus for k in ms):
                continue
            if any(_overlap(c, x) > max_overlap or abs(c["total_odds"] / x["total_odds"] - 1) < 0.04 for x in chosen):
                continue
            chosen.append(c)
            for k in ms:
                used[k] = used.get(k, 0) + 1
                used_all[k] = used_all.get(k, 0) + 1
            n -= 1

    # 배당이 한 구간에 몰리지 않게: 구간별로 가장 좋은 조합을 먼저 뽑고, 모자라면 전체에서 채운다
    tiers = {"lotto": [(40, 80, 2), (80, 200, 2), (200, 5000, 2)],
             "aggressive": [(7, 12, 4), (12, 25, 4), (25, 80, 4)],
             "upset": [(4, 8, 4), (8, 16, 3), (16, 60, 3)],
             "balanced": [(2.5, 3.5, 4), (3.5, 5, 4), (5, 8, 4)]}.get(name)
    # 같은 경기가 여러 조합에 반복되지 않게: 먼저 '경기당 1번'으로 뽑고, 모자랄 때만 2번·3번까지 허용
    for cap, cap_all in ((1, 4), (2, 7), (3, 10), (4, 14)):
        if tiers:
            for lo_t, hi_t, n_t in tiers:
                have = sum(1 for c in chosen if lo_t <= c["total_odds"] < hi_t)
                take([c for c in cands if lo_t <= c["total_odds"] < hi_t], n_t - have, cap, cap_all)
        take(cands, top_n, cap, cap_all)
        if len(chosen) >= top_n:
            break
    chosen.sort(key=lambda c: c["total_odds"])
    for i, c in enumerate(chosen, 1):
        c["strategy"] = name
        c["rank"] = i
    return chosen


def all_combos(markets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    picks = legs_from(markets)
    every = legs_from(markets, all_outcomes=True)  # 공격형·로또는 확률이 충분한 역배도 후보
    used_all: dict[str, int] = {}
    # 단폴더는 한 경기짜리라 다른 전략의 '같은 경기 반복 제한' 계산에 넣지 않는다
    return {name: strategy_combos(every if name in ("aggressive", "lotto", "upset") else picks, name, {} if name == "single" else used_all)
            for name in STRATEGIES}


def value_legs(markets: list[dict[str, Any]], min_ev: float = 0.0) -> list[dict[str, Any]]:
    """기대값이 플러스인 개별 선택. 대개 해외 배당과 베트맨 배당이 어긋난 경기에서 나온다."""
    legs = [l for l in legs_from(markets, use_value=True) if l["ev"] > min_ev and l["confidence"] >= 45]
    legs.sort(key=lambda l: -l["ev"])
    for l in legs:
        l["kelly"] = round(kelly(l["p"], l["odds"]), 4)
    return legs[:10]


def _is_dog(m: dict[str, Any], a: dict[str, Any], key: str) -> bool:
    """역배 = 승패·승무패에서 베트맨 배당이 상대보다 높은 쪽(무승부 제외).

    핸디캡·언더오버는 기준점으로 양쪽 배당을 맞춘 마켓이라 역배로 보지 않는다. 배당이 같으면 역배가 아니다."""
    if m.get("market") not in ("1X2", "WL") or key == "D":
        return False
    od = {k: v for k, v in (m.get("odds") or {}).items() if k != "D" and v}
    return key in od and len(od) >= 2 and od[key] > min(v for k, v in od.items() if k != key)


def upset_legs(markets: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """역배 후보: 해외 배당이 더 높은 쪽인데 해외 기준 근거가 겹치는 선택. 베트맨 배당·배당 변동은 쓰지 않는다.

    근거: ① 해외 배당이 비슷했던 과거 경기에서 실제로 해외 배당 확률보다 자주 이겼다
          ② 팀 레이팅이 해외 시장보다 이 팀을 높게 본다
          ③ 해외 기준 추정 확률이 40% 이상인 박빙
    """
    out = []
    for m in markets:
        a = m.get("analysis")
        if not a or m["market"] not in ("1X2", "WL"):
            continue
        for k in (m.get("odds") or {}):
            if not _is_dog(m, a, k) or k not in a["p"]:
                continue
            xo = (a.get("x_odds") or {}).get(k) or m["odds"][k]
            if xo > 9:
                continue
            p = a["p"][k]
            ref = (a.get("p_ref") or {}).get(k, p)
            hist = x_hist(a).get(k) or {}
            elo = (a.get("p_elo") or {}).get(k)
            reasons, score = [], p * 0.5
            if hist.get("n", 0) >= 100 and hist["hit"] >= ref + 0.01:
                reasons.append(f"해외 배당이 비슷했던 {hist['bucket']} {hist['n']:,}경기에서 실제 {hist['hit'] * 100:.0f}% 적중(해외 배당 확률 {ref * 100:.0f}%)")
                score += (hist["hit"] - ref) * 3
            if elo is not None and elo >= ref + 0.03:
                reasons.append(f"팀 레이팅은 {elo * 100:.0f}%로 해외 시장보다 높게 봄")
                score += elo - ref
            if p >= 0.4:
                reasons.append(f"해외 기준 추정 확률 {p * 100:.0f}%의 박빙")
            if not reasons or p < 0.25:
                continue
            leg = _leg(m, a, k)
            leg["score"] = round(score, 4)
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
        xo = (a.get("x_odds") or {}).get(k)
        if k not in (m.get("odds") or {}) or not xo or xo < 1.2:
            continue  # 해외 배당 1.2배 미만은 고를 의미가 없어 제외
        leg = _leg(m, a, k)
        hist = x_hist(a).get(k) or {}
        ref = (a.get("p_ref") or {}).get(k, leg["p"])
        leg["hist_hit"] = hist.get("hit")
        leg["hist_n"] = hist.get("n")
        # 해외 기준 추정 확률 + 해외 기록이 해외 배당 확률보다 더 자주 맞았던 만큼
        leg["score"] = round(leg["p"] + ((hist["hit"] - ref) * 0.5 if hist else 0), 4)
        out.append(leg)
    out.sort(key=lambda l: -l["score"])
    seen, uniq = set(), []
    for l in out:
        if l["match"] in seen:
            continue
        seen.add(l["match"])
        uniq.append(l)
    return uniq[:limit]
