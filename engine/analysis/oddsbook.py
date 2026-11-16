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


# 배당 대 배당 구도용 구간: 3배까지 0.1, 6배까지 0.5, 10배까지 1 단위
BANDS = [round(1.0 + 0.1 * i, 1) for i in range(20)] + [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0, 9.0, 10.0]


def band(o: float) -> int:
    i = 0
    for j, b in enumerate(BANDS):
        if o + 1e-9 >= b:
            i = j
    return i


def band_label(i: int) -> str:
    lo = BANDS[i]
    if i == len(BANDS) - 1:
        return "10배 이상"
    w = round(BANDS[i + 1] - lo, 2)
    return f"{lo:.1f}배대" if w == 0.1 else f"{lo:g}~{BANDS[i + 1]:g}배"


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


def build_overseas(rows: list[list]) -> dict[str, dict]:
    """해외 평균 마감 배당 기준 구도표. X|홈밴드|원정밴드 → 승·무·패, XOU|오버밴드|언더밴드 → 오버 적중."""
    out: dict[str, dict] = {}
    for h, d, a, res, ov, un, goals in rows:
        pr = out.setdefault(f"X|{band(h)}|{band(a)}", {"n": 0, "h": 0, "d": 0, "a": 0})
        pr["n"] += 1
        pr["h" if res == 0 else "d" if res == 1 else "a"] += 1
        if ov > 1 and un > 1 and goals >= 0:
            po = out.setdefault(f"XOU|{band(ov)}|{band(un)}", {"n": 0, "over": 0})
            po["n"] += 1
            po["over"] += int(goals >= 3)
    return out


def build(rows: list[list], overseas: list[list] | None = None) -> dict[str, Any]:
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
            pk = f"{mk}|{band(lo_o)}|{band(hi_o)}"
            pr = pairs.setdefault(pk, {"n": 0, "hi": 0})
            pr["n"] += 1
            pr["hi"] += int(code == hi_side)
        elif mk == "1X2" and d and d > 1:
            pk = f"1X2|{band(w)}|{band(l)}"
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
                mband = "d3" if chg <= -0.10 else "d2" if chg <= -0.05 else "d1" if chg < -0.005 else "u1" if chg < 0.05 and chg > 0.005 else "u2" if chg >= 0.05 else "flat"
                mv = moves.setdefault(mband, {"n": 0, "hit": 0, "ret": 0.0, "inv": 0.0})
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
    return {"updated": config.now_kst().isoformat(timespec="seconds"), "rows": len(rows), "edges": EDGES, "table": table, "moves": mv_out, "pairs": pairs,
            "xpairs": build_overseas(overseas or []), "xrows": len(overseas or [])}


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


def _gather(table: dict, prefix: str, a: int, b: int, fields: tuple[str, ...], need: int = 25) -> dict | None:
    """표본이 모자라면 이웃 구간(±1, ±2)까지 합친다."""
    acc = {}
    for width in (0, 1, 2):
        acc = {"n": 0, **{f: 0 for f in fields}}
        for da in range(-width, width + 1):
            for db in range(-width, width + 1):
                pr = table.get(f"{prefix}|{a + da}|{b + db}")
                if pr:
                    acc["n"] += pr["n"]
                    for f in fields:
                        acc[f] += pr.get(f, 0)
        if acc["n"] >= need:
            acc["wide"] = width
            return acc
    return None


def pair_stat(book: dict, m: dict) -> dict | None:
    """이 경기와 같은 '배당 대 배당' 구도의 과거 결과.

    해외 배당이 있는 축구 승무패는 해외 기록(더 크고 정확한 시장)으로, 나머지는 베트맨 기록으로 본다.
    """
    book = book or {}
    odds = m.get("odds") or {}
    mk = m["market"]
    ref = m.get("ref_odds") or {}
    if mk == "1X2" and m.get("sport") == "soccer" and {"H", "A"} <= set(ref):
        acc = _gather(book.get("xpairs") or {}, "X", band(ref["H"]), band(ref["A"]), ("h", "d", "a"))
        if acc:
            n = acc["n"]
            return {"kind": "1X2", "src": "해외", "n": n, "H": round(acc["h"] / n, 4), "D": round(acc["d"] / n, 4), "A": round(acc["a"] / n, 4),
                    "ho": ref["H"], "ao": ref["A"]}
    pairs = book.get("pairs") or {}
    if mk == "1X2" and {"H", "D", "A"} <= set(odds):
        acc = _gather(pairs, "1X2", band(odds["H"]), band(odds["A"]), ("h", "d", "a"), 20)
        if not acc:
            return None
        n = acc["n"]
        return {"kind": "1X2", "src": "베트맨", "n": n, "H": round(acc["h"] / n, 4), "D": round(acc["d"] / n, 4), "A": round(acc["a"] / n, 4),
                "ho": odds["H"], "ao": odds["A"]}
    if mk in ("WL", "HANDICAP", "OU") and len(odds) == 2:
        (k1, o1), (k2, o2) = sorted(odds.items(), key=lambda kv: kv[1])
        acc = _gather(pairs, mk, band(o1), band(o2), ("hi",), 20)
        if not acc:
            return None
        n = acc["n"]
        return {"kind": "2way", "src": "베트맨", "n": n, "lo_key": k1, "hi_key": k2, "lo": o1, "hi": o2,
                "hi_rate": round(acc["hi"] / n, 4), "lo_rate": round(1 - acc["hi"] / n, 4)}
    return None
