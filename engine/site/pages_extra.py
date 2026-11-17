"""회차별 페이지와 팀별 페이지용 데이터.

- 회차: 리포트에 나온 마켓을 베트맨 회차 번호(예: 260136)로 묶는다. 같은 마켓은 가장 최근 리포트 것을 쓴다.
- 팀: 베트맨 지난 회차 기록(승패·승무패 행의 실제 점수)과 최근 리포트의 다가오는 경기로 만든다.
  같은 이름이라도 종목이 다르면 다른 팀이다(예: 대한민국 축구·농구·배구).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from ..util import slug

KST = timezone(timedelta(hours=9))
MIN_GAMES = 3  # 지난 기록이 이보다 적고 다가오는 경기도 없는 팀은 페이지를 만들지 않는다


def round_label(ts) -> str:
    t = str(ts or "")
    return f"{int(t[2:])}회차" if t.isdigit() and len(t) == 6 else ""


def round_year(ts) -> str:
    t = str(ts or "")
    return f"20{t[:2]}" if t.isdigit() and len(t) == 6 else ""


def rounds(reports: list[dict]) -> dict[str, dict]:
    """회차 번호 → {ts, label, year, markets, outcomes, dates}. reports 는 최신 날짜가 앞."""
    out: dict[str, dict] = {}
    seen: set[str] = set()
    for r in reports:
        outs = r.get("outcomes") or {}
        for m in r.get("markets", []):
            ts = str(m.get("round") or "")
            if not ts.isdigit() or len(ts) != 6:
                continue
            ro = out.setdefault(ts, {"ts": ts, "label": round_label(ts), "year": round_year(ts), "markets": [], "outcomes": {}, "dates": set()})
            if m["id"] in seen:
                continue
            seen.add(m["id"])
            ro["markets"].append(m)
            ro["dates"].add(r["date"])
            if m["id"] in outs:
                ro["outcomes"][m["id"]] = outs[m["id"]]
    for ro in out.values():
        ro["markets"].sort(key=lambda m: (m["kickoff"], m.get("game_no") or 0))
        ro["dates"] = sorted(ro["dates"])
        ro["first_ko"] = ro["markets"][0]["kickoff"] if ro["markets"] else ""
        ro["last_ko"] = ro["markets"][-1]["kickoff"] if ro["markets"] else ""
        ro["sports"] = Counter(m["sport"] for m in ro["markets"])
        ro["leagues"] = [k for k, _ in Counter(m["league"] for m in ro["markets"]).most_common(4)]
        graded = [(m, ro["outcomes"][m["id"]]) for m in ro["markets"] if m.get("analysis") and ro["outcomes"].get(m["id"]) not in (None, "VOID")]
        ro["graded"] = len(graded)
        ro["hit"] = sum(1 for m, o in graded if o == m["analysis"]["pick"])
    return dict(sorted(out.items(), key=lambda kv: kv[0], reverse=True))


def team_url(sport: str, name: str) -> str:
    return f"/teams/{sport}/{slug(name)}/"


def teams(history_rows: list[list], reports: list[dict], now_iso: str) -> dict[tuple[str, str], dict]:
    """(종목, 팀 이름) → 팀 정보."""
    games: dict[tuple, dict] = {}
    for r in history_rows:
        try:
            sport, league, mk, w, d, l, ko, home, away, hs, as_ = r[0], r[1], r[2], r[4], r[5], r[6], r[8], r[10], r[11], r[12], r[13]
        except (IndexError, TypeError):
            continue
        if mk not in ("WL", "1X2") or hs is None or as_ is None or not home or not away:
            continue
        try:
            dt = datetime.fromtimestamp(int(ko) / 1000, KST)
        except (TypeError, ValueError, OSError):
            continue
        key = (sport, dt.date().isoformat(), home, away)
        if key in games:
            continue
        games[key] = {"sport": sport, "league": league, "date": dt.date().isoformat(), "ko": dt.isoformat(timespec="minutes"),
                      "home": home, "away": away, "hs": hs, "as": as_, "oh": w, "od": d or 0, "oa": l}
    by_team: dict[tuple[str, str], dict] = {}

    def team(sport, name):
        # 띄어쓰기만 다른 이름(예: 'KB 스타즈'·'KB스타즈')은 같은 팀으로 묶는다
        t = by_team.setdefault((sport, name.replace(" ", "")), {"sport": sport, "name": name, "games": [],
                                                                "leagues": Counter(), "upcoming": [], "names": Counter()})
        t["names"][name] += 1
        return t

    for g in games.values():
        for side in ("home", "away"):
            name = g[side]
            me, op = (g["hs"], g["as"]) if side == "home" else (g["as"], g["hs"])
            my_odds, op_odds = (g["oh"], g["oa"]) if side == "home" else (g["oa"], g["oh"])
            res = "W" if me > op else ("L" if me < op else "D")
            t = team(g["sport"], name)
            t["leagues"][g["league"]] += 1
            t["games"].append({"date": g["date"], "league": g["league"], "opp": g["away"] if side == "home" else g["home"],
                               "home": side == "home", "me": me, "op": op, "res": res, "odds": my_odds, "opp_odds": op_odds,
                               "fav": bool(my_odds and op_odds and my_odds < op_odds)})
    # 다가오는 경기(최근 리포트의 승패·승무패 마켓)
    seen = set()
    for r in reports[:3]:
        for m in r.get("markets", []):
            if m.get("market") not in ("WL", "1X2") or m["kickoff"] <= now_iso:
                continue
            k = (m["sport"], m["home"], m["away"], m["kickoff"][:10])
            if k in seen:
                continue
            seen.add(k)
            for side in ("home", "away"):
                t = team(m["sport"], m[side])
                t["leagues"][m["league"]] += 1
                t["upcoming"].append({"m": m, "home": side == "home", "opp": m["away"] if side == "home" else m["home"], "date": r["date"]})
    out = {}
    for k, t in by_team.items():
        if len(t["games"]) < MIN_GAMES and not t["upcoming"]:
            continue
        t["games"].sort(key=lambda x: x["date"], reverse=True)
        # 표시 이름: 다가오는 경기에 쓰인 이름 → 가장 최근 경기 이름 → 가장 많이 쓰인 이름
        if t["upcoming"]:
            t["name"] = t["upcoming"][0]["m"]["home"] if t["upcoming"][0]["home"] else t["upcoming"][0]["m"]["away"]
        else:
            t["name"] = t["names"].most_common(1)[0][0]
        t["url"] = team_url(t["sport"], t["name"])
        t["aliases"] = list(t["names"])
        t["upcoming"].sort(key=lambda x: x["m"]["kickoff"])
        t["league"] = t["leagues"].most_common(1)[0][0] if t["leagues"] else ""
        gs = t["games"]
        t["n"] = len(gs)
        t["w"], t["d"], t["l"] = (sum(1 for x in gs if x["res"] == c) for c in "WDL")
        t["form"] = [x["res"] for x in gs[:10]]
        home = [x for x in gs if x["home"]]
        away = [x for x in gs if not x["home"]]
        t["home_rec"] = _rec(home)
        t["away_rec"] = _rec(away)
        t["avg_for"] = round(sum(x["me"] for x in gs) / len(gs), 1) if gs else None
        t["avg_against"] = round(sum(x["op"] for x in gs) / len(gs), 1) if gs else None
        fav = [x for x in gs if x["fav"]]
        dog = [x for x in gs if x["odds"] and x["opp_odds"] and x["odds"] > x["opp_odds"]]
        t["fav_n"], t["fav_w"] = len(fav), sum(1 for x in fav if x["res"] == "W")
        t["dog_n"], t["dog_w"] = len(dog), sum(1 for x in dog if x["res"] == "W")
        t["h2h"] = _h2h(gs)
        out[(t["sport"], t["name"])] = t
    return out


def _rec(gs: list[dict]) -> dict:
    return {"n": len(gs), "w": sum(1 for x in gs if x["res"] == "W"), "d": sum(1 for x in gs if x["res"] == "D"), "l": sum(1 for x in gs if x["res"] == "L")}


def _h2h(gs: list[dict]) -> list[dict]:
    """자주 만난 상대 상위 5팀과의 전적."""
    by: dict[str, list] = defaultdict(list)
    for x in gs:
        by[x["opp"]].append(x)
    rows = [{"opp": o, **_rec(v)} for o, v in by.items() if len(v) >= 2]
    rows.sort(key=lambda r: -r["n"])
    return rows[:5]


def team_groups(ts: dict[tuple[str, str], dict]) -> list[dict]:
    """팀 목록 페이지: 종목 → 리그 → 팀."""
    order = ["soccer", "basketball", "baseball", "volleyball"]
    out = []
    for sp in order:
        leagues: dict[str, list] = defaultdict(list)
        for (s, _), t in ts.items():
            if s == sp:
                leagues[t["league"]].append(t)
        if not leagues:
            continue
        lg = [{"name": k, "teams": sorted(v, key=lambda t: (-t["n"], t["name"]))} for k, v in leagues.items()]
        lg.sort(key=lambda x: -sum(t["n"] for t in x["teams"]))
        out.append({"sport": sp, "leagues": lg})
    return out
