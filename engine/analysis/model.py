"""경기별 분석: 확률 결합, 추천 픽, 기대값, 신뢰도, 이변 위험."""
from __future__ import annotations

from typing import Any

from .. import config
from ..util import read_json
from .elo import Elo
from .probability import combine, entropy_norm, overround, remove_margin_power, shrink

CAL_PATH = config.STATE / "calibration.json"

# 소스별 기본 가중치. 해외 배당(마진 작음)이 가장 정확한 시장 정보다.
W_REF = 0.60
W_BETMAN = 0.25
W_ELO = 0.15
# 베트맨 과거 기록은 분석에 쓰지 않는다. 과거 기록은 해외 배당 기준(xbook)만 쓴다.


def _divergence(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    return max(abs(a[k] - b[k]) for k in keys)


def analyze_market(m: dict[str, Any], elo: Elo, ref: dict[str, float] | None, alpha: float, book: dict | None = None) -> dict[str, Any]:
    odds = m.get("odds") or {}
    from .xbook import hist_for, market_stat
    xstat = market_stat(book or {}, m) if odds else None
    p_hist = dict(xstat["p"]) if xstat and set(xstat["p"]) == set(odds) else None
    hist_info = hist_for(xstat, odds)
    p_bet = remove_margin_power(odds) if odds else {}
    p_elo = elo.probs(m["sport"], m["home"], m["away"], m["market"]) if m["market"] in ("1X2", "WL") else None

    # 분석은 해외 배당 기준으로만 한다. 베트맨 배당·베트맨 지난 기록·베트맨 배당 변동은 확률에 넣지 않는다
    # (베트맨 배당은 구매 배당 표시용). 해외 배당이 없는 경기는 분석하지 않는다.
    intl = None
    cap = 100
    if ref:
        sources = [(ref, 0.65 if p_hist else 0.85)]
        used = ["해외 배당(기준점 환산)" if m.get("ref_kind") == "환산" else "해외 배당"]
        if p_hist:
            sources.append((p_hist, 0.25)); used.append(f"해외 과거 기록({xstat['src']})")
        if p_elo:
            sources.append((p_elo, 0.10 if p_hist else 0.15)); used.append("Elo")
    else:
        # 해외 배당이 없는 경기: 베트맨 배당은 쓰지 않고 레이팅·기록으로만 본다(신뢰도 상한)
        from ..sources import intl_history as IH
        st = IH.stat(m["home"], m["away"]) if m["sport"] == "soccer" else None
        p_i = IH.market_probs(st, m["market"], m.get("line"), set(odds)) if st else None
        if p_i:
            intl = {"rh": st["rh"], "ra": st["ra"], "n": st["n"]}
            xstat = {"src": "A매치", "n": st["n"], "p": {k: round(v, 4) for k, v in p_i.items()},
                     "basis": f"국가대표 레이팅 {st['rh']} 대 {st['ra']}와 비슷한"}
            hist_info = hist_for(xstat, odds)
            p_hist = None
            sources, used, cap = [(p_i, 1.0)], ["국가대표 레이팅·A매치 기록(해외 배당 없음)"], 55
        elif p_elo and m["market"] in ("1X2", "WL"):
            xstat, hist_info, p_hist = None, None, None
            sources, used, cap = [(p_elo, 1.0)], ["팀 레이팅(해외 배당 없음)"], 40
        else:
            return {**m, "analysis": None, "no_x": True}
        ref = {}
    p = combine(sources)
    if not p:
        return {**m, "analysis": None, "no_x": True}
    p = shrink(p, alpha)
    order = ("H", "D", "A", "O", "U")  # 화면 표시 순서 고정(승·무·패, 오버·언더)
    p = {k: p[k] for k in order if k in p}

    pick = max(p, key=p.get)
    pick_prob = p[pick]
    pick_odds = odds.get(pick)
    ev = pick_prob * pick_odds - 1 if pick_odds else None

    # 가치 픽: 추천 결과와 무관하게 기대값이 가장 높은 결과
    value_key, value_ev = None, None
    if odds:
        evs = {k: p[k] * odds[k] - 1 for k in odds if k in p}
        value_key = max(evs, key=evs.get)
        value_ev = evs[value_key]

    # 신뢰도: 소스 일치도 + 소스 개수 + 픽 확률
    div = max([_divergence(ref or {}, p_hist or {}), _divergence(ref or {}, p_elo or {}), _divergence(p_hist or {}, p_elo or {})])
    agree = max(0.0, 1 - div / 0.25)
    n_src = len(sources)
    confidence = round(100 * (0.45 * agree + 0.25 * (n_src / 3) + 0.30 * min(1.0, (pick_prob - 1 / len(p)) / 0.45)))
    if n_src == 1:
        confidence = min(confidence, 62)  # 단일 소스는 상한을 둔다
    confidence = min(confidence, cap)     # 해외 배당 없는 경기는 더 낮은 상한
    upset = round(100 * (1 - pick_prob) * (0.6 + 0.4 * entropy_norm(p)))
    data_score = round(100 * min(1.0, 0.35 * n_src + (0.15 if p_elo else 0)))

    flags = []
    if not ref:
        flags.append("해외 배당 없음")
    if ref and p_hist and _divergence(ref, p_hist) >= 0.06:
        flags.append("해외 기록과 차이")
    if pick_prob < 0.5 and len(p) == 3:
        flags.append("혼전")
    if upset >= 45:
        flags.append("이변 주의")

    return {
        **m,
        "analysis": {
            "p": {k: round(v, 4) for k, v in p.items()},
            "p_betman": {k: round(v, 4) for k, v in p_bet.items()},
            "p_ref": {k: round(v, 4) for k, v in ref.items()} if ref else None,
            "p_elo": {k: round(v, 4) for k, v in p_elo.items()} if p_elo else None,
            "pick": pick,
            "pick_prob": round(pick_prob, 4),
            "pick_odds": pick_odds,
            "ev": round(ev, 4) if ev is not None else None,
            "value_key": value_key,
            "value_ev": round(value_ev, 4) if value_ev is not None else None,
            "confidence": max(0, min(100, confidence)),
            "upset_risk": max(0, min(100, upset)),
            "data_score": data_score,
            "sources": used,
            "flags": flags,
            "payout_rate": round(1 / overround(odds), 4) if odds else None,
            "hist": hist_info or None,
            "pair": xstat,
            "intl": intl,
            "ref_odds": m.get("ref_odds"),
            # 해외 배당: 승패·승무패는 해외 시장의 실제 배당, 핸디캡·언더오버는 해외 확률을 베트맨 기준점으로 환산한 배당
            "x_odds": ({k: (m["ref_odds"][k] if m.get("ref_kind") == "직접" and (m.get("ref_odds") or {}).get(k) else round(1 / v, 2))
                        for k, v in ref.items() if v > 0} if ref else None),
            "x_kind": m.get("ref_kind"),
            "elo": {
                "home": round(elo.rating(m["sport"], m["home"])),
                "away": round(elo.rating(m["sport"], m["away"])),
            } if p_elo else None,
        },
    }


_LESSONS: dict | None = None


def _apply_lessons(p: dict[str, float], m: dict[str, Any]) -> dict[str, float]:
    """복기에서 배운 보정: 배당이 다른 쪽으로 내려가는 경기에서 과거에 덜 맞았다면 그만큼 확률을 옮긴다."""
    global _LESSONS
    if _LESSONS is None:
        _LESSONS = read_json(config.STATE / "lessons.json", {}) or {}
    ls = _LESSONS.get("flow_against") or {}
    if ls.get("n", 0) < 40 or ls.get("gap", 0) <= 0.02:
        return p
    fl = m.get("flow") or {}
    pick = max(p, key=p.get)
    drops = {k: (fl["from"][k] - v) / fl["from"][k] for k, v in (fl.get("to") or {}).items() if (fl.get("from") or {}).get(k) and k in p}
    rival = max((k for k in drops if k != pick), key=lambda k: drops[k], default=None)
    if not rival or drops[rival] < 0.03:
        return p
    shift = min(p[pick] * 0.5, ls["gap"] * min(1.0, ls["n"] / 150))
    q = dict(p)
    q[pick] -= shift
    q[rival] += shift
    return q


def calibration_alpha() -> float:
    cal = read_json(CAL_PATH, {}) or {}
    a = cal.get("alpha", 0.03)
    return min(max(float(a), 0.0), 0.3)
