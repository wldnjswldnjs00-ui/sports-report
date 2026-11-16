"""해외 배당 과거 기록(football-data.co.uk 공개 CSV, 유럽 축구 리그).

경기별 해외 평균 마감 배당(승·무·패, 2.5 오버·언더)과 실제 결과를 모은다.
- 지난 시즌 파일은 한 번만 받는다. 이번 시즌 파일은 3일마다 새로 받는다.
- 실행 한 번에 최대 20개 파일(서버 부담 최소화).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import time
from pathlib import Path

from .. import config
from ..util import http

log = logging.getLogger("engine.overseas")
DIR = config.DATA / "history" / "overseas"
LEAGUES = ["E0", "E1", "SP1", "SP2", "I1", "I2", "D1", "D2", "F1", "F2", "N1", "P1", "B1", "T1", "SC0", "G1"]
URL = "https://www.football-data.co.uk/mmz4281/{season}/{lg}.csv"


def _seasons(n: int = 6) -> list[str]:
    now = config.now_kst()
    start = now.year if now.month >= 7 else now.year - 1
    return [f"{(start - i) % 100:02d}{(start - i + 1) % 100:02d}" for i in range(n)]


def _f(row: dict, *keys: str) -> float:
    for k in keys:
        try:
            v = float(row.get(k) or 0)
            if v > 1:
                return v
        except ValueError:
            continue
    return 0.0


def parse_csv(text: str) -> list[list]:
    """[홈배당, 무배당, 원정배당, 결과(0홈/1무/2원정), 오버2.5배당, 언더2.5배당, 총득점, 홈득점, 원정득점]"""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        res = {"H": 0, "D": 1, "A": 2}.get((row.get("FTR") or "").strip())
        h = _f(row, "AvgCH", "PSCH", "AvgH", "PSH", "B365H")
        d = _f(row, "AvgCD", "PSCD", "AvgD", "PSD", "B365D")
        a = _f(row, "AvgCA", "PSCA", "AvgA", "PSA", "B365A")
        if res is None or not (h and d and a):
            continue
        try:
            goals = int(float(row.get("FTHG") or 0)) + int(float(row.get("FTAG") or 0))
        except ValueError:
            goals = -1
        try:
            hg, ag = int(float(row.get("FTHG"))), int(float(row.get("FTAG")))
        except (TypeError, ValueError):
            hg = ag = -1
        out.append([h, d, a, res, _f(row, "AvgC>2.5", "PC>2.5", "Avg>2.5", "P>2.5", "B365>2.5"),
                    _f(row, "AvgC<2.5", "PC<2.5", "Avg<2.5", "P<2.5", "B365<2.5"), goals, hg, ag])
    return out


def _path(season: str, lg: str) -> Path:
    return DIR / f"{season}_{lg}.json"


def _old_format(p: Path) -> bool:
    """홈·원정 득점이 없는 예전 형식(7칸) 파일이면 다시 받는다(핸디캡 분석에 득점 차가 필요)."""
    try:
        head = p.read_text(encoding="utf-8")[:400]
        if head.strip() == "[]":
            return False
        rows = json.loads(p.read_text(encoding="utf-8"))
        return bool(rows) and len(rows[0]) < 9
    except (OSError, json.JSONDecodeError):
        return True


def backfill(max_files: int = 20) -> int:
    if config.DEMO:
        return 0
    DIR.mkdir(parents=True, exist_ok=True)
    seasons = _seasons()
    done = 0
    from ..util import read_json, write_json
    stamp_path = config.STATE / "overseas_fetch.json"
    stamps = read_json(stamp_path, {}) or {}
    today = config.today_kst()

    def fresh(name: str) -> bool:
        from datetime import date
        d = stamps.get(name)
        return bool(d) and (date.fromisoformat(today) - date.fromisoformat(d)).days < 3

    for si, season in enumerate(seasons):
        for lg in LEAGUES:
            p = _path(season, lg)
            if p.exists() and (si > 0 or fresh(p.name)) and not _old_format(p):
                continue
            if done >= max_files:
                write_json(stamp_path, stamps)
                return done
            try:
                time.sleep(1.0)
                r = http("GET", URL.format(season=season, lg=lg), retries=2)
                rows = parse_csv(r.content.decode("utf-8-sig", "replace"))
                p.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
                stamps[p.name] = today
                done += 1
            except Exception as e:  # noqa: BLE001
                log.warning("해외 기록 %s %s 실패: %s", season, lg, type(e).__name__)
                if not p.exists():
                    p.write_text("[]", encoding="utf-8")  # 없는 리그·시즌은 다시 시도하지 않는다
    write_json(stamp_path, stamps)
    log.info("해외 배당 기록 %d개 파일 갱신", done)
    return done


def load_all() -> list[list]:
    rows: list[list] = []
    if not DIR.exists():
        return rows
    for p in DIR.glob("*.json"):
        try:
            rows += json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return rows
