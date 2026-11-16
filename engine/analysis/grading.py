"""결과 채점, 성과 집계, 확률 보정, Elo 재계산.

모든 계산은 저장된 리포트와 결과 파일에서 매번 처음부터 다시 한다.
중간 상태를 누적하지 않으므로 몇 번을 다시 돌려도 결과가 같다(멱등).
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from .. import config
from ..util import read_json, write_json
from .elo import Elo


def settle(market: dict[str, Any], res: dict[str, Any]) -> str | None:
    """마켓 결과 키 반환. 'VOID' 는 취소/적중특례. None 은 아직 결과 없음."""
    status = (res.get("status") or "FT").upper()
    if status in ("CANCELLED", "POSTPONED", "VOID", "ABANDONED"):
        return "VOID"
    if status != "FT":
        return None
    if res.get("outcome"):  # 발행처가 판정한 결과가 있으면 그대로 따른다(핸디·언오버 규정 차이 방지)
        return res["outcome"]
    try:
        hs, as_ = float(res["home_score"]), float(res["away_score"])
    except (KeyError, TypeError, ValueError):
        return None
    mk, line = market["market"], market.get("line") or 0.0
    if mk == "1X2":
        return "H" if hs > as_ else "A" if hs < as_ else "D"
    if mk == "WL":
        if hs == as_:
            return "VOID"  # 승패 마켓 동점(연장 미포함 규정 외)은 적중특례로 처리
        return "H" if hs > as_ else "A"
    if mk == "HANDICAP":
        adj = hs + line - as_
        if "D" in market.get("odds", {}) or market["sport"] == "soccer":
            return "H" if adj > 0 else "A" if adj < 0 else "D"
        return "H" if adj > 0 else "A" if adj < 0 else "VOID"
    if mk == "OU":
        t = hs + as_
        return "O" if t > line else "U" if t < line else "VOID"
    return None


def grade_report(report: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    rmap = results.get("markets", {}) if results else {}
    outcomes: dict[str, str] = {}
    for m in report.get("markets", []):
        res = rmap.get(m["id"])
        if res:
            o = settle(m, res)
            if o:
                outcomes[m["id"]] = o
    report["outcomes"] = outcomes
    from .narrative import review
    for m in report.get("markets", []):
        o = outcomes.get(m["id"])
        if o and not m.get("review"):
            rv = review(m, o)
            if rv:
                m["review"] = rv

    def grade_legs(legs):
        status, odds = "win", 1.0
        for l in legs:
            o = outcomes.get(l["market_id"])
            if o is None:
                l["result"] = None
                status = "pending" if status != "lose" else status
                continue
            if o == "VOID":
                l["result"] = "void"
                continue
            hit = o == l["outcome"]
            l["result"] = "hit" if hit else "miss"
            if hit:
                odds *= l["odds"]
            else:
                status = "lose"
        return status, math.floor(odds * 100) / 100

    for combos in report.get("combos", {}).values():
        for c in combos:
            st, eff = grade_legs(c["legs"])
            c["result"] = st
            c["return"] = int(c["stake"] * eff // 10 * 10) if st == "win" else 0 if st == "lose" else None
    for l in report.get("value_picks", []):
        o = outcomes.get(l["market_id"])
        l["result"] = None if o is None else "void" if o == "VOID" else "hit" if o == l["outcome"] else "miss"
    return report


def _dates_back(today: str, days: int) -> set[str]:
    d = date.fromisoformat(today)
    return {(d - timedelta(days=i)).isoformat() for i in range(days)}


def aggregate(reports: list[dict[str, Any]], today: str) -> dict[str, Any]:
    """전체/최근 30일 성과, 보정 곡선, 전략별 ROI."""
    last30 = _dates_back(today, 30)

    def empty():
        return {"n": 0, "hit": 0, "p_sum": 0.0, "brier": 0.0, "logloss": 0.0}

    picks_all, picks_30 = empty(), empty()
    buckets = defaultdict(lambda: {"n": 0, "hit": 0, "p_sum": 0.0})
    strat = defaultdict(lambda: {"n": 0, "win": 0, "stake": 0, "ret": 0, "p_sum": 0.0})
    strat30 = defaultdict(lambda: {"n": 0, "win": 0, "stake": 0, "ret": 0, "p_sum": 0.0})
    value = {"n": 0, "hit": 0, "stake": 0, "ret": 0.0}
    daily = []

    for rep in reports:
        outs = rep.get("outcomes") or {}
        if not outs:
            continue
        day = {"date": rep["date"], "n": 0, "hit": 0}
        for m in rep.get("markets", []):
            a = m.get("analysis")
            o = outs.get(m["id"])
            if not a or o in (None, "VOID") or m.get("preview"):
                continue
            pp = a["pick_prob"]
            hit = int(o == a["pick"])
            for acc in ([picks_all, picks_30] if rep["date"] in last30 else [picks_all]):
                acc["n"] += 1
                acc["hit"] += hit
                acc["p_sum"] += pp
                acc["brier"] += (pp - hit) ** 2
                acc["logloss"] += -math.log(max(1e-6, pp if hit else 1 - pp))
            b = min(9, int(pp * 10))
            buckets[b]["n"] += 1
            buckets[b]["hit"] += hit
            buckets[b]["p_sum"] += pp
            day["n"] += 1
            day["hit"] += hit
        if day["n"]:
            daily.append(day)
        for name, combos in (rep.get("combos") or {}).items():
            for c in combos:
                if c.get("result") not in ("win", "lose"):
                    continue
                for acc in ([strat[name], strat30[name]] if rep["date"] in last30 else [strat[name]]):
                    acc["n"] += 1
                    acc["win"] += int(c["result"] == "win")
                    acc["stake"] += c["stake"]
                    acc["ret"] += c.get("return") or 0
                    acc["p_sum"] += c["joint_p"]
        for l in rep.get("value_picks") or []:
            if l.get("result") in ("hit", "miss"):
                value["n"] += 1
                value["stake"] += 1
                if l["result"] == "hit":
                    value["hit"] += 1
                    value["ret"] += l["odds"]

    def fin(acc):
        n = acc["n"]
        return {
            "n": n,
            "hit_rate": round(acc["hit"] / n, 4) if n else None,
            "expected": round(acc["p_sum"] / n, 4) if n else None,
            "brier": round(acc["brier"] / n, 4) if n else None,
            "logloss": round(acc["logloss"] / n, 4) if n else None,
        }

    def fin_s(acc):
        n = acc["n"]
        return {
            "n": n,
            "win_rate": round(acc["win"] / n, 4) if n else None,
            "expected": round(acc["p_sum"] / n, 4) if n else None,
            "roi": round(acc["ret"] / acc["stake"] - 1, 4) if acc["stake"] else None,
        }

    return {
        "updated": config.now_kst().isoformat(timespec="seconds"),
        "picks": {"all": fin(picks_all), "30d": fin(picks_30)},
        "calibration": [
            {"bucket": f"{b * 10}-{b * 10 + 10}%", "n": v["n"],
             "expected": round(v["p_sum"] / v["n"], 4), "actual": round(v["hit"] / v["n"], 4)}
            for b, v in sorted(buckets.items()) if v["n"]
        ],
        "strategies": {k: {"all": fin_s(strat[k]), "30d": fin_s(strat30[k])} for k in ("safe", "balanced", "aggressive", "lotto")},
        "value": {
            "n": value["n"],
            "hit_rate": round(value["hit"] / value["n"], 4) if value["n"] else None,
            "roi": round(value["ret"] / value["stake"] - 1, 4) if value["stake"] else None,
        },
        "daily": daily[-60:],
    }


def fit_alpha(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """과신 보정 계수 alpha 를 로그손실 최소화로 고른다. 표본 200 미만이면 기본값 유지."""
    rows = []
    for rep in reports:
        outs = rep.get("outcomes") or {}
        for m in rep.get("markets", []):
            a = m.get("analysis")
            o = outs.get(m["id"])
            if a and o and o != "VOID" and o in a["p"] and not m.get("preview"):
                rows.append((a["p"], o))
    if len(rows) < 200:
        return {"alpha": 0.03, "n": len(rows), "note": "표본 부족, 기본값"}
    best = (1e9, 0.03)
    for i in range(0, 31):
        al = i / 100
        loss = 0.0
        for p, o in rows:
            n = len(p)
            # 저장된 p 는 이미 기존 alpha 가 적용된 값이지만, 추가 수축량을 찾는 근사로 충분하다.
            q = (1 - al) * p[o] + al / n
            loss -= math.log(max(q, 1e-6))
        if loss < best[0]:
            best = (loss, al)
    return {"alpha": best[1], "n": len(rows)}


def rebuild_elo(reports: list[dict[str, Any]], results_by_date: dict[str, dict], history: list[list] | None = None) -> Elo:
    """모든 결과로 Elo 를 처음부터 다시 계산한다(멱등). 베트맨 과거 회차 실제 점수를 먼저 반영."""
    from datetime import datetime as _dt
    elo = Elo({})
    games = {}
    for row in history or []:
        if len(row) < 14 or row[2] not in ("1X2", "WL") or row[12] is None or not isinstance(row[8], (int, float)):
            continue
        ko = _dt.fromtimestamp(row[8] / 1000, config.KST).isoformat(timespec="minutes")
        games.setdefault((row[0], ko[:10], row[10], row[11]), (ko, float(row[12]), float(row[13])))
    for rep in reports:
        rmap = (results_by_date.get(rep["date"]) or {}).get("markets", {})
        for m in rep.get("markets", []):
            res = rmap.get(m["id"])
            if not res or (res.get("status") or "FT").upper() != "FT":
                continue
            key = (m["sport"], m["kickoff"][:10], m["home"], m["away"])
            if key in games:
                continue  # 같은 경기의 여러 마켓은 한 번만 반영
            try:
                games[key] = (m["kickoff"], float(res["home_score"]), float(res["away_score"]))
            except (KeyError, TypeError, ValueError):
                continue
    for (sport, _, home, away), (ko, hs, as_) in sorted(games.items(), key=lambda kv: kv[1][0]):
        score = 1.0 if hs > as_ else 0.0 if hs < as_ else 0.5
        elo.update(sport, home, away, score, margin=hs - as_)
    return elo


def save_state(perf, cal, elo: Elo):
    write_json(config.STATE / "performance.json", perf)
    write_json(config.STATE / "calibration.json", cal)
    elo.save()


def load_perf() -> dict[str, Any]:
    return read_json(config.STATE / "performance.json", {}) or {}
