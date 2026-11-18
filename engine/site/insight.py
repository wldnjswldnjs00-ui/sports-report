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


def recent5(t: dict | None, kickoff: str) -> str | None:
    """최근 5경기 평균 득실(경기 시작 전 경기만). 5경기 미만이면 None."""
    gs = [x for x in (t or {}).get("games") or [] if x["date"] < str(kickoff)[:10]][:5]
    if len(gs) < 5:
        return None
    return _f(sum(x["me"] - x["op"] for x in gs) / 5)


def line_hits(t: dict | None, kickoff: str, kind: str, line: float, n: int = 10) -> tuple[int, int] | None:
    """팀 최근 n경기에 기준점 대입: kind=margin(내 점수차+기준점>0) / total(합계>기준점). 딱 맞은 경기는 뺀다. (넘김, 셈한 경기)"""
    gs = [x for x in (t or {}).get("games") or [] if x["date"] < str(kickoff)[:10]][:n]
    hit = cnt = 0
    for x in gs:
        v = (x["me"] - x["op"] + line) if kind == "margin" else (x["me"] + x["op"] - line)
        if v == 0:
            continue
        cnt += 1
        hit += v > 0
    return (hit, cnt) if cnt >= 5 else None


def head_to_head(t: dict | None, opp: str, kickoff: str, n: int = 5) -> dict | None:
    gs = [x for x in (t or {}).get("games") or [] if x["date"] < str(kickoff)[:10] and x.get("opp") == opp][:n]
    if not gs:
        return None
    w = sum(1 for x in gs if x["res"] == "W")
    l = sum(1 for x in gs if x["res"] == "L")
    return {"n": len(gs), "w": w, "l": l, "d": len(gs) - w - l,
            "margin": sum(x["me"] - x["op"] for x in gs) / len(gs), "total": sum(x["me"] + x["op"] for x in gs) / len(gs),
            "games": [{"date": x["date"], "me": x["me"], "op": x["op"]} for x in gs]}


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
    return f"{0:.{d}f}" if abs(x) < 0.5 * 10 ** -d else f"{x:+.{d}f}"


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
    # 합계 vs 언더오버 기준점: 최근 득실로 본 예상 합계 + 두 팀 최근 경기에 오늘 기준점을 대입한 결과
    ou = _main_line(g, "OU")
    ovr = None
    if ou:
        oh, oa = line_hits(th, g["kickoff"], "total", ou["line"]), line_hits(ta, g["kickoff"], "total", ou["line"])
        if oh and oa:
            ovr = (oh[0] + oa[0], oh[1] + oa[1])
    if ou and mh and ma and TOT.get(sp):
        exp_total = (mh["for"] + ma["against"] + ma["for"] + mh["against"]) / 2
        gap = exp_total - ou["line"]
        rate = ovr[0] / ovr[1] if ovr and ovr[1] >= 12 else None
        by_avg = 1 if gap >= TOT[sp] else -1 if gap <= -TOT[sp] else 0
        by_cnt = 1 if rate is not None and rate >= 0.75 else -1 if rate is not None and rate <= 0.25 else 0
        side = by_avg or by_cnt
        if side and not (by_avg and by_cnt and by_avg != by_cnt):
            ol = j(f"{ou['line']:g}", "을를")
            cnt = f" 두 팀 최근 {ovr[1]}경기 중 {ovr[0]}경기가 {ol} 넘었습니다." if ovr and by_cnt == side else ""
            notes.append((3 if by_avg and by_cnt else 2, "합계",
                          f"두 팀 최근 득실로 본 예상 합계는 {j(f'{exp_total:.1f}{u}', '으로')} 기준점 {ou['line']:g}보다 "
                          f"{'높습니다' if gap > 0 else '낮습니다'}.{cnt} {'오버' if side > 0 else '언더'} 쪽 근거입니다."))
    # 핸디 기준점 대입: 각 팀 최근 10경기에 오늘 핸디를 적용했을 때 넘긴 경기 수
    hc0 = _main_line(g, "HANDICAP")
    cov = {}
    if hc0:
        for side, t, ln in (("home", th, hc0["line"]), ("away", ta, -hc0["line"])):
            r = line_hits(t, g["kickoff"], "margin", ln)
            if r:
                cov[side] = (r[0], r[1], ln)
        for side, name in (("home", g["home"]), ("away", g["away"])):
            if side in cov:
                c, n, ln = cov[side]
                if n >= 8 and (c / n >= 0.8 or c / n <= 0.2):
                    lt = j(f"{ln:+g}", "을를")
                    notes.append((2, "핸디", f"{j(name, '은는')} 최근 {n}경기에 오늘 기준점 {lt} 대입하면 {c}경기에서 넘겼습니다."
                                         + (" 이 기준점을 꾸준히 넘긴 팀입니다." if c / n >= 0.8 else " 이 기준점은 넘기기 어려웠던 팀입니다.")))
    # 맞대결: 두 팀이 최근 만난 경기의 승패·점수 차·합계
    vs = head_to_head(th, g["away"], g["kickoff"])
    if vs and vs["n"] >= 3:
        if vs["w"] == vs["n"] or vs["l"] == vs["n"]:
            who = g["home"] if vs["w"] == vs["n"] else g["away"]
            notes.append((2, "맞대결", f"최근 맞대결 {vs['n']}번은 {who}이(가) 모두 이겼습니다(평균 {abs(vs['margin']):.1f}{u} 차)."))
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
    if hc0 and cov:
        def cv(sd):
            return f"{cov[sd][0]}/{cov[sd][1]}" if sd in cov else "–"
        rows.append((f"핸디 {hc0['line']:+g} 대입", cv("home"), cv("away")))
    if ou:
        def ov(t):
            r = line_hits(t, g["kickoff"], "total", ou["line"])
            return f"{r[0]}/{r[1]}" if r else "–"
        rows.append((f"합계 {ou['line']:g} 넘김", ov(th), ov(ta)))
    if vs:
        rows.append((f"맞대결 최근 {vs['n']}", f"{vs['w']}승{(' ' + str(vs['d']) + '무') if vs['d'] else ''} {vs['l']}패 · {_f(vs['margin'])}",
                     f"{vs['l']}승{(' ' + str(vs['d']) + '무') if vs['d'] else ''} {vs['w']}패 · {_f(-vs['margin'])}"))
    return {"notes": lines, "items": items, "rows": rows, "n": (mh or ma)["n"], "vs": vs}


