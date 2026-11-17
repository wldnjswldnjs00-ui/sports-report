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


# ───────────────────────── 리그 순위표 ─────────────────────────
NO_TABLE = ("친선", "동남아시아", "네이션스리그", "월드컵", "예선", "컵", "아시안게임", "챔피언스리그", "유로파리그", "컨퍼런스리그",
            "선수권", "올림픽", "리베르타도레스", "동아시아", "박신자", "골드컵", "코파")
EURO = ("잉글랜드", "스페인", "이탈리아", "독일", "프랑스", "네덜란드", "포르투갈", "스코틀랜드", "벨기에", "튀르키예", "터키", "그리스")


def lkey(name: str) -> str:
    return str(name or "").replace(" ", "")


def _season(sport: str, league: str, now: datetime) -> tuple[str, str, str]:
    """(시작일, 끝일(포함 안 함), 시즌 이름). 겨울 리그는 9월(유럽 축구는 7월)에 시작, 나머지는 1월."""
    y = now.year
    if sport in ("basketball", "volleyball") or (sport == "soccer" and any(k in league for k in EURO)):
        m0 = 7 if sport == "soccer" else 9
        sy = y if now.month >= m0 else y - 1
        return f"{sy}-{m0:02d}-01", f"{sy + 1}-{m0:02d}-01", f"{sy}-{str(sy + 1)[2:]} 시즌"
    return f"{y}-01-01", f"{y + 1}-01-01", f"{y} 시즌"


def standings(history_rows: list[list], now: datetime) -> dict[str, dict]:
    """리그(띄어쓰기 뺀 이름) → 이번 시즌 순위표. 베트맨 발매 경기 결과로 센다."""
    games: dict[tuple, dict] = {}
    for r in history_rows:
        try:
            sport, league, mk, ko, home, away, hs, as_ = r[0], r[1], r[2], r[8], r[10], r[11], r[12], r[13]
        except (IndexError, TypeError):
            continue
        if mk not in ("WL", "1X2") or hs is None or as_ is None or any(k in league for k in NO_TABLE):
            continue
        try:
            dt = datetime.fromtimestamp(int(ko) / 1000, KST)
        except (TypeError, ValueError, OSError):
            continue
        k = (lkey(league), dt.date().isoformat(), home, away)
        games.setdefault(k, {"sport": sport, "league": league, "date": dt.date().isoformat(), "home": home, "away": away, "hs": hs, "as": as_})
    by_lg: dict[str, list] = defaultdict(list)
    for g in games.values():
        by_lg[lkey(g["league"])].append(g)
    out = {}
    for lk, gs in by_lg.items():
        sport, name = gs[0]["sport"], Counter(g["league"] for g in gs).most_common(1)[0][0]
        start, end, label = _season(sport, name, now)
        cur = [g for g in gs if start <= g["date"] < end]
        if len(cur) < 10:  # 비시즌이면 지난 시즌
            prev = now.replace(year=now.year - 1)
            start, end, label = _season(sport, name, prev)
            cur = [g for g in gs if start <= g["date"] < end]
        if len(cur) < 10:
            continue
        tb: dict[str, dict] = {}
        for g in sorted(cur, key=lambda x: x["date"]):
            for side in ("home", "away"):
                t, me, op = (g["home"], g["hs"], g["as"]) if side == "home" else (g["away"], g["as"], g["hs"])
                row = tb.setdefault(lkey(t), {"team": t, "g": 0, "w": 0, "d": 0, "l": 0, "pts": 0, "gf": 0, "ga": 0, "form": []})
                row["team"] = t
                row["g"] += 1
                row["gf"] += me
                row["ga"] += op
                res = "W" if me > op else ("L" if me < op else "D")
                row[res.lower()] += 1
                row["form"].append(res)
                if sport == "soccer":
                    row["pts"] += 3 if res == "W" else (1 if res == "D" else 0)
                elif sport == "volleyball":  # 3:0·3:1 승 3점, 3:2 승 2점, 2:3 패 1점
                    row["pts"] += (3 if op <= 1 else 2) if res == "W" else (1 if me == 2 else 0)
        rows = list(tb.values())
        if len(rows) < 4:
            continue
        for r_ in rows:
            dec = r_["w"] + r_["l"]
            r_["pct"] = r_["w"] / dec if dec else 0.0
            r_["gd"] = r_["gf"] - r_["ga"]
            r_["form"] = r_["form"][-5:][::-1]
        if sport in ("soccer", "volleyball"):
            rows.sort(key=lambda x: (-x["pts"], -x["w"], -x["gd"], -x["gf"], x["team"]))
        else:
            rows.sort(key=lambda x: (-x["pct"], -x["w"], x["l"], x["team"]))
        for i, r_ in enumerate(rows):
            r_["rank"] = i + 1
        out[lk] = {"name": name, "sport": sport, "season": label, "rows": rows, "n": len(cur),
                   "last": max(g["date"] for g in cur), "points": sport in ("soccer", "volleyball")}
    return out


