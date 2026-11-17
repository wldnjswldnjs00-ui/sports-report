"""'숫자가 말하는 것': 배당이 아닌 경기 내용(점수)으로 두 팀을 비교하고, 눈에 띄는 것만 문장으로 쓴다.

모두 매 실행 때 점수 기록으로 다시 계산된다(사람 손 없음). 표본이 적으면 문장을 쓰지 않는다.
- 득실 기준 기대 승률(피타고라스): 득점·실점으로 본 '원래 이겼어야 할' 비율 → 실제와 차이가 크면 운
- 접전 성적: 근소한 차이 경기의 승패 → 한쪽으로 크게 치우치면 운
- 흐름: 최근 5경기 평균 득실 vs 최근 20경기 평균
- 기복: 득실 편차(핸디 기준점이 클 때 중요)
- 휴식: 경기 전 쉰 날 수, 연전
- 득점 합계: 두 팀 최근 평균 합계 vs 언더오버 기준점
"""
from __future__ import annotations

import math
from datetime import date

# 종목별 기준값
EXP = {"basketball": 14.0, "baseball": 1.83, "soccer": 1.35, "volleyball": 2.5}   # 피타고라스 지수
CLOSE = {"basketball": 5, "baseball": 1, "soccer": 1, "volleyball": 1}              # 접전: 점수(세트) 차 이하
FORM = {"basketball": 6.0, "baseball": 1.5, "soccer": 0.7, "volleyball": 0.8}        # 흐름 변화로 볼 득실 차
VOL = {"basketball": 14.0, "baseball": 4.5, "soccer": 2.3, "volleyball": 1.6}        # 기복이 큰 편으로 볼 편차
TOT = {"basketball": 6.0, "baseball": 1.2, "soccer": 0.5, "volleyball": 0.0}         # 합계가 기준점과 차이 날 때
UNIT = {"basketball": "점", "baseball": "점", "soccer": "골", "volleyball": "세트"}
MIN_N = 8


def _batchim(w: str) -> bool | None:
    """마지막 글자에 받침이 있는지. 숫자·영문은 읽는 소리로."""
    w = str(w).strip()
    if not w:
        return None
    c = w[-1]
    if "가" <= c <= "힣":
        return (ord(c) - 0xAC00) % 28 != 0
    if c.isdigit():
        return c in "013678"
    return c.lower() in "lmnr" if c.isalpha() else None


