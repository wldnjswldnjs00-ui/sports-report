"""스스로 배우는 확률 결합(사람 손 없이 매일 돈다).

무엇을 배우나
  - 확률 소스별 비중: 해외 배당(ref) · 해외 과거 기록(hist) · 팀 레이팅(elo) / 해외 배당이 없으면 베트맨 배당(bet) · 보조 레이팅(r)
  - 과신 보정(shrink alpha: 균등분포 쪽으로 당기는 정도)
  를 '종목 × 마켓 × 해외 배당 유무' 묶음마다 따로.

어떻게
  1) 채점된 지난 예측에서 각 소스의 확률과 실제 결과를 모은다.
  2) 시간순으로 앞 70%로 찾고(격자 탐색, 로그 손실 최소), 최근 30%로 검증한다.
  3) 검증에서 지금 값보다 확실히 좋을 때만(로그 손실 0.3% 이상 개선, 표본 충분) 바꾼다. 한 번에 절반만 옮긴다.
  4) 실제 발행한 확률이 단순 시장 확률(해외 배당 또는 베트맨 배당)보다 나빠지면 그 묶음은 시장 확률 위주의 안전 설정으로 되돌린다.
결과는 data/state/learned.json(내부용, 사이트에 공개하지 않음).
"""
from __future__ import annotations

import itertools
import logging
import math
from typing import Any

from .. import config
from ..util import read_json, write_json
from .probability import combine, remove_margin_power, shrink

log = logging.getLogger("engine.learn")
PATH = config.STATE / "learned.json"
MIN_TRAIN, MIN_VAL = 300, 120
IMPROVE = 0.003          # 검증 로그 손실이 이만큼(비율) 줄어야 바꾼다
STEP = 0.5               # 새 값 쪽으로 한 번에 옮기는 비율
ROLLBACK_N = 150         # 실제 성적 비교에 필요한 최소 표본
ROLLBACK_MARGIN = 0.01   # 시장 확률보다 로그 손실이 1% 넘게 나쁘면 안전 설정으로

# 지금 모델(model.py)의 기본값과 같아야 한다
DEFAULT = {
    "x": {"w": {"ref": 0.65, "hist": 0.25, "elo": 0.10}, "alpha": None},
    "b": {"w": {"bet": 0.70, "r": 0.30}, "alpha": None},
}
SAFE = {"x": {"ref": 0.9, "hist": 0.1, "elo": 0.0}, "b": {"bet": 1.0, "r": 0.0}}

_cache: dict | None = None


def _mk(m: str) -> str:
    return "WL" if m in ("1X2", "WL") else m


def seg_keys(sport: str, market: str, regime: str) -> list[str]:
    """구체적인 묶음부터 넓은 묶음 순서."""
    return [f"{sport}|{_mk(market)}|{regime}", f"*|{_mk(market)}|{regime}", f"*|*|{regime}"]


def load() -> dict:
    global _cache
    if _cache is None:
        _cache = read_json(PATH, {}) or {}
    return _cache


def params(sport: str, market: str, regime: str) -> dict | None:
    """모델이 쓸 비중·보정값. 배운 값이 없으면 None(기본값 사용)."""
    segs = (load().get("segments") or {})
    for k in seg_keys(sport, market, regime):
        s = segs.get(k)
        if s and s.get("w"):
            return s
    return None


# ───────── 학습 데이터 ─────────
def samples(reports: list[dict]) -> list[dict]:
    out = []
    for r in reports:
        outs = r.get("outcomes") or {}
        for m in r.get("markets", []):
            a, o = m.get("analysis"), outs.get(m["id"])
            if not a or not o or o == "VOID" or m.get("preview") or o not in (a.get("p") or {}):
                continue
            keys = set(a["p"])
            ref = a.get("p_ref")
            pair = (a.get("pair") or {}).get("p")
            src: dict[str, dict] = {}
            if ref:
                regime = "x"
                src["ref"] = ref
                if pair and set(pair) == keys and not a.get("intl"):
                    src["hist"] = pair
                if a.get("p_elo") and set(a["p_elo"]) == keys:
                    src["elo"] = a["p_elo"]
                base = ref
            else:
                regime = "b"
                bet = a.get("p_betman") or (remove_margin_power(m["odds"]) if m.get("odds") else None)
                if not bet:
                    continue
                src["bet"] = bet
                aux = pair if (a.get("intl") and pair) else a.get("p_elo")
                if aux and set(aux) == keys:
                    src["r"] = aux
                base = bet
            out.append({"date": r["date"], "sport": m["sport"], "market": _mk(m["market"]), "regime": regime,
                        "src": src, "o": o, "pub": a["p"], "base": base})
    out.sort(key=lambda s: s["date"])
    return out


def _ll(p: dict, o: str) -> float:
    return -math.log(max(1e-6, p.get(o, 0.0)))


def _pred(s: dict, w: dict, alpha: float) -> dict:
    srcs = [(s["src"][k], w.get(k, 0.0)) for k in s["src"] if w.get(k, 0.0) > 0]
    if not srcs:
        k0 = next(iter(s["src"]))
        srcs = [(s["src"][k0], 1.0)]
    p = combine(srcs)
    return shrink(p, alpha) if alpha else p


