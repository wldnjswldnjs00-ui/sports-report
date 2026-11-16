"""배당 → 확률 변환과 확률 결합.

- 마진 제거: power 방식(저배당/고배당 편향 보정). 실패 시 비례 방식으로 폴백.
- 결합: 로그 오즈(log-odds) 가중 평균. 소스가 빠지면 가중치를 재정규화한다.
"""
from __future__ import annotations

import math


def implied(odds: dict[str, float]) -> dict[str, float]:
    return {k: 1.0 / v for k, v in odds.items()}


def overround(odds: dict[str, float]) -> float:
    return sum(implied(odds).values())


def remove_margin_proportional(odds: dict[str, float]) -> dict[str, float]:
    imp = implied(odds)
    s = sum(imp.values())
    return {k: v / s for k, v in imp.items()}


def remove_margin_power(odds: dict[str, float]) -> dict[str, float]:
    """p_i = (1/o_i)^k, sum p_i = 1 을 만족하는 k 를 이분법으로 찾는다.

    베트맨처럼 마진이 큰 배당에서 비례 방식보다 저배당(정배) 확률을 덜 깎는다.
    """
    imp = implied(odds)
    if len(imp) < 2:
        return remove_margin_proportional(odds)
    s = sum(imp.values())
    if abs(s - 1) < 1e-9:
        return dict(imp)
    lo, hi = 0.2, 5.0
    f = lambda k: sum(v ** k for v in imp.values()) - 1.0  # noqa: E731
    if f(lo) * f(hi) > 0:
        return remove_margin_proportional(odds)
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    k = (lo + hi) / 2
    p = {key: v ** k for key, v in imp.items()}
    t = sum(p.values())
    return {key: v / t for key, v in p.items()}


def _clip(p: float, eps: float = 1e-4) -> float:
    return min(max(p, eps), 1 - eps)


def combine(sources: list[tuple[dict[str, float], float]]) -> dict[str, float]:
    """[(확률분포, 가중치)] 를 로그 확률 가중 평균으로 결합(기하 평균 풀링).

    키 집합이 다르면 공통 키만 사용한다. 소스가 없으면 빈 dict.
    """
    sources = [(p, w) for p, w in sources if p and w > 0]
    if not sources:
        return {}
    keys = set(sources[0][0])
    for p, _ in sources[1:]:
        keys &= set(p)
    if not keys:
        return dict(sources[0][0])
    wsum = sum(w for _, w in sources)
    logit = {k: sum(w * math.log(_clip(p[k])) for p, w in sources) / wsum for k in keys}
    z = {k: math.exp(v) for k, v in logit.items()}
    t = sum(z.values())
    return {k: v / t for k, v in z.items()}


def shrink(p: dict[str, float], alpha: float) -> dict[str, float]:
    """과신 방지: 균등분포 쪽으로 alpha 만큼 당긴다 (보정 단계에서 학습된 값 사용)."""
    if not p:
        return p
    n = len(p)
    return {k: (1 - alpha) * v + alpha / n for k, v in p.items()}


def entropy_norm(p: dict[str, float]) -> float:
    """0(확실) ~ 1(완전 불확실)."""
    if len(p) < 2:
        return 0.0
    h = -sum(v * math.log(v) for v in p.values() if v > 0)
    return h / math.log(len(p))
