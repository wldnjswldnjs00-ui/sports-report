"""정적 사이트 생성기. data/ → dist/

서버 없이 HTML 파일만 만든다. 방문자가 늘어도 서버 CPU 를 쓰지 않는다.
"""
from __future__ import annotations

import json
import re
import logging
import shutil
from collections import defaultdict
from datetime import date, timedelta, datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Undefined, select_autoescape

from .. import config
from ..analysis.combos import STRATEGIES
from ..analysis.grading import is_pick
from ..analysis.grading import load_perf
from ..schema import MARKET_LABEL, OUTCOME_LABEL, SPORT_LABEL
from ..util import read_json, slug, write_json
from . import insight as INS

log = logging.getLogger("engine.build")
HERE = Path(__file__).resolve().parent
WEEK = "월화수목금토일"


def _none(x):
    return x is None or isinstance(x, Undefined)


def _pct(x, d=0):
    return "–" if _none(x) else f"{x * 100:.{d}f}%"


def _signed(x, d=1):
    return "–" if _none(x) else f"{x * 100:+.{d}f}%"


def _odds(x):
    return "–" if _none(x) or not x else f"{x:.2f}"


def _won(x):
    return "–" if _none(x) else f"{int(x):,}원"


def _kdate(s: str, with_week=True):
    d = date.fromisoformat(s[:10])
    out = d.strftime("%Y.%m.%d")
    return f"{out} ({WEEK[d.weekday()]})" if with_week else out


def _ktime(s: str):
    return datetime.fromisoformat(s).strftime("%H:%M")


def _kdt(s: str):
    t = datetime.fromisoformat(s)
    return f"{t.month}/{t.day} {t:%H:%M}"


def _outcome(m: dict, key: str) -> str:
    mk = m.get("market")
    if mk == "OU":
        return OUTCOME_LABEL.get(key, key)
    if mk == "HANDICAP":
        line = m.get("line")
        ln = f"{line:+g}" if line is not None else ""
        return {"H": f"핸디승{(' ' + ln) if ln else ''}", "D": "핸디무", "A": "핸디패"}.get(key, key)
    return OUTCOME_LABEL.get(key, key)



def _short(team: str) -> str:
    t = str(team or "").split()
    return t[0] if t and len(t[0]) >= 2 else str(team or "")


def _pick_label(x: dict, key: str | None = None) -> str:
    """팀 기준으로 읽히는 선택 이름: '브루클린 승', '노르웨이 +1', '언더 2.5'."""
    k = key or x.get("outcome")
    mk, line = x.get("market"), x.get("line")
    h, a = _short(x.get("home")), _short(x.get("away"))
    if mk == "OU":
        return f"{OUTCOME_LABEL.get(k, k)} {line:g}" if line is not None else OUTCOME_LABEL.get(k, k)
    if mk == "HANDICAP" and line is not None:
        if k == "H":
            return f"{h} {line:+g}"
        if k == "A":
            return f"{a} {-line:+g}"
        return f"핸디 무({line:+g})"
    return {"H": f"{h} 승", "D": "무승부", "A": f"{a} 승"}.get(k, k)


LINE_KINDS = (("up", "역배", "upsets"), ("hd", "핸디캡", "handi_picks"), ("ou", "언더오버", "ou_picks"))


def _line_groups(r: dict) -> list[dict]:
    """역배·핸디캡·언더오버 픽을 경기별로 묶는다(한 경기 = 한 칸)."""
    groups: dict[tuple, dict] = {}
    for kind, label, field in LINE_KINDS:
        for x in r.get(field) or []:
            key = (x.get("home"), x.get("away"), str(x.get("kickoff"))[:10])
            g = groups.setdefault(key, {"home": x.get("home"), "away": x.get("away"), "league": x.get("league"),
                                        "sport": x.get("sport"), "kickoff": x.get("kickoff"), "picks": [], "kinds": []})
            if any(p["x"].get("market_id") == x.get("market_id") and p["x"].get("outcome") == x.get("outcome") for p in g["picks"]):
                continue
            g["picks"].append({"kind": kind, "label": label, "x": x})
            if kind not in g["kinds"]:
                g["kinds"].append(kind)
                g["k_" + kind] = True
            if str(x.get("kickoff")) < str(g["kickoff"]):
                g["kickoff"] = x.get("kickoff")
    return sorted(groups.values(), key=lambda g: (str(g["kickoff"]), g["home"] or ""))


def _upset_map(r: dict) -> dict:
    """경기별 역배 후보(가장 확률 높은 것 하나): 'home|away|date' → 픽."""
    out: dict[str, dict] = {}
    for x in r.get("upsets") or []:
        k = f"{x.get('home')}|{x.get('away')}|{str(x.get('kickoff'))[:10]}"
        if k not in out or (x.get("p") or 0) > (out[k].get("p") or 0):
            out[k] = x
    return out


