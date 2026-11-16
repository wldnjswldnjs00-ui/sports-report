"""해외 배당 과거 기록 구도표. 베트맨 기록은 쓰지 않는다.

'해외 배당이 이렇게 붙었던 경기들은 실제로 어떻게 끝났나'를 점수 분포째로 저장한다.
분포를 저장하면 승무패·모든 핸디캡 기준점·모든 언더오버 기준점을 같은 표 하나로 답할 수 있다.

- 축구(유럽 16개 리그 6시즌)
    pair : 홈·원정 공정확률 구간(0.05×0.05) → [경기 수, 홈승, 무, 원정승, 득점차 표본 수, 득점차 -6..+6 분포]
    goals: 오버 2.5 공정확률 구간(0.025)   → [경기 수, 총 득점 0..10+ 분포]
- 농구(NBA)·야구(MLB) 2011~2021
    wl   : 홈 공정확률 구간(0.025) → [경기 수, 홈 점수차 -M..+M 분포]
    tot  : (실제 총점 − 마감 기준점) 분포, 0.5 단위 -R..+R
공정확률 = 배당 역수를 합이 1이 되게 나눈 값(발행처 마진 제거). 배당 그 자체 대신 확률로 묶어야
마진이 다른 시장끼리도 같은 칸을 가리킨다.
"""
from __future__ import annotations

from typing import Any

from .. import config
from ..util import read_json, write_json

PATH = config.STATE / "xbook.json"
SOC_W, GOAL_W, US_W = 0.05, 0.025, 0.025
DIFF_MAX, GOAL_MAX = 6, 10
US = {"basketball": {"key": "nba", "label": "NBA", "mmax": 45, "rmax": 60.0},
      "baseball": {"key": "mlb", "label": "MLB", "mmax": 15, "rmax": 15.0}}
NEED = 250  # 한 칸 표본이 이보다 적으면 이웃 칸까지 넓힌다
SOURCE_LABEL = {"soccer": "유럽 축구", "basketball": "NBA", "baseball": "MLB", "intl": "A매치"}


def _bin(p: float, w: float) -> int:
    return max(0, min(round(1 / w) - 1, int(p / w)))


def fair(*odds: float) -> list[float] | None:
    if not odds or any(not o or o <= 1 for o in odds):
        return None
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [v / s for v in inv]


# ───────────────────────── 구축 ─────────────────────────
def build(soccer_rows: list[list], us_rows: dict[str, list[list]]) -> dict[str, Any]:
    pair: dict[str, list[int]] = {}
    goals: dict[str, list[int]] = {}
    for r in soccer_rows:
        h, d, a, res, ov, un, g = r[:7]
        f = fair(h, d, a)
        if f:
            row = pair.setdefault(f"{_bin(f[0], SOC_W)}|{_bin(f[2], SOC_W)}", [0] * (5 + 2 * DIFF_MAX + 1))
            row[0] += 1
            row[1 + res] += 1
            if len(r) >= 9 and r[7] >= 0 and r[8] >= 0:
                row[4] += 1
                row[5 + DIFF_MAX + max(-DIFF_MAX, min(DIFF_MAX, r[7] - r[8]))] += 1
        fo = fair(ov, un) if ov and un else None
        if fo and g >= 0:
            row = goals.setdefault(str(_bin(fo[0], GOAL_W)), [0] * (GOAL_MAX + 2))
            row[0] += 1
            row[1 + min(g, GOAL_MAX)] += 1
    out: dict[str, Any] = {"updated": config.now_kst().isoformat(timespec="seconds"),
                           "soccer": {"n": len(soccer_rows), "pair": pair, "goals": goals}}
    for sport, meta in US.items():
        rows = us_rows.get(meta["key"]) or []
        M, R = meta["mmax"], meta["rmax"]
        wl: dict[str, list[int]] = {}
        tot = [0] * (int(R * 4) + 1)
        tn = 0
        for ph, hs, as_, line in rows:
            row = wl.setdefault(str(_bin(ph, US_W)), [0] * (2 * M + 2))
            row[0] += 1
            row[1 + M + max(-M, min(M, hs - as_))] += 1
            if line:
                rres = max(-R, min(R, round((hs + as_ - line) * 2) / 2))
                tot[int((rres + R) * 2)] += 1
                tn += 1
        out[sport] = {"n": len(rows), "label": meta["label"], "mmax": M, "rmax": R, "wl": wl, "tot": tot, "tn": tn}
    return out


