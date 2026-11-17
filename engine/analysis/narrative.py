"""경기 분석문과 복기문. 오레오(OREO) 구조로 쓴다.

O 의견  : 무엇을 고르는가
R 이유  : 왜 그런가 (시장·흐름·레이팅 중 가장 강한 근거)
E 사례  : 숫자로 된 증거 (해외 배당이 비슷했던 과거 경기의 실제 결과, 최근 10경기, 상대 전적, 부상자)
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
        o1 = r.choice([f"{call} 예측. 확률은 {_pct(pp)}로 본다.", f"{call} 예측({_pct(pp)}).", f"{call} 예측. {_pct(pp)}로 한쪽에 무게가 실린다."])
    else:
        o1 = r.choice([f"{call} 예측. 다만 {_pct(pp)}라 거의 반반이다.", f"{call} 예측({_pct(pp)}). 박빙이다.", f"{call} 예측. {_pct(pp)}로 크게 앞서지는 않는다."])

    # R: 가장 강한 근거부터 최대 2개
    reasons: list[str] = []
    ref = a.get("p_ref") or {}
    if pick in ref and m.get("ref_kind") != "환산":
        reasons.append(r.choice([f"해외 시장도 {_pct(ref[pick])}로 같은 쪽을 본다", f"해외 배당 기준으로도 {_pct(ref[pick])}"]))
    x = m.get("x") or {}
    if m.get("ref_kind") == "환산" and pick in ref:
        if m["market"] == "OU" and x.get("total"):
            if abs(x["total"][0] - (m.get("line") or 0)) < 0.01:
                reasons.append(f"해외 시장도 같은 기준점 {x['total'][0]:g}에서 이 결과를 {_pct(ref[pick])}로 본다")
            else:
                reasons.append(f"해외 기준점 {x['total'][0]:g}에서 이 경기 {m.get('line'):g}로 맞춰 보면 {_pct(ref[pick])}")
        elif m["market"] == "HANDICAP" and x.get("spread"):
            if abs(x["spread"][0] - (m.get("line") or 0)) < 0.01:
                reasons.append(f"해외 시장도 같은 핸디캡 {x['spread'][0]:+g}에서 이 결과를 {_pct(ref[pick])}로 본다")
            else:
                reasons.append(f"해외 핸디 {x['spread'][0]:+g}에서 이 경기 {m.get('line'):+g}로 맞춰 보면 {_pct(ref[pick])}")
        elif m["market"] == "HANDICAP":
            reasons.append(f"해외 승무패 배당을 이 경기 핸디 {m.get('line'):+g}로 맞춰 보면 {_pct(ref[pick])}")
    F = m.get("form") or {}
    side_form = F.get("home") if pick == "H" else F.get("away") if pick == "A" else None
    opp_form = F.get("away") if pick == "H" else F.get("home") if pick == "A" else None
    if side_form and opp_form and m["market"] in ("1X2", "WL", "HANDICAP"):
        me = name.replace(" 핸디", "")
        reasons.append(f"{_josa(me, ('은', '는'))} 최근 {side_form['n']}경기 {side_form['w']}승 {side_form['l']}패, 상대는 {opp_form['w']}승 {opp_form['l']}패")
    if a.get("intl"):
        it = a["intl"]
        reasons.insert(0, f"해외 배당이 없는 경기다. 국가대표 레이팅(A매치 전 경기 기준)은 {m['home']} {it['rh']}, {m['away']} {it['ra']}로 {abs(it['rh'] - it['ra'])}점 차이다")
    elif not a.get("p_ref") and a.get("elo"):
        reasons.insert(0, "해외 배당이 없는 경기라 팀 레이팅으로만 봤다")
    if a.get("elo") and m["market"] in ("1X2", "WL") and not a.get("intl"):
        d = a["elo"]["home"] - a["elo"]["away"]
        if abs(d) >= 40:
            reasons.append(f"팀 레이팅도 {m['home'] if d > 0 else m['away']} 쪽이 {abs(d)}점 높다")
    if not reasons:
        reasons.append("해외 배당에서 발행처 몫을 걷어낸 확률이 이쪽으로 기운다" if a.get("p_ref")
                       else "해외 배당이 없어 베트맨 배당에서 발행처 몫을 걷어낸 확률로 봤다")
    r_txt = ". ".join(reasons[:2]) + "."

    # E: 숫자 증거
    ev: list[str] = []
    from .xbook import x_pair
    pr = x_pair(a)
    if pr:
        hit = pr["p"].get(pick)
        if hit is not None:
            ev.append(r.choice([f"배당이 비슷했던 {pr['src']} {pr['n']:,}경기 중 {_pct(hit)}가 이렇게 끝났다",
                                f"비슷한 배당의 {pr['src']} {pr['n']:,}경기를 보면 {_pct(hit)}가 같은 결과였다"]))
    bh = a.get("bhist")
    if bh and not pr:
        ev.append(f"베트맨 배당이 비슷했던 {bh['group']} {bh['n']:,}경기 중 {_pct(bh['hit'])}가 이렇게 끝났다")
    if F.get("h2h"):
        hh = F["h2h"]
        ev.append(f"최근 맞대결은 {m['home']} 기준 {hh['w']}승 {hh['l']}패")
    inj = {}  # 부상자 기능은 쓰지 않는다
    outs = {s: [x["name"] for x in inj.get(s, []) if x["out"]] for s in ("home", "away")}
    if outs["home"] or outs["away"]:
        parts = []
        if outs["home"]:
            parts.append(f"{m['home']} {len(outs['home'])}명")
        if outs["away"]:
            parts.append(f"{m['away']} {len(outs['away'])}명")
        ev.append("결장·결장 유력 " + ", ".join(parts))
    if side_form and side_form.get("streak") and len(ev) < 2:
        ev.append(f"{name.replace(' 핸디', '')} {side_form['streak']} 중")
    e_txt = (". ".join(ev[:2]) + ".") if ev else ""

    # O: 쓰임새
    risk = a["upset_risk"]
    xo = (a.get("x_odds") or {}).get(pick)
    if xo and xo < 1.2:
        o2 = r.choice(["배당이 낮아 단독보다는 조합의 축으로 쓸 만하다.", "혼자 사기엔 배당이 낮다. 조합에 한 장 끼우는 용도."])
    elif strong and risk < 30:
        o2 = r.choice(["안정형 조합의 기준 경기로 무난하다.", "조합을 짤 때 먼저 깔고 가기 좋은 경기."])
    elif risk >= 45:
        o2 = r.choice(["뒤집힐 여지가 꽤 있다. 넣는다면 폴더 수와 금액을 줄인다.", "이변이 자주 나오는 구도라 무리하지 않는 게 좋다."])
    else:
        o2 = r.choice(["한쪽으로 크게 기울지 않아 밸런스형에 어울린다.", "확신보다는 비중을 나눠 담을 경기."])
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
    if not hit:
        if a["upset_risk"] >= 40:
            causes.append(f"발행 당시 이변 위험이 {a['upset_risk']}로 이미 높았다")
        if pp < 0.55:
            causes.append(f"추정 확률이 {_pct(pp)}에 그친 박빙 경기였다")
        inj = {}  # 부상자 기능은 쓰지 않는다
        side = "home" if pick == "H" else "away" if pick == "A" else None
        if side and sum(1 for x in inj.get(side, []) if x["out"]) >= 2:
            causes.append("고른 팀에 결장 선수가 2명 이상 있었다")
        if not causes:
            causes.append(f"추정 확률 {_pct(pp)}는 {_pct(1 - pp)}의 빗나갈 몫을 포함한다. 이번이 그 경우였다")
    else:
        causes.append(f"추정 확률 {_pct(pp)}대로 나온 결과다")
    r_txt = ". ".join(causes[:2]) + "."
    from .xbook import x_hist
    h = x_hist(a).get(pick)
    e_txt = f"해외 배당이 비슷했던 {h['bucket']} 경기에서는 {_pct(h['hit'])} 적중했다. {'이번은 나머지 ' + _pct(1 - h['hit']) + '에 해당한다' if not hit else '기록과 같은 결과다'}." if h else ""
    if hit:
        o2 = "같은 조건의 경기에서 이 판단 기준을 유지한다."
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
