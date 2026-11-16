"""수집 → 분석 → 리포트 저장 → 채점 → 성과 집계.

안전 규칙
1. 킥오프가 지난 경기의 픽은 절대 바꾸지 않는다(사후 수정 방지). 처음 발행된 분석을 고정한다.
2. 모든 소스가 실패해도 이전 리포트를 지우지 않는다. 실패 상태를 리포트에 기록한다.
3. 데모 데이터는 운영 데이터 폴더에 섞이지 않는다(DATA_DIR 분리).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from . import config
from .analysis import combos as C
from .analysis import grading as G
from .analysis.elo import Elo
from .analysis.model import analyze_market, calibration_alpha
from .analysis.narrative import describe, headline
from .schema import validate_all
from .sources import betman, manual, odds_api, sample
from .sources.aliases import alias_map, odds_api_key_for
from .util import read_json, write_json

log = logging.getLogger("engine")


def report_path(day: str):
    return config.REPORTS / f"{day}.json"


def results_path(day: str):
    return config.RESULTS / f"{day}.json"


def _merge(primary: list[dict], extra: list[dict]) -> list[dict]:
    """수동 입력이 같은 경기(홈/원정/마켓)를 덮어쓴다. 사람이 고친 값이 우선."""
    key = lambda m: (m["home"], m["away"], m["market"], m.get("line"))  # noqa: E731
    by = {key(m): m for m in primary}
    for m in extra:
        by[key(m)] = m
    return list(by.values())


def collect(day: str, refresh_ref: bool = False) -> dict[str, Any]:
    status: dict[str, str] = {}
    markets: list[dict] = []
    ref: dict[str, dict] = {}
    demo_results: dict[str, dict] = {}

    if config.DEMO:
        markets, ref, demo_results = sample.generate(day)
        status["sample"] = f"{len(markets)}개 (데모)"
    else:
        try:
            markets = betman.fetch(day)
            status["betman"] = f"{len(markets)}개 수집"
        except Exception as e:  # noqa: BLE001
            log.warning("베트맨 수집 실패: %s", e)
            status["betman"] = f"실패: {type(e).__name__}"
        man = manual.load_markets(day)
        if man:
            markets = _merge(markets, man)
            status["manual"] = f"{len(man)}개 반영"

    markets = validate_all(markets, log)
    prev = read_json(report_path(day), {}) or {}
    prev_by_id = {m["id"]: m for m in prev.get("markets", [])}

    if not config.DEMO:
        odds_api.prune_cache()
        try:
            ref, st = odds_api.reference(markets, day, refresh=refresh_ref)
            status["odds_api"] = st
        except Exception as e:  # noqa: BLE001
            status["odds_api"] = f"실패: {type(e).__name__}"

    if not markets and prev.get("markets"):
        log.warning("새 데이터 없음. 기존 리포트 유지")
        prev.setdefault("sources", {}).update({k: v for k, v in status.items()})
        prev["last_attempt"] = config.now_kst().isoformat(timespec="seconds")
        write_json(report_path(day), prev)
        return prev

    elo = Elo.load()
    alpha = calibration_alpha()
    from .analysis import oddsbook
    book = oddsbook.load()
    now = config.now_kst()
    analyzed = []
    for m in markets:
        old = prev_by_id.get(m["id"])
        started = datetime.fromisoformat(m["kickoff"]) <= now
        if old and old.get("analysis") and started:
            # 고정: 킥오프 이후에는 처음 분석 유지, 배당만 마지막 값 기록
            old["odds_close"] = m["odds"]
            analyzed.append(old)
            continue
        a = analyze_market(m, elo, ref.get(m["id"]), alpha, book)
        a["odds_open"] = (old or {}).get("odds_open") or m["odds"]
        a["narrative"] = describe(a)
        analyzed.append(a)
    analyzed.sort(key=lambda m: (m["kickoff"], m.get("game_no") or 0))
    # 오늘(당일 06시~익일 06시) 경기만 조합·채점 대상. 그 뒤 경기는 미리보기로만 보여준다
    # (다음 날 리포트에서 본 경기로 다시 다뤄지므로 성과가 두 번 집계되지 않는다).
    for m in analyzed:
        m["preview"] = not betman.in_window(m["kickoff"], day)
    primary = [m for m in analyzed if not m["preview"]]

    proto = [m for m in primary if m.get("analysis") and m["pool"] == "proto"]
    combos = C.all_combos(proto)
    # 이미 발행된 조합 중 경기가 시작된 것은 유지(사후 교체 방지)
    for name, old_list in (prev.get("combos") or {}).items():
        locked = [c for c in old_list if any(datetime.fromisoformat(l["kickoff"]) <= now for l in c["legs"])]
        if locked:
            keys = {c["key"] for c in locked}
            fresh = [c for c in combos.get(name, []) if c["key"] not in keys]
            merged = locked + fresh
            combos[name] = merged[: C.STRATEGIES[name]["top"] + len(locked)]
    value = C.value_legs(proto)

    legs = C.legs_from(proto)
    top = max((l for l in legs if l["confidence"] >= 55 and l["odds"] >= 1.2), key=lambda l: l["p"] * (1 + l["confidence"] / 200), default=None)
    caution = sorted(
        [m for m in proto if m["analysis"]["pick_odds"] and m["analysis"]["pick_odds"] < 1.9 and m["analysis"]["upset_risk"] >= 33],
        key=lambda m: -m["analysis"]["upset_risk"],
    )[:5]
    moves = []
    for m in primary:
        o0, o1 = m.get("odds_open") or {}, m.get("odds_close") or m.get("odds") or {}
        for k in o1:
            if k in o0 and o0[k] and abs(o1[k] - o0[k]) / o0[k] >= 0.05:
                moves.append({"market_id": m["id"], "home": m["home"], "away": m["away"], "outcome": k, "from": o0[k], "to": o1[k]})

    report = {
        "date": day,
        "generated_at": prev.get("generated_at") or now.isoformat(timespec="seconds"),
        "updated_at": now.isoformat(timespec="seconds"),
        "model_version": config.MODEL_VERSION,
        "calibration_alpha": alpha,
        "demo": config.DEMO,
        "sources": status,
        "markets": analyzed,
        "combos": combos,
        "value_picks": value,
        "top_pick": top,
        "caution": [m["id"] for m in caution],
        "odds_moves": moves,
        "stats": {
            "markets": len(analyzed),
            "matches": len({(m["home"], m["away"], m["kickoff"][:10]) for m in primary}),
            "upcoming": len({(m["home"], m["away"], m["kickoff"][:10]) for m in analyzed if m["preview"]}),
            "legs": len(legs),
            "combos": sum(len(v) for v in combos.values()),
        },
        "outcomes": prev.get("outcomes", {}),
    }
    report["headline"] = headline(report)
    write_json(report_path(day), report)
    if config.DEMO and demo_results:
        write_json(results_path(day), {"markets": demo_results})
    log.info("%s 리포트 저장: 마켓 %d, 조합 %d", day, report["stats"]["markets"], report["stats"]["combos"])
    return report


def all_reports() -> list[dict]:
    out = []
    for p in sorted(config.REPORTS.glob("*.json")):
        r = read_json(p)
        if r and r.get("date"):
            out.append(r)
    return out


def _collect_results(rep: dict, fetch_scores: bool = True) -> dict:
    """수동 + Odds API 결과를 합친다. 기존 결과는 덮어쓰지 않고 보강만 한다."""
    path = results_path(rep["date"])
    res = read_json(path, {"markets": {}}) or {"markets": {}}
    rmap = res.setdefault("markets", {})
    # 예전 형식(판정 코드 없는) 베트맨 결과는 다시 받는다
    for k in [k for k, v in rmap.items() if v.get("src") == "betman" and v.get("status") == "FT" and not v.get("outcome")]:
        del rmap[k]
    pending = [m for m in rep.get("markets", []) if m["id"] not in rmap and not m.get("preview")]
    if not pending:
        return res

    rows = manual.load_results(rep["date"])
    for m in pending:
        for r in rows:
            if (r.get("game_no") and m.get("game_no") and str(m["game_no"]) == r["game_no"]) or (
                r.get("home") == m["home"] and r.get("away") == m["away"]):
                try:
                    rmap[m["id"]] = {"home_score": float(r["home_score"] or 0), "away_score": float(r["away_score"] or 0),
                                     "status": (r.get("status") or "FT").upper(), "src": "manual"}
                except ValueError:
                    pass
                break

    pending = [m for m in pending if m["id"] not in rmap]
    now = config.now_kst()
    finished = [m for m in pending if datetime.fromisoformat(m["kickoff"]) + timedelta(hours=2, minutes=30) < now]
    # 1순위: 베트맨 공식 결과(전 종목, 키 불필요)
    rounds = {str(m.get("round")) for m in finished if m.get("source") == "betman" and m.get("round")}
    if rounds and not config.DEMO:
        for mid, r in betman.fetch_results(rounds).items():
            if mid not in rmap and any(m["id"] == mid for m in finished):
                rmap[mid] = r
        finished = [m for m in finished if m["id"] not in rmap]
    keys = {odds_api_key_for(m["league"]) for m in finished} - {None}
    if keys and fetch_scores and not config.DEMO:
        events = odds_api.scores(keys)
        amap = alias_map()
        for m in finished:
            r = odds_api.result_for(m, events, amap)
            if r:
                rmap[m["id"]] = r
    write_json(path, res)
    return res


def grade(today: str, lookback: int = 7, fetch_scores: bool = True) -> dict:
    reports = all_reports()
    cutoff = (date.fromisoformat(today) - timedelta(days=lookback)).isoformat()
    results_by_date = {}
    for rep in reports:
        if rep["date"] >= cutoff and not config.DEMO:
            res = _collect_results(rep, fetch_scores)
        else:
            res = read_json(results_path(rep["date"]), {}) or {}
        results_by_date[rep["date"]] = res
        G.grade_report(rep, res)
        write_json(report_path(rep["date"]), rep)
    perf = G.aggregate(reports, today)
    cal = G.fit_alpha(reports)
    elo = G.rebuild_elo(reports, results_by_date)
    G.save_state(perf, cal, elo)
    log.info("채점 완료: 픽 %s", perf["picks"]["all"])
    return perf


def history(max_rounds: int = 8) -> None:
    """과거 회차 백필 + 배당 구간표 재계산. 실패해도 다른 단계에 영향 없음."""
    from .analysis import oddsbook
    from .sources import betman_history
    try:
        betman_history.backfill(max_rounds)
    except Exception:  # noqa: BLE001
        log.exception("백필 실패")
    rows = betman_history.load_all()
    if rows:
        oddsbook.save(oddsbook.build(rows))
        log.info("배당 구간표 갱신: %d개 선택 기록", len(rows))


def demo(days: int = 21) -> None:
    """과거 N일치 샘플 리포트와 결과를 만들어 사이트 미리보기를 채운다."""
    assert config.DEMO, "DEMO=1 에서만 실행"
    today = date.fromisoformat(config.today_kst())
    for i in range(days, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        collect(d)
        if i == 0:
            # 오늘 결과는 아직 없다
            p = results_path(d)
            if p.exists():
                p.unlink()
    grade(today.isoformat())
