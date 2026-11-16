"""경기 분석문과 복기문. 오레오(OREO) 구조로 쓴다.

O 의견  : 무엇을 고르는가
R 이유  : 왜 그런가 (시장·흐름·레이팅 중 가장 강한 근거)
E 사례  : 숫자로 된 증거 (과거 같은 배당 적중률, 최근 10경기, 상대 전적, 부상자)
O 의견  : 그래서 어떻게 쓰는가 (조합에서의 역할)

문장은 데이터가 있을 때만 만든다. 없는 근거를 지어내지 않는다.
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
    if m["market"] == "HANDICAP":
        base = {"H": m["home"], "A": m["away"], "D": "핸디 무"}.get(key, key)
        return f"{base} 핸디" if key in ("H", "A") else base
    if key == "H":
        return m["home"]
    if key == "A":
        return m["away"]
    if key == "D":
        return "무승부"
    return OUTCOME_LABEL.get(key, key)


def _call(m: dict, key: str) -> str:
    """'한국 승', '무승부', '보스턴 핸디승', '2.5 언더' 같은 예측 표기."""
    mk = m["market"]
    if mk == "OU":
        return f"기준점 {m.get('line'):g} {OUTCOME_LABEL.get(key, key)}"
    if key == "D":
        return "핸디 무" if mk == "HANDICAP" else "무승부"
    team = m["home"] if key == "H" else m["away"]
    return f"{team} {'핸디승' if mk == 'HANDICAP' else '승'}"


def _josa(word: str, pair: tuple[str, str]) -> str:
    ch = word[-1] if word else ""
    if "가" <= ch <= "힣":
        return word + (pair[0] if (ord(ch) - 0xAC00) % 28 else pair[1])
    return word + pair[1]


def _flow_note(m: dict, key: str) -> str | None:
    fl = m.get("flow") or {}
    f0, f1 = (fl.get("from") or {}).get(key), (fl.get("to") or {}).get(key)
    if not f0 or not f1 or f0 == f1:
        return None
    if f1 < f0:
        return f"베트맨 배당이 {f0:.2f}에서 {f1:.2f}로 내려왔다. 구매가 이쪽으로 몰린다는 신호다"
    return f"베트맨 배당이 {f0:.2f}에서 {f1:.2f}로 올랐다. 구매는 반대편으로 쏠리고 있다"


def oreo(m: dict[str, Any]) -> dict[str, str] | None:
    a = m.get("analysis")
    if not a:
        return None
    r = _rng(m["id"])
    pick = a["pick"]
    name = _side(m, pick)
    pp = a["pick_prob"]
    odds = a.get("pick_odds")
    n = len(a["p"])
    strong = pp >= (0.62 if n == 2 else 0.55)

    # O
    call = _call(m, pick)
    if strong:
        o1 = f"{call} 예측. 추정 확률 {_pct(pp)}."
    else:
        o1 = f"{call} 예측. 추정 확률 {_pct(pp)}로 접전이다."

    # R: 가장 강한 근거부터 최대 2개
    reasons: list[str] = []
    ref, bet = a.get("p_ref") or {}, a.get("p_betman") or {}
    if pick in ref and m.get("ref_kind") != "환산":
        gap = (ref[pick] - bet.get(pick, ref[pick])) * 100
        if abs(gap) >= 3:
            reasons.append(f"해외 시장은 이 결과를 {_pct(ref[pick])}로 본다. 베트맨 내재확률({_pct(bet[pick])})보다 {'높다' if gap > 0 else '낮다'}")
        else:
            reasons.append(f"해외 시장 확률({_pct(ref[pick])})과 베트맨 배당이 같은 방향을 가리킨다")
    x = m.get("x") or {}
    if m.get("ref_kind") == "환산" and pick in ref:
        if m["market"] == "OU" and x.get("total"):
            reasons.append(f"해외 시장의 합계 기준점은 {x['total'][0]:g}이다. 이를 베트맨 기준점 {m.get('line'):g}로 환산하면 이 결과가 {_pct(ref[pick])}")
        elif m["market"] == "HANDICAP" and x.get("spread"):
            reasons.append(f"해외 시장의 핸디캡 기준점은 홈 {x['spread'][0]:+g}이다. 베트맨 기준점 {m.get('line'):+g}로 환산하면 이 결과가 {_pct(ref[pick])}")
        elif m["market"] == "HANDICAP":
            reasons.append(f"해외 승무패 배당을 베트맨 핸디캡 {m.get('line'):+g}로 환산하면 이 결과가 {_pct(ref[pick])}")
    fn = _flow_note(m, pick)
    if fn:
        reasons.append(fn)
    F = m.get("form") or {}
    side_form = F.get("home") if pick == "H" else F.get("away") if pick == "A" else None
    opp_form = F.get("away") if pick == "H" else F.get("home") if pick == "A" else None
    if side_form and opp_form and m["market"] in ("1X2", "WL", "HANDICAP"):
        reasons.append(f"최근 {side_form['n']}경기 {side_form['w']}승 {side_form['l']}패(평균 득실 {side_form['margin']:+.1f}), "
                       f"상대는 {opp_form['w']}승 {opp_form['l']}패({opp_form['margin']:+.1f})")
    if a.get("elo") and m["market"] in ("1X2", "WL"):
        d = a["elo"]["home"] - a["elo"]["away"]
        if abs(d) >= 40:
            reasons.append(f"팀 레이팅은 {m['home']} {a['elo']['home']}, {m['away']} {a['elo']['away']}로 {abs(d)}점 차이다")
    if not reasons:
        reasons.append("베트맨 배당에서 발행처 몫을 걷어낸 확률이 이쪽으로 기운다")
    r_txt = ". ".join(reasons[:2]) + "."

    # E: 숫자 증거
    ev: list[str] = []
    pr = a.get("pair")
    if pr and pr["kind"] == "2way":
        ln, hn = _call(m, pr["lo_key"]), _call(m, pr["hi_key"])
        ev.append(f"{ln} {pr['lo']:.2f}배, {hn} {pr['hi']:.2f}배와 같은 배당 구도는 과거 {pr['n']:,}건이고 "
                  f"{pr['lo']:.2f}배 쪽({ln})이 {_pct(pr['lo_rate'])}, {pr['hi']:.2f}배 쪽({hn})이 {_pct(pr['hi_rate'])} 맞았다")
    elif pr and pr["kind"] == "1X2":
        src = "해외 배당 " if pr.get("src") == "해외" else ""
        ev.append(f"{src}홈 {pr['ho']:.2f}배 대 원정 {pr['ao']:.2f}배와 같은 구도 {pr['n']:,}경기는 홈승 {_pct(pr['H'])}, 무 {_pct(pr['D'])}, 원정승 {_pct(pr['A'])}였다")
    h = (a.get("hist") or {}).get(pick)
    if h and not pr:
        ev.append(f"베트맨에서 {h['bucket']} 배당은 과거 {h['n']:,}건 중 {_pct(h['hit'])}가 맞았다")
    if F.get("h2h"):
        hh = F["h2h"]
        ev.append(f"최근 맞대결 {hh['n']}경기는 {m['home']} 기준 {hh['w']}승 {hh['l']}패")
    inj = m.get("injuries") or {}
    outs = {s: [x["name"] for x in inj.get(s, []) if x["out"]] for s in ("home", "away")}
    if outs["home"] or outs["away"]:
        parts = []
        if outs["home"]:
            parts.append(f"{m['home']} {len(outs['home'])}명")
        if outs["away"]:
            parts.append(f"{m['away']} {len(outs['away'])}명")
        ev.append("결장·결장 유력 " + ", ".join(parts))
    if side_form and side_form.get("streak"):
        ev.append(f"{name.replace(' 핸디', '')} {side_form['streak']} 중")
    e_txt = (". ".join(ev[:3]) + ".") if ev else ""

    # O: 쓰임새
    risk = a["upset_risk"]
    if odds and odds < 1.2:
        o2 = f"배당 {odds:.2f}배로 낮다. 단독보다는 조합의 축으로 쓴다."
    elif strong and risk < 30:
        o2 = f"배당 {odds:.2f}배. 안정형·밸런스형 조합의 기준 경기로 적합하다." if odds else "안정형 조합의 기준 경기로 적합하다."
    elif risk >= 45:
        o2 = f"이변 위험 {risk}로 높다. 넣는다면 폴더 수를 줄이고 금액을 낮춘다."
    else:
        o2 = f"배당 {odds:.2f}배. 확률과 배당의 균형이 맞아 밸런스형에 어울린다." if odds else "밸런스형에 어울린다."
    return {"o1": o1, "r": r_txt, "e": e_txt, "o2": o2}


def describe(m: dict[str, Any]) -> str:
    o = oreo(m)
    if not o:
        return "분석에 필요한 데이터가 부족하다."
    m["oreo"] = o
    return " ".join(x for x in [o["o1"], o["r"], o["e"], o["o2"]] if x)


def review(m: dict[str, Any], outcome: str) -> dict[str, str] | None:
    """결과가 나온 뒤의 복기(오레오). 왜 맞았고 왜 틀렸는지 발행 당시 숫자로 설명한다."""
    a = m.get("analysis")
    if not a or outcome == "VOID":
        return None
    pick = a["pick"]
    hit = outcome == pick
    pp = a.get("pick_prob") or (a.get("p") or {}).get(pick) or 0.5
    a.setdefault("upset_risk", 0)
    name, got = _side(m, pick), _side(m, outcome)
    if hit:
        o1 = f"적중. {name} 선택이 맞았다."
    else:
        o1 = f"빗나갔다. 선택은 {name}, 결과는 {got}."
    causes: list[str] = []
    fl = m.get("flow") or {}
    f0, f1 = (fl.get("from") or {}).get(outcome), (fl.get("to") or {}).get(outcome)
    if not hit:
        if f0 and f1 and f1 < f0:
            causes.append(f"경기 전 {got} 배당이 {f0:.2f}에서 {f1:.2f}로 내려가고 있었다. 구매 쏠림이 보낸 신호를 충분히 반영하지 못했다")
        if a["upset_risk"] >= 40:
            causes.append(f"발행 당시 이변 위험이 {a['upset_risk']}로 이미 높았다")
        if pp < 0.55:
            causes.append(f"추정 확률이 {_pct(pp)}에 그친 박빙 경기였다")
        inj = m.get("injuries") or {}
        side = "home" if pick == "H" else "away" if pick == "A" else None
        if side and sum(1 for x in inj.get(side, []) if x["out"]) >= 2:
            causes.append("고른 팀에 결장 선수가 2명 이상 있었다")
        if not causes:
            causes.append(f"추정 확률 {_pct(pp)}는 {_pct(1 - pp)}의 빗나갈 몫을 포함한다. 이번이 그 경우였다")
    else:
        if f0 and f1 and f1 < f0:
            causes.append("배당 흐름도 같은 방향이었다")
        causes.append(f"추정 확률 {_pct(pp)}대로 나온 결과다")
    r_txt = ". ".join(causes[:2]) + "."
    h = (a.get("hist") or {}).get(pick)
    e_txt = f"같은 배당 구간은 과거 {_pct(h['hit'])} 적중했다. {'이번은 나머지 ' + _pct(1 - h['hit']) + '에 해당한다' if not hit else '기록과 같은 결과다'}." if h else ""
    if hit:
        o2 = "같은 조건의 경기에서 이 판단 기준을 유지한다."
    elif f0 and f1 and f1 < f0:
        o2 = "다음부터 배당이 반대쪽으로 움직이는 경기는 신뢰도를 한 단계 낮춘다."
    elif a["upset_risk"] >= 40 or pp < 0.55:
        o2 = "이런 경기는 축으로 쓰지 않고 폴더 수를 줄이는 쪽이 맞다."
    else:
        o2 = "판단 과정에 오류는 없었다. 확률이 허용한 범위의 결과로 기록한다."
    return {"hit": hit, "o1": o1, "r": r_txt, "e": e_txt, "o2": o2}


def headline(report: dict[str, Any]) -> str:
    r = _rng(report["date"])
    n = report["stats"]["matches"]
    if n == 0:
        failed = any(str(v).startswith("실패") for v in (report.get("sources") or {}).values())
        return "발매 정보를 불러오는 중입니다. 잠시 후 다시 확인해 주세요." if failed else "오늘 킥오프하는 발매 경기는 없습니다. 아래에서 다음 경기를 미리 보세요."
    t = report.get("top_pick")
    up = report["stats"].get("upcoming", 0)
    tail = f" 이후 {up}경기도 미리 분석했습니다." if up else ""
    if t:
        side = t["home"] if t["outcome"] == "H" else t["away"] if t["outcome"] == "A" else "무승부"
        how = {"H": "홈승", "A": "원정승", "D": "무승부"}.get(t["outcome"], "")
        return r.choice([f"오늘 프로토 {n}경기. 기준 경기는 {side} {how}({t['p'] * 100:.0f}%).",
                         f"오늘 {n}경기 분석 완료. 가장 단단한 선택은 {side} {how}, 추정 {t['p'] * 100:.0f}%."]) + tail
    return f"오늘 프로토 {n}경기 분석 완료." + tail
