"""해외 농구·야구 과거 배당(NBA·MLB 2011~2021 시즌, 마감 머니라인·합계 기준점 + 실제 점수).

출처: sportsbookreviewsonline 아카이브를 정리한 공개 저장소(flancast90/sportsbookreview-scraper).
지난 기록이라 한 번만 받아 압축 저장한다. 파일이 있으면 다시 받지 않는다.

압축 행: [홈 공정확률, 홈 점수, 원정 점수, 마감 합계 기준점(없으면 0)]
- 머니라인을 소수 배당으로 바꾸고 마진을 비례 제거한 홈 승리 확률.
- 마진이 비정상(MARGIN 범위 밖)이거나 점수가 이상한 경기는 버린다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import config
from ..util import http

log = logging.getLogger("engine.us_history")
DIR = config.DATA / "history" / "us"
BASE = "https://raw.githubusercontent.com/flancast90/sportsbookreview-scraper/main/data/{lg}_archive_10Y.json"
LEAGUES = {"nba": "basketball", "mlb": "baseball"}
# 합계 기준점이 이 범위 밖이면 잘못 적힌 값(전반 합계 등)으로 보고 버린다
TOTAL_RANGE = {"nba": (150, 290), "mlb": (5, 15)}
SCORE_MAX = {"nba": 200, "mlb": 40}
# 양쪽 배당 역수 합(마진) 허용 범위. MLB 기록은 홈·원정 배당 시점이 어긋난 행이 많아 넓게 받는다(방향은 맞음: 확률 .4→실제 43%, .6→59%)
MARGIN = {"nba": (1.0, 1.15), "mlb": (0.95, 1.15)}


def american_to_decimal(ml) -> float:
    try:
        v = float(ml)
    except (TypeError, ValueError):
        return 0.0
    if v >= 100:
        return 1 + v / 100
    if v <= -100:
        return 1 + 100 / -v
    return 0.0  # -100 < v < 100 은 머니라인 표기가 아니다


def compact(rows: list[dict], lg: str) -> list[list]:
    out = []
    lo, hi = TOTAL_RANGE[lg]
    for r in rows:
        h, a = american_to_decimal(r.get("home_close_ml")), american_to_decimal(r.get("away_close_ml"))
        if h <= 1 or a <= 1:
            continue
        s = 1 / h + 1 / a
        if not (MARGIN[lg][0] <= s <= MARGIN[lg][1]):
            continue
        try:
            hs, as_ = int(float(r.get("home_final"))), int(float(r.get("away_final")))
        except (TypeError, ValueError):
            continue
        if hs == as_ or hs < 0 or as_ < 0 or hs > SCORE_MAX[lg] or as_ > SCORE_MAX[lg]:
            continue  # 동점은 이 두 종목에서 나올 수 없다 → 잘못된 기록
        try:
            t = float(r.get("close_over_under") or 0)
        except (TypeError, ValueError):
            t = 0.0
        if not (lo <= t <= hi):
            t = 0.0
        out.append([round((1 / h) / s, 4), hs, as_, t])
    return out


def _path(lg: str) -> Path:
    return DIR / f"{lg}.json"


def backfill() -> int:
    if config.DEMO:
        return 0
    DIR.mkdir(parents=True, exist_ok=True)
    done = 0
    for lg in LEAGUES:
        p = _path(lg)
        if p.exists() and p.stat().st_size > 1000:
            continue
        try:
            r = http("GET", BASE.format(lg=lg), retries=2, timeout=90)
            rows = compact(r.json(), lg)
            if len(rows) < 1000:
                raise ValueError(f"행이 너무 적음: {len(rows)}")
            p.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
            done += 1
            log.info("%s 과거 배당 %d경기 저장", lg.upper(), len(rows))
        except Exception as e:  # noqa: BLE001
            log.warning("%s 과거 배당 실패: %s", lg.upper(), type(e).__name__)
    return done


def load(lg: str) -> list[list]:
    p = _path(lg)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