def _tone(label) -> str:
    """선택 이름에 맞는 색 클래스. 핸디는 부호(+ 초록, − 빨강), 그 외는 승/오버 초록, 패/언더 빨강."""
    t = str(label or "")
    mt = re.search(r"([+\-−])\d", t)
    if mt:
        return "t-neg" if mt.group(1) in "-−" else "t-pos"
    if "오버" in t:
        return "t-pos"
    if "언더" in t:
        return "t-neg"
    if "무" in t:
        return "t-draw"
    if "패" in t:
        return "t-neg"
    if "승" in t:
        return "t-pos"
    return ""


def _tone_html(label):
    """팀 이름은 색 없이, 결과(승·패·+n·−n)만 색을 입힌다. '언더 2.5'처럼 팀 이름이 없으면 전체에 색."""
    from markupsafe import Markup, escape
    t = str(label or "")
    head, _, last = t.rpartition(" ")
    if head and not head.startswith(("오버", "언더", "핸디")):
        return Markup(f'{escape(head)} <span class="{_tone(last)}">{escape(last)}</span>')
    return Markup(f'<span class="{_tone(t)}">{escape(t)}</span>')


def _flow_key(m: dict) -> str | None:
    """배당이 3% 이상 가장 많이 내려간 선택(=구매가 몰린 쪽)."""
    fl = m.get("flow") or {}
    best, drop = None, 0.03
    for k, v in (fl.get("to") or {}).items():
        f0 = (fl.get("from") or {}).get(k)
        if f0 and v and (f0 - v) / f0 >= drop:
            best, drop = k, (f0 - v) / f0
    return best


def _round_label(ts) -> str:
    """베트맨 회차 번호 260136 → '136회차'."""
    t = str(ts or "")
    return f"{int(t[2:])}회차" if t.isdigit() and len(t) == 6 else ""


def _rounds(r: dict) -> list[str]:
    seen = []
    for m in r.get("markets", []):
        lb = _round_label(m.get("round"))
        if lb and lb not in seen:
            seen.append(lb)
    return seen


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    env.tests["is_pick_m"] = lambda m: is_pick((m or {}).get("analysis"))
    from . import flowchart as FC
    env.tests["has_flow"] = FC.has_flow
    env.globals.update(flow_svg=lambda m: FC.svg(m, _outcome), flow_sum=lambda m: FC.summary(m, _pick_label))
    env.filters.update(tone=_tone, tone_html=_tone_html, sday=config.sales_day, match_groups=_match_groups, pct=_pct, signed=_signed, odds=_odds, won=_won, kdate=_kdate, ktime=_ktime, kdt=_kdt, slug=slug)
    env.globals.update(is_pick=is_pick, PICK_MIN=config.PICK_MIN,
        cfg=config, STRATEGIES=STRATEGIES, MARKET_LABEL=MARKET_LABEL, SPORT_LABEL=SPORT_LABEL, XSRC=("유럽 축구", "NBA", "MLB", "A매치"), mk_short=_mk_short,
        outcome=_outcome, pick_label=_pick_label, line_groups=_line_groups, upset_map=_upset_map, flow_key=_flow_key, round_label=_round_label, rounds_of=_rounds, now=config.now_kst(), asset_v=config.now_kst().strftime("%Y%m%d%H%M"),
        nav=[("/", "TODAY"), ("/analysis/", "경기 분석"), ("/leagues/", "리그·순위"), ("/odds/", "배당 분석"), ("/tool/", "금액 계산기"), ("/performance/", "성과"),
             ("/reports/", "지난 리포트"), ("/guide/", "가이드"), ("/support/", "후원")],
    )
    return env


def _season_balls(today: date) -> list[str]:
    m = today.month
    if m in (10, 11, 12, 1, 2, 3):
        return ["basketball", "volleyball"]
    if m in (4, 5, 6, 7, 8, 9):
        return ["baseball", "soccer"]
    return ["basketball", "volleyball"]


def _write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def _report_summary(r: dict) -> dict:
    """보관함용 요약: 날짜, 경기 수, 픽 적중, 조합 적중."""
    outs = r.get("outcomes") or {}
    n = hit = 0
    for m in r.get("markets", []):
        a = m.get("analysis")
        o = outs.get(m["id"])
        if a and o and o != "VOID":
            n += 1
            hit += int(o == a["pick"])
    cw = cl = 0
    for cs in (r.get("combos") or {}).values():
        for c in cs:
            if c.get("result") == "win":
                cw += 1
            elif c.get("result") == "lose":
                cl += 1
    return {"date": r["date"], "matches": r["stats"]["matches"], "combos": r["stats"]["combos"], "graded": n,
            "hit": hit, "combo_win": cw, "combo_lose": cl, "headline": r.get("headline", ""), "demo": r.get("demo")}


def _leagues(reports: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in reports:
        outs = r.get("outcomes") or {}
        for m in r.get("markets", []):
            lg = out.setdefault(m["league"], {"name": m["league"], "slug": slug(m["league"]), "sport": m["sport"],
                                              "n": 0, "graded": 0, "hit": 0, "teams": defaultdict(int), "recent": []})
            lg["n"] += 1
            lg["teams"][m["home"]] += 1
            lg["teams"][m["away"]] += 1
            a = m.get("analysis")
            o = outs.get(m["id"])
            if a and o and o != "VOID":
                lg["graded"] += 1
                lg["hit"] += int(o == a["pick"])
            if len(lg["recent"]) < 40:
                lg["recent"].append({**m, "date": r["date"], "result": o})
    for lg in out.values():
        lg["teams"] = sorted(lg["teams"].items(), key=lambda kv: -kv[1])
        lg["recent"].sort(key=lambda m: m["kickoff"], reverse=True)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["n"]))


