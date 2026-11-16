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
    from .analysis import xbook
    book = xbook.load()
    now = config.now_kst()
    analyzed = []
    for m in markets:
        old = prev_by_id.get(m["id"])
        started = datetime.fromisoformat(m["kickoff"]) <= now
        if old and old.get("analysis") and started:
            # 고정: 킥오프 이후에는 처음 분석 유지, 배당만 마지막 값 기록
            old["odds_close"] = m["odds"]
            old["flow"] = m.get("flow")
            analyzed.append(old)
            continue
        a = analyze_market(m, elo, ref.get(m["id"]), alpha, book)
        a["odds_open"] = (old or {}).get("odds_open") or m["odds"]
        a["narrative"] = describe(a)
        analyzed.append(a)
    analyzed.sort(key=lambda m: (m["kickoff"], m.get("game_no") or 0))
    # 최근 10경기·상대 전적(올 시즌 포함)·휴식일
    if not config.DEMO:
        try:
            from .analysis import form as F
            from .sources import betman_history
            reps = all_reports()
            rbd = {r["date"]: read_json(results_path(r["date"]), {}) or {} for r in reps}
            nf = F.attach(analyzed, F.build(betman_history.load_all(), reps, rbd))
            status["form"] = f"{nf}개 마켓"
        except Exception:  # noqa: BLE001
            log.exception("흐름 처리 실패(분석은 계속)")
    # 근거 데이터가 다 붙은 뒤 분석문(오레오)을 쓴다. 시작된 경기의 글은 고정.
    for m in analyzed:
        if m.get("analysis") and not (datetime.fromisoformat(m["kickoff"]) <= now and m.get("oreo")):
            m["narrative"] = describe(m)
    # 오늘 구매일(당일 08:30~익일 08:30 킥오프) 경기만 조합·채점 대상. 그 뒤 경기는 미리보기로만 보여준다
    # (다음 날 리포트에서 본 경기로 다시 다뤄지므로 성과가 두 번 집계되지 않는다).
    # 전날 리포트에서 이미 본 경기로 다룬 것은 다시 세지 않는다(날짜 기준을 바꿔도 이중 집계 방지).
    yday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    covered = {m["id"] for m in (read_json(report_path(yday), {}) or {}).get("markets", []) if not m.get("preview")}
    analyzed = [m for m in analyzed if m["id"] not in covered]
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
            top_n = C.STRATEGIES[name]["top"]
            combos[name] = (locked[:top_n] + fresh)[:top_n]  # 고정된 조합 우선, 전략별 개수는 그대로
    value = C.value_legs(proto)
    upcoming = [m for m in analyzed if m.get("analysis") and m["pool"] == "proto" and datetime.fromisoformat(m["kickoff"]) > now]
    upsets = C.upset_legs(upcoming)
    handi_picks = C.market_legs(upcoming, "HANDICAP")
    ou_picks = C.market_legs(upcoming, "OU")

    legs = C.legs_from(proto)
    cands = sorted((l for l in legs if l["confidence"] >= 55 and (l.get("x_odds") or l["odds"]) >= 1.2 and datetime.fromisoformat(l["kickoff"]) > now),
                   key=lambda l: -(l["p"] * (1 + l["confidence"] / 200)))
    top_picks, seen_match = [], set()
    for l in cands:
        if l["match"] in seen_match:
            continue
        seen_match.add(l["match"])
        top_picks.append(l)
        if len(top_picks) >= 6:
            break
    top = top_picks[0] if top_picks else (prev.get("top_pick") if prev.get("date") == day else None)
    caution = sorted(
        # 해외 배당 기준 정배(1.9배 미만)인데 이변 위험이 높은 경기
        [m for m in proto if m["market"] != "OU" and m["analysis"]["pick_prob"] >= 0.55
         and (m["analysis"].get("x_odds") or m.get("odds") or {}).get(m["analysis"]["pick"], 9) < 1.9 and m["analysis"]["upset_risk"] >= 33],
        key=lambda m: -m["analysis"]["upset_risk"],
    )[:5]
    moves = []
    for m in analyzed:
        fl = m.get("flow") or {}
        o0 = fl.get("from") or m.get("odds_open") or {}
        o1 = m.get("odds_close") or m.get("odds") or {}
        for k in o1:
            if k in o0 and o0[k] and o1[k] != o0[k]:
                moves.append({"market_id": m["id"], "home": m["home"], "away": m["away"], "market": m["market"], "line": m.get("line"),
                              "kickoff": m["kickoff"], "outcome": k, "from": o0[k], "to": o1[k],
                              "chg": round(o1[k] / o0[k] - 1, 4), "n": fl.get("changes")})
    moves.sort(key=lambda x: x["chg"])
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
        "upsets": upsets,
        "handi_picks": handi_picks,
        "ou_picks": ou_picks,
        "top_pick": top,
        "top_picks": top_picks,
        "caution": [m["id"] for m in caution],
        "odds_moves": moves,
        "pending": sorted([x for x in betman.PENDING if x["kickoff"] > now.isoformat()], key=lambda x: x["kickoff"])[:60] if not config.DEMO else [],
        "stats": {
            "markets": len(analyzed),
            "matches": len({(m["home"], m["away"], m["kickoff"][:16]) for m in primary}),
            "upcoming": len({(m["home"], m["away"], m["kickoff"][:16]) for m in analyzed if m["preview"]}),
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
    from .sources import betman_history
    elo = G.rebuild_elo(reports, results_by_date, betman_history.load_all())
    G.save_state(perf, cal, elo, G.learn(reports))
    log.info("채점 완료: 픽 %s", perf["picks"]["all"])
    return perf


def history(max_rounds: int = 8) -> None:
    """과거 기록 백필 + 해외 배당 구도표 재계산. 실패해도 다른 단계에 영향 없음.

    베트맨 지난 회차는 채점·Elo용으로만 모은다. 배당 분석은 해외 기록(xbook)만 쓴다."""
    from .analysis import xbook
    from .sources import betman_history, us_history
    try:
        betman_history.backfill(max_rounds)
    except Exception:  # noqa: BLE001
        log.exception("백필 실패")
    from .sources import overseas_history
    try:
        overseas_history.backfill()
    except Exception:  # noqa: BLE001
        log.exception("해외 기록 수집 실패")
    from .sources import intl_history
    try:
        intl_history.backfill()
    except Exception:  # noqa: BLE001
        log.exception("국가대표 기록 수집 실패")
    try:
        us_history.backfill()
    except Exception:  # noqa: BLE001
        log.exception("NBA·MLB 기록 수집 실패")
    xrows = overseas_history.load_all()
    us = {lg: us_history.load(lg) for lg in us_history.LEAGUES}
    if xrows or any(us.values()):
        xbook.save(xbook.build(xrows, us))
        log.info("해외 배당 구도표 갱신: 축구 %d, NBA %d, MLB %d경기", len(xrows), len(us["nba"]), len(us["mlb"]))


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
