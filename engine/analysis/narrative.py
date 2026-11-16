"""경기별 한 단락 분석문.

템플릿을 여러 벌 두고 경기 ID 로 고정 시드를 써서 고른다.
같은 경기는 다시 빌드해도 같은 문장이 나오고, 날마다 문장이 똑같이 반복되지 않는다.
말투는 기사체(건조, 짧게). 감탄사·이모지·과장 없음.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any

from ..schema import OUTCOME_LABEL


def _rng(seed: str) -> random.Random:
    return random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:8], 16))


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _side(m: dict, key: str) -> str:
    if key == "H":
        return m["home"]
    if key == "A":
        return m["away"]
    if key == "D":
        return "무승부"
    return OUTCOME_LABEL.get(key, key)


def _with_josa(word: str, pair: tuple[str, str]) -> str:
    """받침 유무로 조사 선택. pair=(받침 있을 때, 없을 때)."""
    ch = word[-1] if word else ""
    if "가" <= ch <= "힣":
        has = (ord(ch) - 0xAC00) % 28 != 0
        return word + (pair[0] if has else pair[1])
    return word + pair[1]


OPEN_FAV = [
    "{fav_i} 우세가 뚜렷하다.",
    "숫자만 놓고 보면 {fav} 쪽으로 기운 경기다.",
    "{fav_i} 한 수 위로 평가된다.",
    "시장도 모델도 {fav} 손을 들어준다.",
]
OPEN_CLOSE = [
    "어느 쪽으로도 쉽게 기울지 않는 경기다.",
    "전력 차가 크지 않아 결과 예측이 까다롭다.",
    "양쪽 확률이 촘촘하게 붙어 있다.",
]
OPEN_CLOSE_SPORT = {
    "soccer": "박빙. 한 골로 갈릴 수 있다.",
    "basketball": "접전 예상. 4쿼터 클러치 싸움이 될 가능성이 높다.",
    "volleyball": "풀세트까지 갈 수 있는 매치업이다.",
    "baseball": "선발 싸움에 따라 결과가 바뀔 경기다.",
}
OPEN_LEAN = [
    "{fav} 쪽으로 약간 기운다.",
    "근소하게 {fav} 우위.",
    "{fav_i} 반 발 앞선다는 평가다.",
]
MID_PROB = [
    "모델 추정 {pick_lbl} 확률은 {pp}, 베트맨 배당 {po}배다.",
    "{pick_lbl} 쪽 추정 확률 {pp}. 배당은 {po}배.",
    "추정 {pp}에 배당 {po}배가 걸려 있다.",
]
EV_NEG = [
    "다만 기대값은 {ev}로, 배당이 확률을 충분히 보상하지 못한다.",
    "기대값은 {ev}. 맞힐 가능성은 높아도 장기적으로 남는 장사는 아니다.",
    "배당 대비 기대값 {ev}. 조합의 안정 축으로만 쓸 만하다.",
]
EV_POS = [
    "배당이 추정 확률보다 후하다. 기대값 {ev}.",
    "베트맨 배당이 시장 평균보다 높게 잡혔다. 기대값 {ev}로 플러스다.",
]
GAP = [
    "해외 배당은 {pick_lbl} 확률을 {pr}로 본다. 베트맨과 {gap}포인트 차이가 난다.",
    "해외 시장 추정치({pr})와 베트맨 내재확률({pb}) 사이에 간격이 있다.",
]
ELO_LINE = [
    "Elo는 {home} {eh}, {away} {ea}.",
    "레이팅 기준 {home} {eh} 대 {away} {ea}.",
]
WARN = {
    "이변 주의": ["이변 가능성을 열어둬야 한다.", "정배가 무너질 여지가 작지 않다."],
    "혼전": ["무승부 변수가 크다.", "세 갈래 결과가 모두 열려 있다."],
    "배당 괴리": ["배당 변동을 킥오프 전에 다시 볼 필요가 있다."],
    "고마진": ["이 마켓은 환급률이 낮다. 배당 손해가 크다."],
}
TAIL = [
    "라인업 발표 후 재확인 권장.",
    "선발 명단이 나오면 판단을 다시 볼 것.",
    "",
    "",
]


def describe(m: dict[str, Any]) -> str:
    a = m.get("analysis")
    if not a:
        return "분석에 필요한 데이터가 부족하다."
    r = _rng(m["id"])
    p = a["p"]
    pick = a["pick"]
    pick_lbl = _side(m, pick)
    fav = pick_lbl
    parts = []
    n = len(p)
    strong, lean = (0.62, 0.55) if n == 2 else (0.55, 0.45)
    fav_i = _with_josa(fav, ("이", "가"))
    if a["pick_prob"] >= strong:
        parts.append(r.choice(OPEN_FAV).format(fav=fav, fav_i=fav_i))
    elif a["pick_prob"] >= lean and pick != "D":
        parts.append(r.choice(OPEN_LEAN).format(fav=fav, fav_i=fav_i))
    else:
        opts = OPEN_CLOSE + ([OPEN_CLOSE_SPORT[m["sport"]]] if m["sport"] in OPEN_CLOSE_SPORT else [])
        parts.append(r.choice(opts))
    if a["pick_odds"]:
        parts.append(r.choice(MID_PROB).format(pick_lbl=pick_lbl, pp=_pct(a["pick_prob"]), po=f"{a['pick_odds']:.2f}"))
    if a.get("p_ref") and pick in a["p_ref"] and pick in a["p_betman"]:
        gap = abs(a["p_ref"][pick] - a["p_betman"][pick]) * 100
        if gap >= 4:
            parts.append(r.choice(GAP).format(pick_lbl=pick_lbl, pr=_pct(a["p_ref"][pick]), pb=_pct(a["p_betman"][pick]), gap=f"{gap:.0f}"))
    if a.get("elo"):
        parts.append(r.choice(ELO_LINE).format(home=m["home"], away=m["away"], eh=a["elo"]["home"], ea=a["elo"]["away"]))
    if a["ev"] is not None:
        ev_s = f"{a['ev'] * 100:+.1f}%"
        parts.append(r.choice(EV_POS if a["ev"] > 0 else EV_NEG).format(ev=ev_s))
    for f in a["flags"]:
        if f in WARN:
            parts.append(r.choice(WARN[f]))
            break
    t = r.choice(TAIL)
    if t and m["sport"] in ("soccer", "basketball"):
        parts.append(t)
    return " ".join(parts)


def headline(report: dict[str, Any]) -> str:
    """리포트 상단 한 줄 요약."""
    r = _rng(report["date"])
    n = report["stats"]["matches"]
    v = len(report.get("value_picks") or [])
    if n == 0:
        failed = any(str(v).startswith("실패") for v in (report.get("sources") or {}).values())
        if failed:
            return "발매 정보를 아직 받아오지 못했다. 다음 수집 때 다시 시도한다."
        return "오늘은 분석할 발매 경기가 없다."
    if v:
        opts = [
            f"{n}경기 중 배당이 확률보다 후한 선택 {v}개.",
            f"오늘 {n}경기. 기대값 플러스 선택은 {v}개로 추렸다.",
        ]
    else:
        opts = [
            f"{n}경기를 봤다. 기대값이 플러스인 선택은 없다. 소액이거나 쉬는 날.",
            f"오늘 {n}경기. 배당이 확률을 이기는 경기를 찾지 못했다.",
        ]
    return r.choice(opts)