def _mk_short(m: dict) -> str:
    """마켓 짧은 이름: 승무패 / 승패 / 핸디캡 -1 / 언더오버 2.5"""
    if m["market"] == "HANDICAP":
        return f"핸디캡 {m.get('line') or 0:+g}"
    if m["market"] == "OU":
        return f"언더오버 {m.get('line') or 0:g}"
    return MARKET_LABEL.get(m["market"], m["market"])


_MK_ORDER = {"1X2": 0, "WL": 1, "HANDICAP": 2, "OU": 3}


def _match_groups(markets: list[dict]) -> list[dict]:
    """같은 경기(시각·홈·원정)의 승무패·핸디캡·언더오버를 한 묶음으로. 경기 목록 순서는 그대로."""
    groups: dict[tuple, dict] = {}
    for m in markets:
        key = (m["kickoff"][:16], m["home"], m["away"])
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": "|".join(key), "sport": m["sport"], "kickoff": m["kickoff"], "home": m["home"], "away": m["away"],
                               "league": m["league"], "round": m.get("round"), "markets": []}
        g["markets"].append(m)
    out = []
    for g in groups.values():
        g["markets"].sort(key=lambda m: (_MK_ORDER.get(m["market"], 9), m.get("line") or 0))
        g["main"] = next((m for m in g["markets"] if m.get("analysis")), g["markets"][0])
        g["game_no"] = g["main"].get("game_no")
        out.append(g)
    return out


def _slip_payload(r: dict | None) -> dict:
    """조합 계산기·내 조합 기능용 최소 데이터."""
    if not r:
        return {"date": None, "legs": []}
    legs = []
    for m in r.get("markets", []):
        a = m.get("analysis")
        if not a or not m.get("odds") or m["kickoff"] <= config.now_kst().isoformat():
            continue  # 이미 시작한 경기는 담을 수 없다
        for k, o in m["odds"].items():
            legs.append({"id": f"{m['id']}|{k}", "match": f"{m['kickoff'][:10]}|{m['home']}|{m['away']}", "league": m["league"],
                         "label": f"{m['home']} vs {m['away']}", "pick": _outcome(m, k), "odds": o,
                         "p": a["p"].get(k), "ko": m["kickoff"], "no": m.get("game_no"), "rd": str(m.get("round") or ""), "mk": m["market"] + str(m.get("line") or ""),
                         "mkl": MARKET_LABEL.get(m["market"], "") + (f" {m['line']:+g}" if m.get("line") is not None else "")})
    return {"date": r["date"], "legs": legs}


def _xbook_payload(r: dict | None) -> dict:
    """배당 분석 계산기용: 해외 기록 구도표 + 오늘 경기의 해외 배당(승패·해외 핸디·해외 합계, 불러오기용)."""
    from ..analysis import xbook
    out = xbook.page_payload(xbook.load())
    games: dict[str, dict] = {}
    now = config.now_kst().isoformat()
    for m in (r or {}).get("markets", []):
        x = m.get("x") or {}
        if m.get("sport") not in ("soccer", "basketball", "baseball") or not x.get("h2h") or m["kickoff"] <= now:
            continue
        g = games.setdefault(f"{m['kickoff']}|{m['home']}|{m['away']}", {
            "sport": m["sport"], "label": f"{m['home']} vs {m['away']}", "league": m["league"], "ko": m["kickoff"],
            "h2h": x.get("h2h_odds") or {k: round(1 / v, 2) for k, v in x["h2h"].items() if v > 0},
            "spread": x.get("spread"), "total": x.get("total")})
    out["today"] = sorted(games.values(), key=lambda g: g["ko"])
    # 베트맨 배당 기록(해외 기록이 없는 리그용) + 오늘 경기의 베트맨 배당(불러오기용)
    try:
        from ..analysis import bbook
        from ..sources import betman_history
        bk = bbook.build(betman_history.load_all())
        out["bb"] = {"w": bk["w"], "need": bk["need"], "min_group": bk["min_group"], "groups": bk["groups"], "data": bk["data"]}
        bgames: dict[str, dict] = {}
        for m in (r or {}).get("markets", []):
            grp = bbook.group_of(m.get("sport"), m.get("league"))
            if not grp or m["kickoff"] <= now or not m.get("odds"):
                continue
            g = bgames.setdefault(f"{m['kickoff']}|{m['home']}|{m['away']}", {
                "sport": m["sport"], "grp": grp, "label": f"{m['home']} vs {m['away']}", "league": m["league"], "ko": m["kickoff"], "bm": {}})
            mk = "WL" if m["market"] == "1X2" else m["market"]
            g["bm"][mk] = {**m["odds"], "line": m.get("line")}
        out["btoday"] = sorted(bgames.values(), key=lambda g: g["ko"])
    except Exception:  # noqa: BLE001
        log.exception("베트맨 기록 구도표 실패")
    return out


