"""페이지 데이터 → 공유 미리보기 이미지(og.py 로 그림). 실패해도 사이트 빌드는 계속된다(기본 이미지 사용)."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from . import og
from ..schema import OUTCOME_LABEL

log = logging.getLogger("engine.og")
WEEK = "월화수목금토일"


def og_url(url: str) -> str:
    """페이지 주소 → 이미지 주소. '/' → '/og/home.jpg', '/matches/a/b/' → '/og/matches/a/b.jpg'."""
    u = url.strip("/")
    return f"/og/{u or 'home'}.jpg"


def _out(dist: Path, url: str) -> Path:
    return dist / og_url(url).lstrip("/")


def _when(ko: str) -> str:
    t = datetime.fromisoformat(ko)
    return f"{t.month}월 {t.day}일 ({WEEK[t.weekday()]}) {t:%H:%M}"


def _label(m: dict, k: str) -> str:
    """미리보기용 선택 이름: 팀 이름이 들어가 읽기 쉬운 형태."""
    h, a = (m.get("home") or "").split()[0], (m.get("away") or "").split()[0]
    mk, line = m.get("market"), m.get("line")
    if mk == "OU":
        return f"{OUTCOME_LABEL.get(k, k)} {line:g}" if line is not None else OUTCOME_LABEL.get(k, k)
    if mk == "HANDICAP" and line is not None:
        return {"H": f"{h} {line:+g}", "A": f"{a} {-line:+g}"}.get(k, f"핸디 무({line:+g})")
    return {"H": f"{h} 승", "A": f"{a} 승", "D": "무승부"}.get(k, k)


def _pct(p) -> str:
    return f"{round(p * 100)}%" if p is not None else ""


def match(dist: Path, g: dict, round_label: str) -> str | None:
    try:
        main = g.get("main")
        a = (main or {}).get("analysis") or {}
        pick = _label(main, a["pick"]) if a.get("pick") else ""
        extras = []
        for m in g["markets"]:
            ma = m.get("analysis")
            if not ma or m is main:
                continue
            kind = {"HANDICAP": "핸디캡", "OU": "언더오버"}.get(m["market"], "")
            extras.append(f"{kind} {_label(m, ma['pick'])}  {_pct(ma['pick_prob'])}".strip())
        kick = f"{g['league']} · {_when(g['kickoff'])}" + (f" · {g['venue']}" if g.get("venue") and "(" not in g["venue"] else "")
        foot = f"프로토 승부식 {round_label} {g['no']}번" if round_label and g.get("no") else "베트맨 프로토 승부식"
        odds = (main or {}).get("odds", {}).get(a.get("pick")) if a else None
        ok = og.match(_out(dist, g["url"]), kicker=kick, home=g["home"], away=g["away"], pick=pick, prob=_pct(a.get("pick_prob")),
                      odds=f"{odds:.2f}" if odds else "", extras=extras, foot=foot)
        return og_url(g["url"]) if ok else None
    except Exception:  # noqa: BLE001
        log.exception("미리보기 실패 %s", g.get("url"))
        return None


def _top_rows(markets: list[dict], n: int = 3) -> list[tuple[str, str, str]]:
    cand = [m for m in markets if m.get("analysis") and m.get("market") in ("WL", "1X2")]
    cand.sort(key=lambda m: -m["analysis"]["pick_prob"])
    return [(f"{m['home']} vs {m['away']}", _label(m, m["analysis"]["pick"]), _pct(m["analysis"]["pick_prob"])) for m in cand[:n]]


def report(dist: Path, url: str, r: dict, title: str, kicker: str) -> str | None:
    try:
        from collections import Counter
        from ..schema import SPORT_LABEL
        sp = Counter(m["sport"] for m in r.get("markets", []))
        sub = " · ".join(f"{SPORT_LABEL.get(k, k)} {v}" for k, v in sp.most_common()) + " 마켓"
        ok = og.listing(_out(dist, url), kicker=kicker, title=title, sub=sub, rows=_top_rows(r.get("markets", [])),
                        foot="적중 확률 높은 경기 · 전략별 조합 · 역배 · 핸디 · 언오버")
        return og_url(url) if ok else None
    except Exception:  # noqa: BLE001
        log.exception("미리보기 실패 %s", url)
        return None


def round_(dist: Path, url: str, ro: dict) -> str | None:
    try:
        from ..schema import SPORT_LABEL
        f, l = datetime.fromisoformat(ro["first_ko"]), datetime.fromisoformat(ro["last_ko"])
        sub = " · ".join(f"{SPORT_LABEL.get(k, k)} {v}" for k, v in ro["sports"].most_common()) + " 마켓"
        ok = og.listing(_out(dist, url), kicker=f"{ro['year']}년 · {f.month}/{f.day} ~ {l.month}/{l.day}",
                        title=f"프로토 승부식 {ro['label']} 분석", sub=sub, rows=_top_rows(ro["markets"]), foot=f"스포츠분석.kr/rounds/{ro['ts']}")
        return og_url(url) if ok else None
    except Exception:  # noqa: BLE001
        log.exception("미리보기 실패 %s", url)
        return None


def league(dist: Path, url: str, lg: dict) -> str | None:
    tb = lg.get("table")
    if not tb:
        return None
    try:
        P = tb.get("post") or {}
        rows = []
        for r_ in tb["rows"][:3]:
            val = f"{r_['pts']}점" if tb["points"] else f"{r_['w']}승 {r_['l']}패"
            rows.append((f"{r_['rank']}위  {r_['team']}", "", val))
        kicker = f"{tb['season']}" + (f" · 우승 {P['champion']}" if P.get("champion") else "")
        ok = og.listing(_out(dist, url), kicker=kicker, title=f"{lg['name']} 순위", rows=rows, foot="순위표 · 팀별 기록 · 최근 분석 경기")
        return og_url(url) if ok else None
    except Exception:  # noqa: BLE001
        log.exception("미리보기 실패 %s", url)
        return None


def team(dist: Path, t: dict) -> str | None:
    try:
        rank = f"{t['rank'][2]} {t['rank'][0]}위" if t.get("rank") else ""
        rec = t.get("season_rec") or t
        record = f"{rec['w']}승" + (f" {rec['d']}무" if rec.get("d") else "") + f" {rec['l']}패" if t.get("n") else ""
        kicker = f"{t['league']}" + (f" · {t['rank'][3]}" if t.get("rank") else "")
        ok = og.team(_out(dist, t["url"]), kicker=kicker, name=t["name"], rank=rank, record=record, form=t.get("form") or [],
                     foot="최근 경기 · 홈/원정 · 정배·역배 승률 · 다가오는 경기")
        return og_url(t["url"]) if ok else None
    except Exception:  # noqa: BLE001
        log.exception("미리보기 실패 %s", t.get("url"))
        return None
