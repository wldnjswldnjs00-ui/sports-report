"""수동 입력. 자동 수집이 막혀도 리포트가 끊기지 않게 하는 안전장치.

data/manual/YYYY-MM-DD.csv (엑셀에서 그대로 저장 가능, UTF-8)

pool,game_no,sport,league,kickoff,home,away,market,line,H,D,A
proto,1,soccer,EPL,2026-11-16 21:00,맨체스C,리버풀,1X2,,1.85,3.40,3.60
proto,2,basketball,NBA,2026-11-17 09:30,보스턴,LA레이커,WL,,1.45,,2.40
proto,3,basketball,KBL,2026-11-16 19:00,서울SK,창원LG,HANDICAP,-3.5,1.75,,1.80
proto,4,basketball,NBA,2026-11-17 10:00,덴버,피닉스,OU,229.5,1.80,,1.80   (OU: H=오버, A=언더)

data/results/manual/YYYY-MM-DD.csv

game_no,home,away,home_score,away_score,status
1,맨체스C,리버풀,2,1,FT
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import config
from ..util import read_json

log = logging.getLogger("engine.manual")


def _f(v):
    v = (v or "").strip()
    return float(v) if v else None


def _kick(v: str) -> str:
    v = v.strip().replace(".", "-").replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=config.KST).isoformat(timespec="minutes")
        except ValueError:
            pass
    return datetime.fromisoformat(v).isoformat(timespec="minutes")


def load_markets(day: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    j = config.MANUAL / f"{day}.json"
    if j.exists():
        data = read_json(j, [])
        for i, m in enumerate(data if isinstance(data, list) else data.get("markets", [])):
            m.setdefault("id", f"manual:{day}:{i}")
            m["source"] = "manual"
            out.append(m)
    c = config.MANUAL / f"{day}.csv"
    if c.exists():
        with open(c, encoding="utf-8-sig", newline="") as f:
            for i, row in enumerate(csv.DictReader(f)):
                row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
                if not row.get("home"):
                    continue
                try:
                    mk = (row.get("market") or "1X2").upper()
                    h, d, a = _f(row.get("H")), _f(row.get("D")), _f(row.get("A"))
                    if mk == "OU":
                        odds = {"O": h, "U": a}
                    else:
                        odds = {"H": h, "A": a}
                        if d:
                            odds["D"] = d
                    no = row.get("game_no") or str(i + 1)
                    out.append({
                        "id": f"manual:{day}:{no}:{mk}",
                        "source": "manual", "pool": row.get("pool") or "proto", "round": row.get("round") or None,
                        "game_no": int(no) if no.isdigit() else None, "sport": row.get("sport") or "etc",
                        "league": row.get("league") or "기타", "kickoff": _kick(row["kickoff"]),
                        "home": row["home"], "away": row["away"], "market": mk,
                        "line": _f(row.get("line")), "odds": {k: v for k, v in odds.items() if v},
                    })
                except (ValueError, KeyError) as e:
                    log.warning("수동 입력 %d행 건너뜀: %s", i + 2, e)
    return out


def load_results(day: str) -> list[dict[str, Any]]:
    p = config.RESULTS / "manual" / f"{day}.csv"
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            if row.get("home") or row.get("game_no"):
                rows.append(row)
    return rows


def manual_dir_exists() -> bool:
    return Path(config.MANUAL).exists()
