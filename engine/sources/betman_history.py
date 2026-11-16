"""베트맨 지난 회차 백필: 배당과 공식 결과를 모아 '배당 구간별 실제 적중률'을 만든다.

- 자동 실행마다 아직 없는 과거 회차를 몇 개씩만 가져온다(서버 부담 최소화).
- 회차당 한 파일(data/history/proto/<회차>.json), 필요한 필드만 압축 저장.
- 진행 중인 회차는 저장하지 않는다(결과가 다 나온 회차만).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .. import config
from . import betman

log = logging.getLogger("engine.history")
DIR = config.DATA / "history" / "proto2"  # v2: 팀명·실제 점수 포함
OLDEST = 250001  # 2025년 1회차까지


def _path(ts: int) -> Path:
    return DIR / f"{ts}.json"


def compact_rows(doc: dict) -> list[list]:
    """[종목, 리그, 마켓, 기준점, 왼칸배당, 무배당, 오른칸배당, 결과칸(0/1/2), 킥오프ms, 왼칸이언더인지, 홈, 원정, 홈점수, 원정점수]

    점수는 승패·승무패 행에서만 실제 점수다(핸디캡은 핸디 적용, 언더오버는 합계라 None)."""
    out = []
    for r in betman._rows(doc):
        mk = betman._market(r)
        code = str(r.get("gameResult") if r.get("gameResult") is not None else "").strip()
        if not mk or code not in ("0", "1", "2") or str(r.get("gameReject") or "0") != "0":
            continue
        w, d, l = betman._num(r.get("winAllot")), betman._num(r.get("drawAllot")), betman._num(r.get("loseAllot"))
        if w <= 1 or l <= 1:
            continue
        if mk == "1X2" and d <= 1:
            mk = "WL"
        line = r.get("winHandi") if isinstance(r.get("winHandi"), (int, float)) else 0
        under_first = 1 if mk == "OU" and not str(r.get("winTxt") or "언더").startswith("오버") else 0
        hs = as_ = None
        if mk in ("1X2", "WL"):
            sc = betman._SCORE.search(str(r.get("mchScore") or ""))
            if sc:
                hs, as_ = float(sc.group(1)), float(sc.group(2))
        out.append([betman._sport(r), str(r.get("leagueName") or ""), mk, line, w, d if d > 1 else 0, l, int(code),
                    r.get("gameDate"), under_first, str(r.get("homeName") or "").strip(), str(r.get("awayName") or "").strip(), hs, as_])
    return out


def _fetch_round(ts: int) -> dict | None:
    year = "20" + str(ts)[:2]
    slip = f"{betman.BASE}/main/mainPage/gamebuy/gameSlip.do?gmId={betman.GM_ID}&year={year}&gmTs={ts}"
    ajax = {"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01", "Origin": betman.BASE, "Referer": slip}
    r = betman.http("POST", betman.GAME_URL, json={"gmId": betman.GM_ID, "gmTs": ts, "gameYear": year,
                                                   "_sbmInfo": {"debugMode": "false"}}, headers=ajax, retries=2)
    return betman._json(r)


def current_round() -> int | None:
    """가장 최근 리포트에 등장한 회차 중 가장 작은 값(진행 중) — 그보다 작은 회차만 백필."""
    rounds = []
    for p in sorted(config.REPORTS.glob("*.json"))[-3:]:
        try:
            rep = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rounds += [int(m["round"]) for m in rep.get("markets", []) if str(m.get("round") or "").isdigit()]
    return min(rounds) if rounds else None


def backfill(max_rounds: int = 8) -> int:
    cur = current_round()
    if not cur or config.DEMO:
        return 0
    DIR.mkdir(parents=True, exist_ok=True)
    done = 0
    misses = 0
    try:
        betman.http("GET", betman.BASE + "/", retries=2)
    except Exception as e:  # noqa: BLE001
        log.warning("백필 접속 실패: %s", e)
        return 0
    # 최근 회차는 결과가 늦게 채워질 수 있어 다시 받는다
    for recent in range(cur - 4, cur):
        if _path(recent).exists():
            _path(recent).unlink()
    ts = cur - 1
    while ts >= OLDEST and done < max_rounds:
        # 연도 경계: 260001 아래는 2025년 마지막 회차로 건너뛴다
        if ts % 10000 == 0:
            ts = (ts // 10000 - 1) * 10000 + 9999
            continue
        if _path(ts).exists():
            ts -= 1
            continue
        try:
            time.sleep(2.0)
            doc = _fetch_round(ts)
            rows = compact_rows(doc) if doc else []
            cs = (doc or {}).get("compSchedules") or {}
            if not cs.get("datas"):
                misses += 1
                # 연말 존재하지 않는 회차 번호는 빈 파일로 표시만 하고 넘어간다
                _path(ts).write_text("[]", encoding="utf-8")
                if misses > 30:
                    break
            else:
                _path(ts).write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                done += 1
        except Exception as e:  # noqa: BLE001
            log.warning("백필 %s 실패: %s", ts, e)
            break
        ts -= 1
    log.info("과거 회차 백필 %d개 (기준 %s)", done, cur)
    return done


def load_all() -> list[list]:
    rows = []
    if not DIR.exists():
        return rows
    for p in DIR.glob("*.json"):
        try:
            rows += json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return rows