def j(w: str, pair: str) -> str:
    """조사 붙이기: j('LG', '은는') → 'LG는'. pair = 받침 있을 때/없을 때."""
    b = _batchim(w)
    if pair == "으로":
        c = str(w)[-1:]
        last_l = ("가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 == 8) or c in "178"
        return f"{w}{'로' if b is False or last_l or b is None else '으로'}"
    return f"{w}{pair[0] if b else pair[1]}"


def _avg(xs):
    return sum(xs) / len(xs) if xs else None


def metrics(t: dict, sport: str, kickoff: str) -> dict | None:
    gs = [x for x in (t or {}).get("games") or [] if x["date"] < kickoff[:10]][:20]
    if len(gs) < MIN_N:
        return None
    me = [x["me"] for x in gs]
    op = [x["op"] for x in gs]
    marg = [a - b for a, b in zip(me, op)]
    w = sum(1 for x in gs if x["res"] == "W")
    l = sum(1 for x in gs if x["res"] == "L")
    dec = w + l or 1
    k = EXP.get(sport, 2.0)
    sf, sa = sum(me), sum(op)
    pyth = (sf ** k) / (sf ** k + sa ** k) if sf + sa > 0 and sf > 0 and sa > 0 else None
    close = [x for x in gs if abs(x["me"] - x["op"]) <= CLOSE.get(sport, 1) and x["me"] != x["op"]]
    cw = sum(1 for x in close if x["res"] == "W")
    mean = _avg(marg)
    sd = math.sqrt(sum((m - mean) ** 2 for m in marg) / len(marg)) if len(marg) > 1 else 0.0
    last = gs[0]["date"]
    try:
        rest = (date.fromisoformat(kickoff[:10]) - date.fromisoformat(last)).days - 1
    except ValueError:
        rest = None
    return {
        "n": len(gs), "w": w, "l": l, "d": len(gs) - w - l, "wp": w / dec, "pyth": pyth,
        "close_w": cw, "close_l": len(close) - cw,
        "m5": _avg(marg[:5]), "m20": mean, "sd": sd,
        "for": _avg(me), "against": _avg(op), "total": _avg([a + b for a, b in zip(me, op)]),
        "rest": rest,
    }


def _main_line(g: dict, mk: str):
    """같은 종류 기준점이 여러 개면 양쪽 배당이 가장 비슷한(=기준이 되는) 것."""
    c = [m for m in g.get("markets") or [] if m.get("market") == mk and m.get("line") is not None and m.get("odds")]
    def gap(m):
        o = m["odds"]
        a, b = (o.get("O"), o.get("U")) if mk == "OU" else (o.get("H"), o.get("A"))
        return abs(a - b) if a and b else 99
    return min(c, key=gap) if c else None


def _ago(v: int) -> str:
    return "어제(연전)" if v == 0 else f"{v + 1}일 전"


def _f(x, d=1):
    return f"{x:+.{d}f}"


def build(g: dict, th: dict | None, ta: dict | None) -> dict | None:
    sp = g["sport"]
    mh = metrics(th, sp, g["kickoff"]) if th else None
    ma = metrics(ta, sp, g["kickoff"]) if ta else None
    if not mh and not ma:
        return None
    u = UNIT.get(sp, "점")
    notes: list[tuple[int, str, str]] = []   # (중요도, 종류, 문장)
    for name, m in ((g["home"], mh), (g["away"], ma)):
        if not m:
            continue
        # 운: 실제 승률 vs 득실 기준 기대 승률
        if m["pyth"] is not None and sp != "soccer":
            gap = m["wp"] - m["pyth"]
            exp_w = round(m["pyth"] * (m["w"] + m["l"]))
            if gap >= 0.10:
                notes.append((3, "운", f"{j(name, "은는")} 최근 {m['n']}경기 {m['w']}승 {m['l']}패지만 득실로 보면 {exp_w}승 수준입니다. 운이 따른 쪽이라 지금 성적보다 약할 수 있습니다."))
            elif gap <= -0.10:
                notes.append((3, "운", f"{j(name, "은는")} 최근 {m['n']}경기 {m['w']}승 {m['l']}패지만 득실로 보면 {exp_w}승 수준입니다. 경기 내용에 비해 덜 이긴 팀이라 지금 성적보다 강할 수 있습니다."))
        # 접전
        cn = m["close_w"] + m["close_l"]
        if cn >= 4 and (m["close_w"] / cn >= 0.8 or m["close_w"] / cn <= 0.2):
            lucky = m["close_w"] > m["close_l"]
            notes.append((2, "접전", f"{j(name, "은는")} 근소한 차이 경기에서 {m['close_w']}승 {m['close_l']}패로 {'유난히 강했습니다. 접전 승률은 오래 유지되기 어렵습니다' if lucky else '유난히 약했습니다. 내용보다 결과가 나빴던 편입니다'}."))
        # 흐름
        if m["m5"] is not None and m["m20"] is not None:
            dlt = m["m5"] - m["m20"]
            if dlt >= FORM.get(sp, 1):
                notes.append((2, "흐름", f"{j(name, "은는")} 최근 5경기 평균 득실이 {j(_f(m['m5']) + u, '으로')}, {m['n']}경기 평균({_f(m['m20'])}{u})보다 좋아졌습니다. 상승세입니다."))
            elif dlt <= -FORM.get(sp, 1):
                notes.append((2, "흐름", f"{j(name, "은는")} 최근 5경기 평균 득실이 {j(_f(m['m5']) + u, '으로')}, {m['n']}경기 평균({_f(m['m20'])}{u})보다 나빠졌습니다. 하락세입니다."))
    # 휴식
    if mh and ma and mh["rest"] is not None and ma["rest"] is not None and sp in ("basketball", "volleyball"):
        rh, ra = mh["rest"], ma["rest"]
        if (rh == 0) != (ra == 0):
            tired = g["home"] if rh == 0 else g["away"]
            notes.append((2, "연전", f"{j(tired, "은는")} 어제도 경기를 치르고 연속으로 나옵니다. 체력 면에서 불리합니다."))
    # 합계 vs 언더오버 기준점
    ou = _main_line(g, "OU")
    if ou and mh and ma and TOT.get(sp):
        exp_total = (mh["for"] + ma["against"] + ma["for"] + mh["against"]) / 2
        gap = exp_total - ou["line"]
        if abs(gap) >= TOT[sp]:
            notes.append((2, "합계", f"두 팀 최근 득실로 본 예상 합계는 {j(f'{exp_total:.1f}{u}', '으로')}, 기준점 {ou['line']:g}보다 {'높습니다(오버 쪽 근거)' if gap > 0 else '낮습니다(언더 쪽 근거)'}."))
    # 기복 + 큰 핸디
    hc = _main_line(g, "HANDICAP")
    if hc and abs(hc["line"]) >= {"basketball": 7, "baseball": 2, "soccer": 2, "volleyball": 2}.get(sp, 99):
        fav, mf = (g["home"], mh) if hc["line"] < 0 else (g["away"], ma)
        if mf and mf["sd"] >= VOL.get(sp, 99):
            notes.append((1, "기복", f"{j(fav, "은는")} 경기마다 득실 편차가 {j(f"{mf['sd']:.1f}{u}", '으로')} 기복이 큰 편입니다. 핸디 {hc['line']:+g}처럼 큰 기준점에서는 변수가 큽니다."))
    notes.sort(key=lambda x: -x[0])
    top = notes[:3]
    lines = [s for _, _, s in top]
    items = [(k, s) for _, k, s in top]
    if not lines:
        lines = ["두 팀 경기 내용 지표에 눈에 띄는 차이는 없습니다."]

    def cell(m, key, fmt):
        return fmt(m[key]) if m and m.get(key) is not None else "–"

    rows = [
        ("최근 성적", cell(mh, "n", lambda _: f"{mh['w']}승 {mh['l']}패"), cell(ma, "n", lambda _: f"{ma['w']}승 {ma['l']}패")),
    ]
    if sp != "soccer":
        rows.append(("득실 기준", cell(mh, "pyth", lambda v: f"{round(v * (mh['w'] + mh['l']))}승 (실제 {mh['w']}승)"), cell(ma, "pyth", lambda v: f"{round(v * (ma['w'] + ma['l']))}승 (실제 {ma['w']}승)")))
    rows += [
        ("접전", cell(mh, "n", lambda _: f"{mh['close_w']}승 {mh['close_l']}패"), cell(ma, "n", lambda _: f"{ma['close_w']}승 {ma['close_l']}패")),
        ("최근 5 득실", cell(mh, "m5", lambda v: f"{_f(v)}"), cell(ma, "m5", lambda v: f"{_f(v)}")),
        ("평균 득실", cell(mh, "m20", lambda v: f"{_f(v)}"), cell(ma, "m20", lambda v: f"{_f(v)}")),
        ("평균 합계", cell(mh, "total", lambda v: f"{v:.1f}"), cell(ma, "total", lambda v: f"{v:.1f}")),
        ("기복(편차)", cell(mh, "sd", lambda v: f"{v:.1f}"), cell(ma, "sd", lambda v: f"{v:.1f}")),
        ("직전 경기", cell(mh, "rest", _ago), cell(ma, "rest", _ago)),
    ]
    return {"notes": lines, "items": items, "rows": rows, "n": (mh or ma)["n"]}
