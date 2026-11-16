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
EDGES = [round(1.0 + 0.1 * i, 1) for i in range(21)] + [3.5, 4.0, 5.0, 7.0, 10.0, 1000.0]  # 3.0배까지 0.1 단위
MIN_N = 30


def bucket(o: float) -> int:
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= o < EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def label(i: int) -> str:
    lo, hi = EDGES[i], EDGES[i + 1]
    if hi >= 100:
        return f"{lo:.0f}배 이상"
    if round(hi - lo, 2) == 0.1:
        return f"{lo:.1f}배대"
    return f"{lo:.1f}~{hi:.1f}배"


def _role(market: str, side: str) -> str:
    if side == "D":
        return "D"
    if market == "OU":
        return side  # O / U
    return "X"  # 승·패 쪽(정·역배는 배당 구간이 구분)


def build(rows: list[list]) -> dict[str, Any]:
    acc: dict[str, dict] = {}
    moves: dict[str, dict] = {}
    pairs: dict[str, dict] = {}

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
            add(f"side|{mk}|{side}|{b}", o, hit)          # 배당 분석 페이지용: 마켓×선택×구간
            add(f"sidesum|{mk}|{side}|0", o, hit)
        # 배당 대 배당 구도: 소수 첫째 자리 기준 (예: 1.5배 대 1.8배에서 1.8배 쪽이 이긴 비율)
        if mk in ("WL", "HANDICAP", "OU") and not (d and d > 1):
            lo_side, hi_side = (0, 2) if w <= l else (2, 0)
            lo_o, hi_o = min(w, l), max(w, l)
            pk = f"{mk}|{int(lo_o * 10 + 1e-6)}|{int(hi_o * 10 + 1e-6)}"
            pr = pairs.setdefault(pk, {"n": 0, "hi": 0})
            pr["n"] += 1
            pr["hi"] += int(code == hi_side)
        elif mk == "1X2" and d and d > 1:
            pk = f"1X2|{int(w * 10 + 1e-6)}|{int(l * 10 + 1e-6)}"
            pr = pairs.setdefault(pk, {"n": 0, "h": 0, "d": 0, "a": 0})
            pr["n"] += 1
            pr["h" if code == 0 else "d" if code == 1 else "a"] += 1
        # 배당 변동: 첫 발매 배당 대비
        if len(row) >= 17:
            opens = {0: row[14], 1: row[15], 2: row[16]}
            for side, o, c in sides:
                o0 = opens.get(c) or 0
                if not o or o <= 1 or not o0 or o0 <= 1:
                    continue
                chg = o / o0 - 1
                band = "d3" if chg <= -0.10 else "d2" if chg <= -0.05 else "d1" if chg < -0.005 else "u1" if chg < 0.05 and chg > 0.005 else "u2" if chg >= 0.05 else "flat"
                mv = moves.setdefault(band, {"n": 0, "hit": 0, "ret": 0.0, "inv": 0.0})
                mv["n"] += 1
                mv["hit"] += int(code == c)
                mv["ret"] += o if code == c else 0.0
                mv["inv"] += 1 / o
    table = {}
    for k, a in acc.items():
        n = a["n"]
        table[k] = {"n": n, "hit": round(a["hit"] / n, 4), "be": round(a["inv"] / n, 4), "roi": round(a["ret"] / n - 1, 4)}
    mv_out = {k: {"n": v["n"], "hit": round(v["hit"] / v["n"], 4), "be": round(v["inv"] / v["n"], 4), "roi": round(v["ret"] / v["n"] - 1, 4)}
              for k, v in moves.items() if v["n"]}
    return {"updated": config.now_kst().isoformat(timespec="seconds"), "rows": len(rows), "edges": EDGES, "table": table, "moves": mv_out, "pairs": pairs}


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
        if s["n"] < 150 or sport in ("all", "side", "sidesum"):
            continue
        out.append({"key": k, "sport": sport, "market": mk, "role": role, "bucket": label(int(b)), **s})
    out.sort(key=lambda x: -x["roi"])
    return out[:limit]


def pair_stat(book: dict, m: dict) -> dict | None:
    """이 경기와 같은 '배당 대 배당' 구도의 과거 결과. 표본이 20 미만이면 이웃(±0.1) 구간까지 합친다."""
    pairs = (book or {}).get("pairs") or {}
    odds = m.get("odds") or {}
    mk = m["market"]
    if mk == "1X2" and {"H", "D", "A"} <= set(odds):
        a, b = int(odds["H"] * 10 + 1e-6), int(odds["A"] * 10 + 1e-6)
        acc = {"n": 0, "h": 0, "d": 0, "a": 0}
        for width in (0, 1, 2):
            acc = {"n": 0, "h": 0, "d": 0, "a": 0}
            for da in range(-width, width + 1):
                for db in range(-width, width + 1):
                    pr = pairs.get(f"1X2|{a + da}|{b + db}")
                    if pr:
                        for k in acc:
                            acc[k] += pr.get(k, 0)
            if acc["n"] >= 20:
                break
        if acc["n"] < 20:
            return None
        n = acc["n"]
        return {"kind": "1X2", "n": n, "H": round(acc["h"] / n, 4), "D": round(acc["d"] / n, 4), "A": round(acc["a"] / n, 4),
                "ho": a / 10, "ao": b / 10}
    if mk in ("WL", "HANDICAP", "OU") and len(odds) == 2:
        (k1, o1), (k2, o2) = sorted(odds.items(), key=lambda kv: kv[1])
        a, b = int(o1 * 10 + 1e-6), int(o2 * 10 + 1e-6)
        n = hi = 0
        for width in (0, 1, 2):
            n = hi = 0
            for da in range(-width, width + 1):
                for db in range(-width, width + 1):
                    pr = pairs.get(f"{mk}|{a + da}|{b + db}")
                    if pr:
                        n += pr["n"]; hi += pr["hi"]
            if n >= 20:
                break
        if n < 20:
            return None
        return {"kind": "2way", "n": n, "lo_key": k1, "hi_key": k2, "lo": a / 10, "hi": b / 10, "hi_rate": round(hi / n, 4), "lo_rate": round(1 - hi / n, 4)}
    return None