def _josa(word: str, pair: tuple[str, str]) -> str:
    ch = (word or " ").rstrip()[-1:]
    if "가" <= ch <= "힣":
        return pair[0] if (ord(ch) - 0xAC00) % 28 else pair[1]
    return pair[1] if ch.isalpha() and ch.lower() in "aeiouy" else pair[0]


def team_intro(t: dict, table: dict | None, venue: str | None) -> list[str]:
    """데이터로 쓰는 팀 소개 문장들."""
    from ..schema import SPORT_LABEL
    nm = t["name"]
    out = [f"{nm}{_josa(nm, ('은', '는'))} 베트맨 프로토 승부식에 발매되는 {t['league'] or SPORT_LABEL.get(t['sport'], '')} 팀입니다."
           + (f" 홈 경기장은 {venue}입니다." if venue else "")]
    if table:
        me = next((r for r in table["rows"] if lkey(r["team"]) == lkey(nm)), None)
        if me:
            rec = f"{me['w']}승" + (f" {me['d']}무" if me["d"] else "") + f" {me['l']}패"
            out.append(f"{table['season']} {table['name']}에서 {me['g']}경기 {rec}"
                       + (f"(승점 {me['pts']})" if table["points"] else f"(승률 {me['pct'] * 100:.0f}%)")
                       + f"로 {len(table['rows'])}팀 중 {me['rank']}위입니다.")
    if t.get("n"):
        f10 = t["form"]
        w10 = f10.count("W")
        out.append(f"최근 {len(f10)}경기는 {w10}승 {len(f10) - w10 - f10.count('D')}패" + (f" {f10.count('D')}무" if f10.count("D") else "")
                   + f"이고, 홈 {t['home_rec']['w']}승 {t['home_rec']['l']}패 · 원정 {t['away_rec']['w']}승 {t['away_rec']['l']}패입니다.")
        bits = []
        if t.get("fav_n", 0) >= 3:
            bits.append(f"정배였던 {t['fav_n']}경기에서 {t['fav_w'] / t['fav_n'] * 100:.0f}%")
        if t.get("dog_n", 0) >= 3:
            bits.append(f"역배였던 {t['dog_n']}경기에서 {t['dog_w'] / t['dog_n'] * 100:.0f}%")
        if bits:
            out.append(" · ".join(bits) + " 이겼습니다.")
    return out


def venues(reports: list[dict]) -> dict[tuple[str, str], str]:
    """(종목, 팀) → 가장 자주 나온 홈 경기장(리포트의 베트맨 경기장 정보)."""
    c: dict[tuple, Counter] = defaultdict(Counter)
    for r in reports[:120]:
        for m in r.get("markets", []):
            v = (m.get("venue") or "").strip()
            if v and "(" not in v:  # '더블린(아일랜드공화국)' 같은 중립 경기 도시는 뺀다
                c[(m["sport"], lkey(m["home"]))][v] += 1
    return {k: v.most_common(1)[0][0] for k, v in c.items()}


def rows_from_results(reports: list[dict], results_by_date: dict[str, dict]) -> list[list]:
    """최근 리포트의 승패·승무패 결과를 지난 회차 기록과 같은 행 모양으로 바꾼다(아직 마감 안 된 회차 보충)."""
    out = []
    for r in reports[:30]:
        res = (results_by_date.get(r["date"]) or {}).get("markets") or {}
        for m in r.get("markets", []):
            if m.get("market") not in ("WL", "1X2"):
                continue
            x = res.get(m["id"]) or {}
            hs, as_ = x.get("home_score"), x.get("away_score")
            if hs is None or as_ is None or x.get("status") != "FT":
                continue
            try:
                ko = int(datetime.fromisoformat(m["kickoff"]).timestamp() * 1000)
            except ValueError:
                continue
            od = m.get("odds") or {}
            out.append([m["sport"], m["league"], m["market"], 0, od.get("H", 0), od.get("D", 0), od.get("A", 0), -1, ko, 0,
                        m["home"], m["away"], float(hs), float(as_)])
    return out
