"""배당 구간별 실제 적중률(베트맨 과거 회차 기준).

'베트맨에서 1.30~1.44배였던 선택은 실제로 몇 % 맞았고, 그 배당에 꾸준히 걸었다면 수익률은?'
- 구간: 종목 × 마켓 × (정배/역배/무) × 배당 구간
- 표본이 적으면 상위 묶음(전 종목)으로 내려간다.
"""
from __future__ import annotations

from typing import Any

from .. import config
from ..util import read_json, write_json

PATH = config.STATE / "oddsbook.json"
EDGES = [1.0, 1.15, 1.3, 1.45, 1.6, 1.8, 2.0, 2.3, 2.7, 3.2, 4.0, 5.0, 7.0, 10.0, 1000.0]
MIN_N = 60


def bucket(o: float) -> int:
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= o < EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def label(i: int) -> str:
    lo, hi = EDGES[i], EDGES[i + 1]
    return f"{lo:.2f}~{hi:.2f}" if hi < 100 else f"{lo:.0f}배 이상"


def _role(market: str, side: str) -> str:
    if side == "D":
        return "D"
    if market == "OU":
        return side  # O / U
    return "X"  # 승·패 쪽(정·역배는 배당 구간이 구분)


def build(rows: list[list]) -> dict[str, Any]:
    acc: dict[str, dict] = {}

    def add(key, o, hit):
        a = acc.setdefault(key, {"n": 0, "hit": 0, "ret": 0.0, "inv": 0.0})
        a["n"] += 1
        a["hit"] += hit
        a["ret"] += o if hit else 0.0
        a["inv"] += 1 / o

    for row in rows:
        sport, _league, mk, _line, w, d, l, code, _ko, under_first = row[:10]
        if mk == "OU":
            sides = [("U" if under_first else "O", w, 0), ("O" if under_first else "U", l, 2)]
        else:
            sides = [("H", w, 0), ("A", l, 2)] + ([("D", d, 1)] if d and d > 1 else [])
        for side, o, c in sides:
            if not o or o <= 1:
                continue
            hit = int(code == c)
            b = bucket(o)
            role = _role(mk, side)
            add(f"{sport}|{mk}|{role}|{b}", o, hit)
            add(f"all|{mk}|{role}|{b}", o, hit)
            add(f"all|all|{'D' if side == 'D' else 'X'}|{b}", o, hit)
    table = {}
    for k, a in acc.items():
        n = a["n"]
        table[k] = {"n": n, "hit": round(a["hit"] / n, 4), "be": round(a["inv"] / n, 4), "roi": round(a["ret"] / n - 1, 4)}
    return {"updated": config.now_kst().isoformat(timespec="seconds"), "rows": len(rows), "edges": EDGES, "table": table}


def save(book: dict) -> None:
    write_json(PATH, book)


def load() -> dict:
    return read_json(PATH, {}) or {}


def lookup(book: dict, sport: str, market: str, side: str, odds: float) -> dict | None:
    t = (book or {}).get("table") or {}
    b = bucket(odds)
    role = _role(market, side)
    for key in (f"{sport}|{market}|{role}|{b}", f"all|{market}|{role}|{b}", f"all|all|{'D' if side == 'D' else 'X'}|{b}"):
        s = t.get(key)
        if s and s["n"] >= MIN_N:
            return {**s, "bucket": label(b), "scope": key.split("|")[0]}
    return None


def hist_probs(book: dict, m: dict) -> tuple[dict[str, float] | None, dict[str, dict]]:
    """각 선택의 '같은 배당 구간 과거 적중률'을 확률 분포로(표본 수로 내재확률 쪽에 수축)."""
    info: dict[str, dict] = {}
    raw: dict[str, float] = {}
    for k, o in (m.get("odds") or {}).items():
        s = lookup(book, m["sport"], m["market"], k, o)
        if not s:
            return None, info
        info[k] = s
        kk = 40  # 표본 40개 분량만큼 배당 내재확률 쪽으로 당김
        raw[k] = (s["hit"] * s["n"] + (1 / o) * kk) / (s["n"] + kk)
    t = sum(raw.values())
    if t <= 0:
        return None, info
    return {k: v / t for k, v in raw.items()}, info


def best_buckets(book: dict, limit: int = 6) -> list[dict]:
    """과거 수익률이 가장 좋았던 구간(표본 충분한 것만)."""
    t = (book or {}).get("table") or {}
    out = []
    for k, s in t.items():
        sport, mk, role, b = k.split("|")
        if s["n"] < 150 or sport == "all" and mk == "all":
            continue
        out.append({"key": k, "sport": sport, "market": mk, "role": role, "bucket": label(int(b)), **s})
    out.sort(key=lambda x: -x["roi"])
    return out[:limit]