def _jsonld(*objs) -> list[str]:
    """JSON-LD 문자열. </script> 조기 종료를 막기 위해 '</' 를 이스케이프."""
    return [json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") for o in objs if o]


def _org() -> dict:
    return {"@type": "Organization", "@id": config.SITE_URL + "/#org", "name": config.SITE_NAME,
            "url": config.SITE_URL + "/", "logo": config.SITE_URL + "/static/og.png"}


def _crumbs(items: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": config.SITE_URL + u} for i, (n, u) in enumerate(items)]}


def _leagues_of(r: dict, n: int = 3) -> list[str]:
    from collections import Counter
    c = Counter((m["league"]) for m in r.get("markets", []))
    return [k for k, _ in c.most_common(n)]


def _matches(r: dict) -> list[dict]:
    """리포트의 마켓을 경기 단위로 묶는다(승패·핸디·언오버가 한 경기)."""
    groups: dict[str, dict] = {}
    for m in r.get("markets", []):
        key = f"{m['kickoff'][:10]}|{m['home']}|{m['away']}"
        g = groups.get(key)
        if not g:
            g = groups[key] = {"key": key, "date": r["date"], "kickoff": m["kickoff"], "league": m["league"],
                               "sport": m["sport"], "home": m["home"], "away": m["away"], "venue": m.get("venue"),
                               "markets": [], "no": m.get("game_no")}
        g["markets"].append(m)
    used: set[str] = set()
    out = []
    for g in sorted(groups.values(), key=lambda g: (g["kickoff"], g["no"] or 0)):
        base = slug(f"{g['home']} vs {g['away']}")
        sl = base if base not in used else f"{base}-{g['no']}"
        used.add(sl)
        g["slug"] = sl
        g["url"] = f"/matches/{r['date']}/{sl}/"
        order = {"1X2": 0, "WL": 1, "HANDICAP": 2, "OU": 3}
        g["markets"].sort(key=lambda m: order.get(m["market"], 9))
        g["main"] = next((m for m in g["markets"] if m.get("analysis")), None)
        out.append(g)
    return out


def _event_ld(g: dict) -> dict:
    ev = {"@type": "SportsEvent", "name": f"{g['home']} vs {g['away']}", "startDate": g["kickoff"],
          "sport": SPORT_LABEL.get(g["sport"], ""), "eventStatus": "https://schema.org/EventScheduled",
          "homeTeam": {"@type": "SportsTeam", "name": g["home"]}, "awayTeam": {"@type": "SportsTeam", "name": g["away"]},
          "competitor": [{"@type": "SportsTeam", "name": g["home"]}, {"@type": "SportsTeam", "name": g["away"]}],
          "url": config.SITE_URL + g["url"], "description": f"{g['league']} {g['home']} 대 {g['away']} 경기 분석"}
    if g.get("venue"):
        ev["location"] = {"@type": "Place", "name": g["venue"]}
    return ev


def _article_ld(title: str, desc: str, url: str, published: str, modified: str) -> dict:
    return {"@context": "https://schema.org", "@type": "Article", "headline": title[:110], "description": desc,
            "inLanguage": "ko-KR", "mainEntityOfPage": config.SITE_URL + url, "datePublished": published,
            "dateModified": modified, "author": _org(), "publisher": _org(), "image": [config.SITE_URL + "/static/og.png"]}


def build() -> None:
    env = _env()
    reports = []
    for p in sorted(config.REPORTS.glob("*.json"), reverse=True):
        r = read_json(p)
        if r and r.get("date"):
            reports.append(r)
    # 예전 문구 규칙으로 저장된 설명(기대값 마이너스 등)은 지금 규칙으로 다시 쓴다. 다시 못 쓰면 그 문장만 뺀다.
    from ..analysis.narrative import describe as _describe
    for r in reports:
        for m in r.get("markets") or []:
            nv = m.get("narrative")
            if nv and "기대값" in nv:
                try:
                    m["narrative"] = _describe(m) if m.get("analysis") else None
                except Exception:  # noqa: BLE001
                    m["narrative"] = None
                if m.get("narrative") and "기대값" in m["narrative"]:
                    m["narrative"] = " ".join(x for x in re.split(r"(?<=\.)\s+", m["narrative"]) if "기대값" not in x) or None
    perf = load_perf()
    today = date.fromisoformat(config.today_kst())
    # 다음 구매일 리포트는 19시부터 '내일 분석'으로 공개(첫 화면은 23시 전환까지 오늘 그대로)
    tomorrow = (today + timedelta(days=1)).isoformat()
    show_next = config.now_kst().hour >= 19
    reports = [r for r in reports if r["date"] <= today.isoformat() or (show_next and r["date"] == tomorrow)]
    latest = next((r for r in reports if r["date"] <= today.isoformat()), reports[0] if reports else None)
    is_demo = any(r.get("demo") for r in reports[:1])

    if config.DIST.exists():
        shutil.rmtree(config.DIST)
    config.DIST.mkdir(parents=True)
    shutil.copytree(HERE / "static", config.DIST / "static")
    # 루트에 그대로 두어야 하는 파일(검색엔진 소유 확인 파일 등)
    for f in (HERE / "root").glob("*"):
        if f.is_file():
            shutil.copy2(f, config.DIST / f.name)

    from . import og as OG, og_pages as OGP
    try:
        OG.default(config.DIST / "og" / "default.jpg")
        for name, size, mask in (("icon-192.png", 192, False), ("icon-512.png", 512, False), ("icon-maskable-512.png", 512, True), ("apple-touch-icon.png", 180, True)):
            OG.icon(config.DIST / name, size, maskable=mask)
    except Exception:  # noqa: BLE001
        log.exception("기본 미리보기·아이콘 생성 실패(기존 파일 사용)")
    summaries = [_report_summary(r) for r in reports]
    leagues = _leagues(reports[:60])
    # 회차별·팀별 페이지 데이터, 경기 페이지 주소표(최근 45일분만 경기 페이지가 있다)
    from . import pages_extra as PX
    from ..sources import betman_history
    murl: dict[tuple, str] = {}
    for r in reports[:45]:
        for g in _matches(r):
            murl.setdefault((g["home"], g["away"], g["kickoff"][:10]), g["url"])
    try:
        from ..pipeline import results_path
        hrows = betman_history.load_all()
        rbd = {r["date"]: read_json(results_path(r["date"]), {}) or {} for r in reports[:30]}
        hrows = PX.rows_from_results(reports, rbd) + hrows  # 최근 결과가 앞(중복이면 이것이 남는다)
        tms = PX.teams(hrows, reports, config.now_kst().isoformat())
        tables = PX.standings(hrows, config.now_kst())
        vns = PX.venues(reports)
        lgames = PX.league_games(hrows)
    except Exception:  # noqa: BLE001
        log.exception("팀·순위 데이터 실패")
        tms, tables, vns, lgames = {}, {}, {}, {}
    # 끝난 경기 점수판(쿼터·이닝·전후반, 골 기록)
    from ..sources import boxscore
    try:
        boxes = boxscore.load_all()
    except Exception:  # noqa: BLE001
        log.exception("점수판 읽기 실패")
        boxes = {}

    def box_of(key=None, date=None, home=None, away=None):
        return boxes.get(key or f"{date}|{home}|{away}")
    for t in tms.values():
        tb = tables.get(PX.lkey(t["league"]))
        t["table_slug"] = slug(tb["name"]) if tb else None
        t["intro"] = PX.team_intro(t, tb, vns.get((t["sport"], PX.lkey(t["name"]))))
        me = next((r for r in tb["rows"] if PX.lkey(r["team"]) == PX.lkey(t["name"])), None) if tb else None
        t["rank"] = (me["rank"], len(tb["rows"]), tb["name"], tb["season"]) if me else None
        t["season_rec"] = me
        # 지구·콘퍼런스가 있는 리그(NBA·MLB 등)는 그 안의 순위를 짧은 표시로 쓴다(예: 서부 3위)
        t["rank_short"] = f"{me['rank']}위" if me else None
        for grp in (tb or {}).get("groups") or []:
            gm = next((r for r in grp["rows"] if PX.lkey(r["team"]) == PX.lkey(t["name"])), None)
            if gm:
                t["rank_short"] = f"{grp['name'].replace(' 콘퍼런스', '')} {gm['rank']}위"
    turl = {(t["sport"], a): t["url"] for t in tms.values() for a in t["aliases"]}
    rds = PX.rounds(reports)

    def team_link(sport, name):
        return turl.get((sport, name))

    tinfo = {(t["sport"], a): t for t in tms.values() for a in t["aliases"]}

    def team_info(sport, name):
        return tinfo.get((sport, name))

    def insights(g):
        try:
            return INS.build(g, team_info(g["sport"], g["home"]), team_info(g["sport"], g["away"]))
        except Exception:  # noqa: BLE001
            log.exception("숫자 비교 실패")
            return None

    def predict(g):
        try:
            return INS.predict(g, team_info(g["sport"], g["home"]), team_info(g["sport"], g["away"]))
        except Exception:  # noqa: BLE001
            return None

    def recent5(g, side):
        return INS.recent5(team_info(g["sport"], g[side]), g["kickoff"])

    def match_url(m):
        return murl.get((m.get("home"), m.get("away"), str(m.get("kickoff"))[:10])) if m else None

    ctx = dict(perf=perf, demo=is_demo, balls=_season_balls(today), summaries=summaries, leagues=leagues,
               team_link=team_link, match_url=match_url, team_info=team_info, box_of=box_of, insights=insights, recent5=recent5, predict=predict)
    urls: list[tuple[str, str]] = []

    def page(tpl: str, out: str, **kw):
        html = env.get_template(tpl).render(**ctx, path=out, **kw)
        _write(config.DIST / out.strip("/") / "index.html" if out != "/" else config.DIST / "index.html", html)
        urls.append((out, kw.get("lastmod") or today.isoformat()))

    site_ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "@id": config.SITE_URL + "/#site", "name": config.SITE_NAME, "alternateName": config.SITE_DOMAIN_DISPLAY,
         "url": config.SITE_URL + "/", "inLanguage": "ko-KR", "publisher": {"@id": config.SITE_URL + "/#org"}}, _org()]}

    def report_ld(r, url):
        if not r:
            return []
        ms = _matches(r)
        title = f"{_kdate(r['date'])} 프로토 승부식 분석"
        items = {"@context": "https://schema.org", "@type": "ItemList", "name": title, "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "item": _event_ld(g)} for i, g in enumerate(ms[:40])]}
        return _jsonld(_article_ld(title, r.get("headline", ""), url, r.get("generated_at") or r["date"], r.get("updated_at") or r["date"]),
                       items, _crumbs([("홈", "/"), ("지난 리포트", "/reports/"), (_kdate(r["date"]), f"/reports/{r['date']}/")]))

    next_rep = next((r for r in reports if r["date"] > today.isoformat()), None)
    # 다음 구매일: 19시 전에는 날짜와(알 수 있으면) 회차만, 19시 뒤에는 분석 요약
    guess_rounds = []
    if latest:
        today_rounds = {m.get("round") for m in latest.get("markets", []) if not m.get("preview")}
        guess_rounds = sorted({_round_label(m.get("round")) for m in latest.get("markets", []) if m.get("preview") and m.get("round") not in today_rounds} - {""})
    next_guess = {"date": tomorrow, "rounds": guess_rounds}
    home_og = OGP.report(config.DIST, "/", latest, f"{_kdate(latest['date'])} 프로토 분석",
                         "TODAY · 프로토 승부식 " + " · ".join(_rounds(latest))) if latest and latest.get("markets") else None
    page("report.html", "/", og_image=home_og, r=latest, is_home=True, next_day=(next_rep or {}).get("date"), nxt=next_rep, next_guess=next_guess, lastmod=(latest or {}).get("date"),
         matches=_matches(latest) if latest else [], leagues_top=_leagues_of(latest) if latest else [],
         jsonld=_jsonld(site_ld) + report_ld(latest, "/"))
    # 경기 분석: 최근 리포트들에서 아직 시작하지 않은 경기 전부(같은 경기는 최신 리포트 것), 시작 날짜별로 묶는다
    an_secs = []
    nowk = config.now_kst().strftime("%Y-%m-%dT%H:%M")
    seen_g: dict = {}
    for r in sorted([x for x in reports if x["date"] >= (today - timedelta(days=2)).isoformat()], key=lambda x: x["date"]):
        for g in _matches(r):
            if str(g["kickoff"])[:16] > nowk:
                seen_g[(g["home"], g["away"], str(g["kickoff"])[:10])] = g
    by_day: dict = {}
    for g in sorted(seen_g.values(), key=lambda g: (g["kickoff"], g["no"] or 0)):
        by_day.setdefault(str(g["kickoff"])[:10], []).append(g)
    for d, gs in by_day.items():
        an_secs.append({"title": _kdate(d), "games": gs})
    page("analysis.html", "/analysis/", sections=an_secs, lastmod=(latest or {}).get("date"))
    rss_items = []
    for i, r in enumerate(reports):
        prev_d = reports[i + 1]["date"] if i + 1 < len(reports) else None
        next_d = reports[i - 1]["date"] if i > 0 else None
        ms = _matches(r)
        url = f"/reports/{r['date']}/"
        rog = OGP.report(config.DIST, url, r, f"{_kdate(r['date'])} 프로토 분석", "프로토 승부식 " + " · ".join(_rounds(r))) if i < 14 and r.get("markets") else None
        page("report.html", url, og_image=rog, r=r, is_home=False, prev_d=prev_d, next_d=next_d, lastmod=r["date"],
             matches=ms, leagues_top=_leagues_of(r), jsonld=report_ld(r, url))
        if i < 30:
            rss_items.append({"title": f"{_kdate(r['date'])} 프로토 승부식 분석 · {' · '.join(_leagues_of(r))}",
                              "url": url, "desc": r.get("headline", ""), "date": r.get("generated_at") or r["date"] + "T06:00:00+09:00"})
        if i < 45:  # 경기 페이지는 최근 45일분만 생성(빌드 시간·저장소 크기 보호)
            outs = r.get("outcomes") or {}
            for g in ms:
                title = f"{g['home']} vs {g['away']} 분석 · {g['league']} {_kdt(g['kickoff'])}"
                main = g.get("main")
                desc = (main or {}).get("narrative") or f"{g['league']} {g['home']} 대 {g['away']} 경기 분석"
                ld = _jsonld({"@context": "https://schema.org", **_event_ld(g)},
                             _article_ld(title, desc[:160], g["url"], r.get("generated_at") or r["date"], r.get("updated_at") or r["date"]),
                             _crumbs([("홈", "/"), (_kdate(r["date"]), url), (f"{g['home']} vs {g['away']}", g["url"])]))
                mog = OGP.match(config.DIST, g, _round_label((g.get("main") or g["markets"][0]).get("round"))) if i < 4 else None
                page("match.html", g["url"], og_image=mog, g=g, r=r, outs=outs, lastmod=r["date"], jsonld=ld, page_title=title, page_desc=desc[:155])
    page("archive.html", "/reports/")
    # 회차별 분석
    page("rounds.html", "/rounds/", rounds=rds)
    rkeys = list(rds)
    for i, ts in enumerate(rkeys):
        ro = rds[ts]
        page("round.html", f"/rounds/{ts}/", og_image=OGP.round_(config.DIST, f"/rounds/{ts}/", ro), ro=ro, prev_ro=rkeys[i + 1] if i + 1 < len(rkeys) else None,
             next_ro=rkeys[i - 1] if i > 0 else None, lastmod=ro["dates"][-1] if ro["dates"] else None,
             jsonld=_jsonld(_crumbs([("홈", "/"), ("회차별 분석", "/rounds/"), (f"{ro['year']}년 {ro['label']}", f"/rounds/{ts}/")])))
    # 팀별 기록
    page("teams.html", "/teams/", groups=PX.team_groups(tms))
    for t in tms.values():
        page("team.html", t["url"], og_image=OGP.team(config.DIST, t), t=t, lastmod=(t["games"][0]["date"] if t["games"] else None),
             jsonld=_jsonld({"@context": "https://schema.org", "@type": "SportsTeam", "name": t["name"], "sport": SPORT_LABEL.get(t["sport"], t["sport"]),
                             "url": config.SITE_URL + t["url"]},
                            _crumbs([("홈", "/"), ("팀별 기록", "/teams/"), (t["name"], t["url"])])))
    # 리그 페이지에 순위표를 붙인다(최근 리포트에 없는 리그도 순위표가 있으면 페이지를 만든다)
    by_key = {PX.lkey(lg["name"]): lg for lg in leagues.values()}
    for lk, tb in tables.items():
        lg = by_key.get(lk)
        if not lg:
            lg = {"name": tb["name"], "slug": slug(tb["name"]), "sport": tb["sport"], "n": 0, "graded": 0, "hit": 0, "teams": [], "recent": []}
            leagues[tb["name"]] = lg
        lg["table"] = tb
    for lg in leagues.values():
        lg["games"] = lgames.get(PX.lkey(lg["name"]), [])
    # 지금 발매 중인 리그(오늘·다음 구매일 리포트에 경기가 있는 리그)
    live_lg = {PX.lkey(m["league"]) for r in reports if r["date"] >= today.isoformat() for m in r.get("markets", [])}
    page("leagues.html", "/leagues/", live_lg=live_lg, lkey=PX.lkey)
    for lg in leagues.values():
        page("league.html", f"/leagues/{lg['slug']}/", og_image=OGP.league(config.DIST, f"/leagues/{lg['slug']}/", lg), lg=lg,
             jsonld=_jsonld(_crumbs([("홈", "/"), ("리그별 기록", "/leagues/"), (lg["name"], f"/leagues/{lg['slug']}/")])))
    # 성과: 종목별·마켓별·확률 구간별(발행된 모든 픽, 적중특례 제외)
    brk = {"sport": defaultdict(lambda: [0, 0, 0.0]), "market": defaultdict(lambda: [0, 0, 0.0]), "band": defaultdict(lambda: [0, 0, 0.0])}
    for r in reports:
        outs = r.get("outcomes") or {}
        for m in r.get("markets", []):
            a, o = m.get("analysis"), outs.get(m["id"])
            if not a or not o or o == "VOID" or m.get("preview") or not is_pick(a):
                continue
            hit, pp = int(o == a["pick"]), a["pick_prob"]
            band = "70% 이상" if pp >= 0.7 else ("60~70%" if pp >= 0.6 else ("50~60%" if pp >= 0.5 else "50% 미만"))
            mk = MARKET_LABEL.get("WL" if m["market"] == "1X2" else m["market"], m["market"])
            for k, v in (("sport", SPORT_LABEL.get(m["sport"], m["sport"])), ("market", mk), ("band", band)):
                c = brk[k][v]
                c[0] += 1
                c[1] += hit
                c[2] += pp
    perf_brk = {k: [{"name": n, "n": c[0], "hit": c[1] / c[0], "exp": c[2] / c[0]} for n, c in sorted(v.items(), key=lambda kv: -kv[1][0])]
                for k, v in brk.items()}
    order = ["70% 이상", "60~70%", "50~60%", "50% 미만"]
    perf_brk["band"].sort(key=lambda x: order.index(x["name"]) if x["name"] in order else 9)
    page("performance.html", "/performance/", brk=perf_brk)
    page("tool.html", "/tool/", jsonld=_jsonld({'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': '켈리 기준(Kelly Criterion)이란 무엇인가요?', 'acceptedAnswer': {'@type': 'Answer', 'text': '가진 자금 중 몇 %를 걸어야 장기적으로 자금이 가장 빨리 불어나는지 알려주는 공식입니다. 1956년 벨 연구소의 존 L. 켈리 주니어가 발표했습니다. 베팅 비율 = (적중 확률 × 배당 − 1) ÷ (배당 − 1).'}}, {'@type': 'Question', 'name': '왜 켈리 금액의 1/4만 거나요?', 'acceptedAnswer': {'@type': 'Answer', 'text': '스포츠 경기의 적중 확률은 추정값이라 오차가 있습니다. 1/4 켈리는 성장 속도를 약 44%로 낮추는 대신 자금 변동을 1/4로 줄여 안전합니다. 이 계산기는 1/4 켈리에 시드의 10%와 1회 100,000원 상한을 둡니다.'}}, {'@type': 'Question', 'name': '켈리 기준으로 시드를 키우면 어디까지 커지나요?', 'acceptedAnswer': {'@type': 'Answer', 'text': '시드 × 베팅 비율이 베트맨 1회차 구매 한도 100,000원에 닿을 때까지는 거는 금액이 시드와 함께 커져 복리로 불어납니다(예: 비율 5%면 시드 200만 원까지). 그 뒤로는 한 회차 금액이 10만 원에서 멈추므로 기대 수익은 회차 수(1주일 약 3회차)만큼만 늘어납니다.'}}, {'@type': 'Question', 'name': '켈리 크리테온과 켈리 기준은 같은 말인가요?', 'acceptedAnswer': {'@type': 'Answer', 'text': "네, 모두 Kelly Criterion을 가리킵니다. 영어 발음은 '크라이테리언'에 가깝고, 우리말로는 '켈리 기준'이 가장 많이 쓰입니다."}}]}))
    for name in ("method", "guide", "about", "privacy", "terms", "contact", "responsible", "odds", "support"):
        page(f"{name}.html", f"/{name}/")

    # 쓰레드 프로필 링크 전용 주소: 방문 통계에서 /t/ 조회수 = 쓰레드에서 넘어온 수. 바로 첫 화면으로 보낸다(검색 제외)
    _write(config.DIST / "t" / "index.html",
           '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
           f'<link rel="canonical" href="{config.SITE_URL}/"><meta http-equiv="refresh" content="2;url=/">'
           '<title>스포츠분석.kr</title><style>body{margin:0;background:#0f1117;color:#8a90a6;font:14px sans-serif;display:grid;place-items:center;height:100vh}</style></head>'
           '<body>스포츠분석.kr로 이동합니다…<script>addEventListener("load",function(){setTimeout(function(){location.replace("/")},500)})</script></body></html>')
    _write(config.DIST / "404.html", env.get_template("404.html").render(**ctx, path="/404"))
    write_json(config.DIST / "data" / "today.json", _slip_payload(latest))
    # 알림 내용(서비스 워커가 알림 신호를 받으면 이 파일을 읽어 띄운다)
    try:
        nr = next_rep if (next_rep and next_rep.get("markets")) else None
        src = nr or latest or {}
        ms = [m for m in src.get("markets", []) if not m.get("preview")]
        ngames = len({(m["home"], m["away"]) for m in ms})
        first = min((m["kickoff"] for m in ms), default=None)
        tp = (src.get("top_picks") or [None])[0]
        body = f"{ngames}경기" + (f" · 첫 경기 {_kdt(first)}" if first else "")
        if tp:
            body += f" · {tp['home']} vs {tp['away']} {_outcome(tp, tp['outcome'])} {round(tp['p'] * 100)}%"
        write_json(config.DIST / "data" / "push.json", {
            "title": f"{_kdate(src['date'])} 프로토 분석 공개" if src.get("date") else "스포츠분석",
            "body": body, "url": "/", "tag": f"day-{src.get('date', '')}"})
    except Exception:  # noqa: BLE001
        log.exception("알림 내용 생성 실패")
    write_json(config.DIST / "data" / "xbook.json", _xbook_payload(latest))
    # 쓰레드 카드 이미지(쓰레드가 공개 주소로 가져간다)
    tdir = config.DATA / "threads"
    if tdir.exists():
        (config.DIST / "threads").mkdir(parents=True, exist_ok=True)
        for f in tdir.glob("*.jpg"):
            shutil.copy2(f, config.DIST / "threads" / f.name)
    _write(config.DIST / "sitemap.xml", env.get_template("sitemap.xml").render(urls=urls))
    _write(config.DIST / "robots.txt", f"User-agent: *\nAllow: /\nDisallow: /data/\n\nSitemap: {config.SITE_URL}/sitemap.xml\n")
    _write(config.DIST / "rss.xml", env.get_template("rss.xml").render(
        items=[{**it, "pub": format_datetime(datetime.fromisoformat(it["date"]))} for it in rss_items],
        built=format_datetime(config.now_kst())))
    if config.INDEXNOW_KEY:
        _write(config.DIST / f"{config.INDEXNOW_KEY}.txt", config.INDEXNOW_KEY)
    write_json(config.DIST / "data" / "urls.json", [u for u, _ in urls])
    if config.ADSENSE_CLIENT:
        pub = config.ADSENSE_CLIENT.replace("ca-", "")
        _write(config.DIST / "ads.txt", f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n")
    _write(config.DIST / "_headers", (HERE / "headers.txt").read_text(encoding="utf-8"))
    log.info("빌드 완료: %d 페이지 → %s", len(urls), config.DIST)
