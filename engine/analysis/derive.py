"""해외 배당을 베트맨 마켓(핸디캡·언더오버)으로 환산한다.

해외 시장의 기준점은 베트맨과 다르다(예: 해외 -7.5, 베트맨 -8.5). 그래서
1) 해외 승패·핸디캡·합계 배당에서 '예상 점수 차'와 '예상 총점'을 역산하고
2) 그 분포로 베트맨 기준점에서의 확률을 다시 계산한다.

- 농구·야구·배구: 점수 차와 총점을 정규분포로 본다(종목별 표준편차).
- 축구: 양 팀 득점을 포아송으로 보고, 해외 승무패(와 합계) 배당에 가장 잘 맞는 기대 득점을 찾는다.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any

N = NormalDist()
# (점수 차 표준편차, 총점 표준편차)
SD = {"basketball": (12.0, 18.0), "baseball": (4.3, 4.4), "volleyball": (1.6, 20.0), "hockey": (2.4, 2.3), "football": (13.5, 13.5)}


def _clip(p: float) -> float:
    return min(max(p, 0.005), 0.995)


def _pois(lam: float, kmax: int = 12) -> list[float]:
    out, p = [], math.exp(-lam)
    for k in range(kmax + 1):
        out.append(p)
        p = p * lam / (k + 1)
    return out


def fit_soccer(h2h: dict[str, float], total: tuple[float, float] | None = None) -> tuple[float, float] | None:
    """해외 승무패 확률(+합계 기준점·오버 확률)에 맞는 (홈 기대득점, 원정 기대득점)."""
    if not {"H", "D", "A"} <= set(h2h):
        return None
    best, arg = 1e9, None
    for ti in range(14, 46):          # 총 기대득점 1.4 ~ 4.5
        lt = ti / 10
        for si in range(10, 91, 2):   # 홈 몫 10% ~ 90%
            lh, la = lt * si / 100, lt * (1 - si / 100)
            ph, pd, pa, pov = _soccer_probs(lh, la, total[0] if total else None)
            err = (ph - h2h["H"]) ** 2 + (pd - h2h["D"]) ** 2 + (pa - h2h["A"]) ** 2
            if total:
                err += (pov - total[1]) ** 2
            if err < best:
                best, arg = err, (lh, la)
    return arg


def _soccer_probs(lh: float, la: float, line: float | None):
    a, b = _pois(lh), _pois(la)
    ph = pd = pa = pov = 0.0
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            p = x * y
            if i > j:
                ph += p
            elif i == j:
                pd += p
            else:
                pa += p
            if line is not None and i + j > line:
                pov += p
    return ph, pd, pa, pov


def soccer_market(lams: tuple[float, float], market: str, line: float | None, keys: set[str]) -> dict[str, float] | None:
    lh, la = lams
    a, b = _pois(lh), _pois(la)
    out = {"H": 0.0, "D": 0.0, "A": 0.0, "O": 0.0, "U": 0.0}
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            p = x * y
            if market == "OU":
                out["O" if i + j > (line or 2.5) else "U"] += p
            else:
                adj = i - j + (line or 0.0)
                out["H" if adj > 0 else "A" if adj < 0 else "D"] += p
    if market == "OU":
        res = {k: out[k] for k in ("O", "U")}
    elif "D" in keys:
        res = {k: out[k] for k in ("H", "D", "A")}
    else:  # 2지 핸디캡: 동률은 적중특례이므로 제외하고 다시 나눈다
        t = out["H"] + out["A"]
        res = {"H": out["H"] / t, "A": out["A"] / t} if t else None
    if not res or set(res) != keys:
        return None
    t = sum(res.values())
    return {k: v / t for k, v in res.items()}


def normal_market(sport: str, x: dict[str, Any], market: str, line: float | None, keys: set[str]) -> dict[str, float] | None:
    sd_m, sd_t = SD.get(sport, SD["basketball"])
    if market == "HANDICAP":
        if x.get("spread"):
            l0, p0 = x["spread"]                       # 해외 홈 핸디 기준점, 홈 커버 확률
            mu = -l0 + sd_m * N.inv_cdf(_clip(p0))
        elif x.get("h2h") and "H" in x["h2h"]:
            ph = x["h2h"]["H"] / (x["h2h"]["H"] + x["h2h"].get("A", 0) or 1)
            mu = sd_m * N.inv_cdf(_clip(ph))
        else:
            return None
        p = N.cdf((mu + (line or 0.0)) / sd_m)
        res = {"H": p, "A": 1 - p}
    elif market == "OU":
        if not x.get("total"):
            return None
        l0, p0 = x["total"]                            # 해외 합계 기준점, 오버 확률
        mu = l0 + sd_t * N.inv_cdf(_clip(p0))
        p = 1 - N.cdf(((line or l0) - mu) / sd_t)
        res = {"O": p, "U": 1 - p}
    else:
        return None
    return res if set(res) == keys else None


def from_overseas(m: dict[str, Any]) -> dict[str, float] | None:
    """m['x'] (해외 승패·핸디·합계) → 이 베트맨 마켓의 확률. 환산할 수 없으면 None."""
    x = m.get("x") or {}
    keys = set(m.get("odds") or {})
    if not x or not keys:
        return None
    mk = m["market"]
    if mk in ("1X2", "WL"):
        h = x.get("h2h")
        if not h:
            return None
        if mk == "WL" and "D" in h:
            t = h["H"] + h["A"]
            h = {"H": h["H"] / t, "A": h["A"] / t}
        return h if set(h) == keys else None
    if m["sport"] == "soccer":
        lams = x.get("lams") or fit_soccer(x.get("h2h") or {}, tuple(x["total"]) if x.get("total") else None)
        if not lams:
            return None
        x["lams"] = list(lams)
        return soccer_market(tuple(lams), mk, m.get("line"), keys)
    return normal_market(m["sport"], x, mk, m.get("line"), keys)