# ── 예상 스코어 ────────────────────────────────────────────
# 분석 확률(해외 배당 기준으로 결합한 최종 확률)에서 역산한다. 매 갱신마다 확률이 바뀌면 같이 바뀐다.
# - 축구: 승무패(+언더오버) 확률에 맞는 양 팀 기대 득점(포아송) → 가장 나올 법한 스코어
# - 농구·야구: 핸디(없으면 승패) 확률 → 예상 점수 차, 언더오버 확률 → 예상 합계(정규분포). 언더오버가 없으면 두 팀 최근 득실로 합계
# - 배구: 승리 확률 → 세트당 이길 확률 → 가장 나올 법한 세트 스코어
def _p2(m: dict | None, a: str, b: str) -> float | None:
    p = ((m or {}).get("analysis") or {}).get("p") or {}
    if p.get(a) is None or p.get(b) is None or p[a] + p[b] <= 0:
        return None
    return min(max(p[a] / (p[a] + p[b]), 0.02), 0.98)


def predict(g: dict, th: dict | None = None, ta: dict | None = None) -> dict | None:
    from statistics import NormalDist
    from ..analysis import derive as D
    sp = g["sport"]
    mk = g.get("markets") or []
    main = next((m for m in mk if m.get("market") in ("1X2", "WL") and (m.get("analysis") or {}).get("p")), None)
    ou, hc = _main_line(g, "OU"), _main_line(g, "HANDICAP")
    try:
        if sp == "soccer":
            p = (main or {}).get("analysis", {}).get("p") or {}
            if not {"H", "D", "A"} <= set(p):
                return None
            po = _p2(ou, "O", "U")
            lams = D.fit_soccer(p, (ou["line"], po) if ou and po is not None else None)
            if not lams:
                return None
            a, b = D._pois(lams[0], 8), D._pois(lams[1], 8)
            i, k = max(((i, k) for i in range(9) for k in range(9)), key=lambda t: a[t[0]] * b[t[1]])
            return {"h": i, "a": k, "xh": round(lams[0], 1), "xa": round(lams[1], 1)}
        if sp == "volleyball":
            pw = _p2(main, "H", "A")
            if pw is None:
                return None
            lo, hi = 0.01, 0.99
            for _ in range(40):           # 세트당 확률 q: 5세트 3선승 승리 확률이 pw 가 되게
                q = (lo + hi) / 2
                win = q ** 3 * (1 + 3 * (1 - q) + 6 * (1 - q) ** 2)
                lo, hi = (q, hi) if win < pw else (lo, q)
            r = 1 - q
            dist = {(3, 0): q ** 3, (3, 1): 3 * q ** 3 * r, (3, 2): 6 * q ** 3 * r ** 2,
                    (0, 3): r ** 3, (1, 3): 3 * r ** 3 * q, (2, 3): 6 * r ** 3 * q ** 2}
            h, a = max(dist, key=dist.get)
            return {"h": h, "a": a}
        if sp not in D.SD:
            return None
        sdm, sdt = D.SD[sp]
        z = NormalDist().inv_cdf
        pc = _p2(hc, "H", "A")
        if pc is not None:
            mu = -hc["line"] + sdm * z(pc)
        else:
            pw = _p2(main, "H", "A")
            if pw is None:
                return None
            mu = sdm * z(pw)
        po = _p2(ou, "O", "U")
        if po is not None:
            tot = ou["line"] + sdt * z(po)
        else:
            mh, ma = metrics(th, sp, g["kickoff"]) if th else None, metrics(ta, sp, g["kickoff"]) if ta else None
            if not (mh and ma):
                return None
            tot = (mh["for"] + ma["against"] + ma["for"] + mh["against"]) / 2
        h, a = round((tot + mu) / 2), round((tot - mu) / 2)
        if h == a:                        # 농구·야구는 무승부가 없다
            h, a = (h + 1, a) if mu >= 0 else (h, a + 1)
        return {"h": max(h, 0), "a": max(a, 0)}
    except Exception:  # noqa: BLE001
        return None