def _loss(ss: list[dict], w: dict, alpha: float) -> float:
    return sum(_ll(_pred(s, w, alpha), s["o"]) for s in ss) / max(1, len(ss))


def _grid(regime: str, center: dict | None = None):
    """비중 격자. center 가 있으면 그 주변을 0.05 간격으로 촘촘히, 없으면 0.1 간격으로 넓게."""
    names = list(DEFAULT[regime]["w"])
    if center:
        steps_for = {k: sorted({max(0.0, min(1.0, round(center[k] + d, 2))) for d in (-0.1, -0.05, 0, 0.05, 0.1)}) for k in names[:-1]}
        combos = itertools.product(*[steps_for[k] for k in names[:-1]])
    else:
        combos = itertools.product([i / 10 for i in range(11)], repeat=len(names) - 1)
    for combo in combos:
        last = round(1 - sum(combo), 4)
        if last < -1e-9:
            continue
        w = dict(zip(names, list(combo) + [max(0.0, last)]))
        if regime == "x" and w["ref"] < 0.3:   # 해외 배당은 항상 중심
            continue
        if regime == "b" and w["bet"] < 0.3:
            continue
        yield w


def _fit(train: list[dict], regime: str) -> tuple[dict, float]:
    best = (None, 0.0, float("inf"))
    for center in (None, "fine"):
        grid = _grid(regime) if center is None else _grid(regime, best[0])
        for w in grid:
            for alpha in (0.0, 0.03, 0.06, 0.1, 0.15, 0.2):
                l = _loss(train, w, alpha)
                if l < best[2]:
                    best = (w, alpha, l)
    return best[0], best[1]


def learn(reports: list[dict], base_alpha: float = 0.0) -> dict:
    """매일 한 번(채점 뒤) 돈다. 바뀐 내용을 learned.json 에 남긴다."""
    global _cache
    state = read_json(PATH, {}) or {}
    segs = state.setdefault("segments", {})
    hist = state.setdefault("history", [])
    ss = samples(reports)
    today = config.today_kst()
    groups: dict[str, list] = {}
    for s in ss:
        for k in seg_keys(s["sport"], s["market"], s["regime"]):
            groups.setdefault(k, []).append(s)
    changed = []
    for key, g in groups.items():
        regime = key.split("|")[-1]
        cur = segs.get(key) or {"w": dict(DEFAULT[regime]["w"]), "alpha": base_alpha}
        cut = int(len(g) * 0.7)
        train, val = g[:cut], g[cut:]
        # 1) 실제 발행 확률이 시장 확률보다 나쁘면 안전 설정으로 되돌림
        recent = g[-400:]
        if len(recent) >= ROLLBACK_N:
            pub = sum(_ll(s["pub"], s["o"]) for s in recent) / len(recent)
            mkt = sum(_ll(s["base"], s["o"]) for s in recent) / len(recent)
            cur["live"] = {"n": len(recent), "model": round(pub, 4), "market": round(mkt, 4)}
            if pub > mkt * (1 + ROLLBACK_MARGIN) and cur.get("w") != SAFE[regime]:
                cur.update({"w": dict(SAFE[regime]), "alpha": cur.get("alpha") or base_alpha, "reason": "시장 확률보다 나빠 안전 설정으로", "updated": today})
                hist.append({"date": today, "seg": key, "event": "rollback", "model": round(pub, 4), "market": round(mkt, 4)})
                segs[key] = cur
                changed.append(key)
                continue
        # 2) 챔피언 대 도전자
        if len(train) < MIN_TRAIN or len(val) < MIN_VAL:
            if key in segs:
                segs[key]["n"] = len(g)
            continue
        train = train[-3000:]  # 너무 오래된 표본은 덜 쓴다(계산 시간도 제한)
        w_new, a_new = _fit(train, regime)
        if not w_new:
            continue
        old_v = _loss(val, cur["w"], cur.get("alpha") or 0.0)
        new_v = _loss(val, w_new, a_new)
        if new_v < old_v * (1 - IMPROVE):
            w = {k: round(cur["w"].get(k, 0.0) + STEP * (w_new[k] - cur["w"].get(k, 0.0)), 3) for k in w_new}
            t = sum(w.values()) or 1
            w = {k: round(v / t, 3) for k, v in w.items()}
            alpha = round((cur.get("alpha") or 0.0) + STEP * (a_new - (cur.get("alpha") or 0.0)), 3)
            segs[key] = {"w": w, "alpha": alpha, "n": len(g), "val_old": round(old_v, 4), "val_new": round(new_v, 4),
                         "updated": today, "live": cur.get("live")}
            hist.append({"date": today, "seg": key, "event": "update", "w": w, "alpha": alpha, "val_old": round(old_v, 4), "val_new": round(new_v, 4)})
            changed.append(key)
        else:
            cur["n"] = len(g)
            cur["checked"] = today
            segs[key] = cur
    state["history"] = hist[-300:]
    state["updated"] = today
    state["samples"] = len(ss)
    write_json(PATH, state)
    _cache = state
    log.info("스스로 학습: 표본 %d, 바뀐 묶음 %s", len(ss), changed or "없음")
    return state