def save(book: dict) -> None:
    write_json(PATH, book)


_CACHE: dict | None = None


def load() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = read_json(PATH, {}) or {}
    return _CACHE


# ───────────────────────── 조회 ─────────────────────────
def _gather(table: dict, keys_at, need: int = NEED, max_r: int = 3) -> tuple[list[int] | None, int]:
    """가운데 칸에서 시작해 표본이 need 이상 될 때까지 반경을 넓혀 합친다."""
    for r in range(max_r + 1):
        acc: list[int] | None = None
        for k in keys_at(r):
            row = table.get(k)
            if not row:
                continue
            acc = list(row) if acc is None else [x + y for x, y in zip(acc, row)]
        if acc and acc[0] >= need:
            return acc, r
    return (acc if acc and acc[0] >= need // 3 else None), max_r


def soccer_pair(book: dict, ph: float, pa: float) -> dict | None:
    t = ((book or {}).get("soccer") or {}).get("pair") or {}
    i, j = _bin(ph, SOC_W), _bin(pa, SOC_W)
    acc, _ = _gather(t, lambda r: [f"{i + a}|{j + b}" for a in range(-r, r + 1) for b in range(-r, r + 1)])
    if not acc:
        return None
    n = acc[0]
    return {"n": n, "H": acc[1] / n, "D": acc[2] / n, "A": acc[3] / n,
            "dn": acc[4], "diff": acc[5:] if acc[4] >= 100 else None}


def soccer_handicap(sp: dict, line: float, keys: set[str]) -> dict | None:
    """홈 득점차 + line 이 양수면 H, 0이면 D, 음수면 A. 2지 핸디캡이면 동률(적중특례)을 빼고 나눈다."""
    diff = sp.get("diff")
    if not diff:
        return None
    o = {"H": 0, "D": 0, "A": 0}
    for idx, c in enumerate(diff):
        v = idx - DIFF_MAX + line
        o["H" if v > 0 else "D" if v == 0 else "A"] += c
    if "D" not in keys:
        t = o["H"] + o["A"]
        return {"H": o["H"] / t, "A": o["A"] / t} if t else None
    t = sum(o.values())
    return {k: v / t for k, v in o.items()} if t else None


def soccer_goals(book: dict, p_over25: float) -> list[int] | None:
    t = ((book or {}).get("soccer") or {}).get("goals") or {}
    i = _bin(p_over25, GOAL_W)
    acc, _ = _gather(t, lambda r: [str(i + a) for a in range(-r, r + 1)])
    return acc


def over_rate(hist: list[int], line: float) -> float | None:
    """총 득점 분포에서 line 초과 비율. 정수 기준점은 같은 값(적중특례)을 빼고 계산."""
    n = hist[0]
    if not n:
        return None
    over = sum(c for g, c in enumerate(hist[1:]) if g > line)
    push = sum(c for g, c in enumerate(hist[1:]) if g == line)
    return over / (n - push) if n - push else None


def soccer_goals_for(book: dict, line_x: float, p_over_x: float) -> list[int] | None:
    """해외 합계 기준점이 2.5가 아닐 때: 그 기준점에서의 오버 확률이 가장 비슷한 2.5 구간을 찾는다."""
    if abs(line_x - 2.5) < 1e-9:
        return soccer_goals(book, p_over_x)
    t = ((book or {}).get("soccer") or {}).get("goals") or {}
    best, arg = 9.0, None
    for k, row in t.items():
        if row[0] < 100:
            continue
        r = over_rate(row, line_x)
        if r is not None and abs(r - p_over_x) < best:
            best, arg = abs(r - p_over_x), float(k) * GOAL_W + GOAL_W / 2
    return soccer_goals(book, arg) if arg is not None and best < 0.05 else None


def us_margin(book: dict, sport: str, ph: float) -> list[int] | None:
    t = ((book or {}).get(sport) or {}).get("wl") or {}
    i = _bin(ph, US_W)
    acc, _ = _gather(t, lambda r: [str(i + a) for a in range(-r, r + 1)])
    return acc


def us_cover(hist: list[int], M: int, line: float) -> tuple[float, float] | None:
    """(홈 점수차 + line > 0 비율, 동률 비율)."""
    n = hist[0]
    if not n:
        return None
    win = sum(c for idx, c in enumerate(hist[1:]) if idx - M + line > 0)
    push = sum(c for idx, c in enumerate(hist[1:]) if idx - M + line == 0)
    return win / n, push / n


def _quantile(tot: list[int], R: float, q: float) -> float:
    n = sum(tot)
    acc = 0
    for idx, c in enumerate(tot):
        acc += c
        if acc >= q * n:
            return idx / 2 - R
    return R


def us_over(book: dict, sport: str, line_x: float, p_over_x: float, line: float) -> float | None:
    """해외 합계 기준점 line_x 의 오버 확률이 p_over_x 일 때, 기준점 line 에서의 오버 확률.

    (실제 총점 − 마감 기준점) 의 실제 분포를 해외 확률에 맞게 옮긴 뒤 line 에서 잘라 본다."""
    b = (book or {}).get(sport) or {}
    tot, R = b.get("tot"), b.get("rmax")
    if not tot or not sum(tot):
        return None
    # 총점 = line_x + δ + e (e 는 실제 분포). P(총점 > line_x) = p 가 되려면 δ = −Q(1−p).
    # 그러면 P(총점 > line) = P(e > line − line_x + Q(1−p)).
    cut = line - line_x + _quantile(tot, R, min(max(1 - p_over_x, 0.01), 0.99))
    n = sum(tot)
    over = sum(c for idx, c in enumerate(tot) if idx / 2 - R > cut)
    push = sum(c for idx, c in enumerate(tot) if idx / 2 - R == cut)
    return over / (n - push) if n - push else None


# ───────────────────────── 경기 분석용 ─────────────────────────
def market_stat(book: dict, m: dict) -> dict | None:
    """이 경기의 해외 배당과 비슷했던 과거 경기들이 이 마켓에서 실제로 어떻게 끝났는지.

    반환: {"src": 출처, "n": 표본, "p": {선택: 실제 비율}, "basis": 화면 문장용 설명}
    해외 배당(m['x'])이 없으면 None — 베트맨 기록으로 대신하지 않는다."""
    x = m.get("x") or {}
    keys = set(m.get("odds") or {})
    sport, mk, line = m.get("sport"), m.get("market"), m.get("line")
    h2h = x.get("h2h") or {}
    if not keys or not x:
        return None
    if sport == "soccer":
        if mk in ("1X2", "WL", "HANDICAP") and {"H", "D", "A"} <= set(h2h):
            sp = soccer_pair(book, h2h["H"], h2h["A"])
            if not sp:
                return None
            basis = f"해외 승무패 확률 {h2h['H'] * 100:.0f}·{h2h['D'] * 100:.0f}·{h2h['A'] * 100:.0f}%와 비슷한"
            if mk == "1X2" and keys == {"H", "D", "A"}:
                return {"src": "유럽 축구", "n": sp["n"], "p": {k: round(sp[k], 4) for k in "HDA"}, "basis": basis}
            if mk == "WL" and keys == {"H", "A"}:
                t = sp["H"] + sp["A"]
                return {"src": "유럽 축구", "n": sp["n"], "p": {"H": round(sp["H"] / t, 4), "A": round(sp["A"] / t, 4)}, "basis": basis}
            if mk == "HANDICAP" and line is not None:
                p = soccer_handicap(sp, float(line), keys)
                if p and set(p) == keys:
                    return {"src": "유럽 축구", "n": sp["dn"], "p": {k: round(v, 4) for k, v in p.items()}, "basis": basis}
            return None
        if mk == "OU" and x.get("total") and line is not None and keys == {"O", "U"}:
            lx, px = x["total"]
            hist = soccer_goals_for(book, float(lx), float(px))
            r = over_rate(hist, float(line)) if hist else None
            if r is None:
                return None
            return {"src": "유럽 축구", "n": hist[0], "p": {"O": round(r, 4), "U": round(1 - r, 4)},
                    "basis": f"해외 합계 {lx:g} 오버 확률 {px * 100:.0f}%와 비슷한"}
        return None
    if sport in US:
        meta = US[sport]
        if mk in ("WL", "HANDICAP") and {"H", "A"} <= set(h2h) and keys == {"H", "A"}:
            ph = h2h["H"] / (h2h["H"] + h2h["A"])
            hist = us_margin(book, sport, ph)
            if not hist:
                return None
            M = (book.get(sport) or {}).get("mmax", meta["mmax"])
            cv = us_cover(hist, M, float(line or 0) if mk == "HANDICAP" else 0.0)
            if not cv:
                return None
            win, push = cv
            pw = win / (1 - push) if push < 1 else 0.5
            return {"src": meta["label"], "n": hist[0], "p": {"H": round(pw, 4), "A": round(1 - pw, 4)},
                    "basis": f"해외 승패 확률 {ph * 100:.0f}% 대 {(1 - ph) * 100:.0f}%와 비슷한"}
        if mk == "OU" and x.get("total") and line is not None and keys == {"O", "U"}:
            lx, px = x["total"]
            r = us_over(book, sport, float(lx), float(px), float(line))
            if r is None:
                return None
            n = (book.get(sport) or {}).get("tn", 0)
            return {"src": meta["label"], "n": n, "p": {"O": round(r, 4), "U": round(1 - r, 4)},
                    "basis": f"해외 합계 {lx:g} 오버 확률 {px * 100:.0f}%를 기준점 {line:g}로 옮긴"}
    return None


def is_x(h: dict | None) -> bool:
    """해외 기록으로 만든 값인지(예전 리포트에 남은 베트맨 기록 값은 거른다)."""
    return bool(h) and h.get("bucket") in SOURCE_LABEL.values()


def x_hist(a: dict | None) -> dict:
    return {k: v for k, v in ((a or {}).get("hist") or {}).items() if is_x(v)}


def x_pair(a: dict | None) -> dict | None:
    pr = (a or {}).get("pair")
    return pr if pr and pr.get("p") and pr.get("basis") else None


def hist_for(stat: dict | None, odds: dict[str, float]) -> dict[str, dict] | None:
    """화면·조합용: 선택별 '해외 기록 적중률'과 그 비율로 베트맨 배당을 샀을 때의 수익률."""
    if not stat:
        return None
    out = {}
    for k, o in (odds or {}).items():
        r = stat["p"].get(k)
        if r is None or not o:
            continue
        out[k] = {"hit": r, "n": stat["n"], "roi": round(r * o - 1, 4), "bucket": stat["src"]}
    return out or None


# ───────────────────────── 배당 분석 페이지용 ─────────────────────────
def page_payload(book: dict) -> dict:
    """브라우저 계산기에 넘길 최소 데이터(표본이 너무 적은 칸은 뺀다)."""
    if not book:
        return {}
    s = book.get("soccer") or {}
    out = {"soc": {"n": s.get("n", 0), "w": SOC_W, "gw": GOAL_W, "dm": DIFF_MAX,
                   "pair": {k: v for k, v in (s.get("pair") or {}).items() if v[0] >= 5},
                   "goals": {k: v for k, v in (s.get("goals") or {}).items() if v[0] >= 5}}}
    for sport in US:
        b = book.get(sport) or {}
        if not b.get("n"):
            continue
        out[sport] = {"n": b["n"], "label": b["label"], "w": US_W, "m": b["mmax"], "r": b["rmax"], "tn": b.get("tn", 0),
                      "wl": {k: v for k, v in b["wl"].items() if v[0] >= 5}, "tot": b["tot"]}
    return out
