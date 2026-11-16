"""팀 최근 흐름: 최근 10경기, 홈·원정 성적, 상대 전적, 휴식일.

데이터: 베트맨 지난 회차 기록(팀명·실제 점수가 있는 승패/승무패 행) + 우리가 채점한 결과.
팀 이름은 베트맨 표기 그대로라 별도 매칭이 필요 없다.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from datetime import datetime
from typing import Any

from .. import config
from ..util import norm_team


class FormIndex:
    def __init__(self) -> None:
        self.games: dict[tuple[str, str], list[tuple[int, str, float, float, bool]]] = defaultdict(list)
        self._seen: set[tuple] = set()

    def add(self, sport: str, ko_ms: int, home: str, away: str, hs: float, as_: float) -> None:
        key = (sport, ko_ms // 3_600_000, norm_team(home), norm_team(away))
        if key in self._seen:
            return
        self._seen.add(key)
        h, a = norm_team(home), norm_team(away)
        self.games[(sport, h)].append((ko_ms, a, hs, as_, True))
        self.games[(sport, a)].append((ko_ms, h, as_, hs, False))

    def finalize(self) -> "FormIndex":
        for v in self.games.values():
            v.sort()
        return self

    def _before(self, sport: str, team: str, ko_ms: int):
        g = self.games.get((sport, norm_team(team)), [])
        i = bisect_left(g, (ko_ms,))
        return g[:i]

    def team(self, sport: str, team: str, ko_ms: int, n: int = 10) -> dict[str, Any] | None:
        past = self._before(sport, team, ko_ms)
        if not past:
            return None
        last = past[-n:]
        seq = []
        w = d = l = 0
        margin = 0.0
        for _, _, f, a, _ in last:
            r = "W" if f > a else "L" if f < a else "D"
            seq.append(r)
            w += r == "W"; d += r == "D"; l += r == "L"
            margin += f - a
        home = [x for x in past if x[4]][-10:]
        away = [x for x in past if not x[4]][-10:]
        rest = (ko_ms - past[-1][0]) / 86_400_000
        return {
            "n": len(last), "w": w, "d": d, "l": l, "seq": "".join(seq),
            "margin": round(margin / len(last), 1),
            "home": [sum(1 for x in home if x[2] > x[3]), len(home)],
            "away": [sum(1 for x in away if x[2] > x[3]), len(away)],
            "rest": round(rest, 1),
            "streak": _streak(seq),
        }

    def h2h(self, sport: str, home: str, away: str, ko_ms: int, n: int = 5) -> dict[str, Any] | None:
        a = norm_team(away)
        past = [x for x in self._before(sport, home, ko_ms) if x[1] == a][-n:]
        if not past:
            return None
        return {"n": len(past), "w": sum(1 for x in past if x[2] > x[3]), "d": sum(1 for x in past if x[2] == x[3]),
                "l": sum(1 for x in past if x[2] < x[3]),
                "last": [{"date": datetime.fromtimestamp(x[0] / 1000, config.KST).strftime("%y.%m.%d"), "score": f"{int(x[2])}:{int(x[3])}",
                          "home": x[4]} for x in reversed(past)]}


def _streak(seq: list[str]) -> str:
    if not seq:
        return ""
    last = seq[-1]
    k = 0
    for r in reversed(seq):
        if r != last:
            break
        k += 1
    return f"{k}{ {'W': '연승', 'L': '연패', 'D': '연속 무'}[last] }" if k >= 2 else ""


def build(history_rows: list[list], reports: list[dict], results_by_date: dict[str, dict]) -> FormIndex:
    idx = FormIndex()
    for row in history_rows:
        if len(row) < 14:
            continue
        sport, _lg, mk, _ln, _w, _d, _l, _c, ko, _uf, home, away, hs, as_ = row[:14]
        if mk in ("1X2", "WL") and hs is not None and as_ is not None and isinstance(ko, (int, float)):
            idx.add(sport, int(ko), home, away, float(hs), float(as_))
    for rep in reports:
        rmap = (results_by_date.get(rep["date"]) or {}).get("markets", {})
        for m in rep.get("markets", []):
            r = rmap.get(m["id"])
            if r and "home_score" in r and m["market"] in ("1X2", "WL"):
                ko = int(datetime.fromisoformat(m["kickoff"]).timestamp() * 1000)
                idx.add(m["sport"], ko, m["home"], m["away"], float(r["home_score"]), float(r["away_score"]))
    return idx.finalize()


def attach(markets: list[dict], idx: FormIndex) -> int:
    """경기마다 홈/원정 최근 흐름과 상대 전적을 붙인다. 붙인 경기 수 반환."""
    cache: dict[tuple, dict] = {}
    n = 0
    for m in markets:
        key = (m["sport"], m["home"], m["away"], m["kickoff"])
        if key not in cache:
            ko = int(datetime.fromisoformat(m["kickoff"]).timestamp() * 1000)
            h = idx.team(m["sport"], m["home"], ko)
            a = idx.team(m["sport"], m["away"], ko)
            cache[key] = {"home": h, "away": a, "h2h": idx.h2h(m["sport"], m["home"], m["away"], ko)} if (h or a) else None
        if cache[key]:
            m["form"] = cache[key]
            n += 1
    return n
