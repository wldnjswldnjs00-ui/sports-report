"""정적 사이트 생성기. data/ → dist/

서버 없이 HTML 파일만 만든다. 방문자가 늘어도 서버 CPU 를 쓰지 않는다.
"""
from __future__ import annotations

import json
import logging
import shutil
from collections import defaultdict
from datetime import date, datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Undefined, select_autoescape

from .. import config
from ..analysis.combos import STRATEGIES
from ..analysis.grading import load_perf
from ..schema import MARKET_LABEL, OUTCOME_LABEL, SPORT_LABEL
from ..util import read_json, slug, write_json

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
    env.filters.update(sday=config.sales_day, match_groups=_match_groups, pct=_pct, signed=_signed, odds=_odds, won=_won, kdate=_kdate, ktime=_ktime, kdt=_kdt, slug=slug)
    env.globals.update(
        cfg=config, STRATEGIES=STRATEGIES, MARKET_LABEL=MARKET_LABEL, SPORT_LABEL=SPORT_LABEL, XSRC=("유럽 축구", "NBA", "MLB", "A매치"), mk_short=_mk_short,
        outcome=_outcome, flow_key=_flow_key, round_label=_round_label, rounds_of=_rounds, now=config.now_kst(), asset_v=config.now_kst().strftime("%Y%m%d%H%M"),
        nav=[("/", "오늘"), ("/odds/", "배당 분석"), ("/tool/", "금액 계산기"), ("/performance/", "성과"),
             ("/reports/", "지난 리포트"), ("/method/", "분석 방법"), ("/guide/", "가이드"), ("/support/", "후원")],
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
                         "p": a["p"].get(k), "ko": m["kickoff"], "no": m.get("game_no"), "mk": m["market"] + str(m.get("line") or ""),
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
    perf = load_perf()
    today = date.fromisoformat(config.today_kst())
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

    summaries = [_report_summary(r) for r in reports]
    leagues = _leagues(reports[:60])
    ctx = dict(perf=perf, demo=is_demo, balls=_season_balls(today), summaries=summaries, leagues=leagues)
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

    page("report.html", "/", r=latest, is_home=True, lastmod=(latest or {}).get("date"),
         matches=_matches(latest) if latest else [], leagues_top=_leagues_of(latest) if latest else [],
         jsonld=_jsonld(site_ld) + report_ld(latest, "/"))
    rss_items = []
    for i, r in enumerate(reports):
        prev_d = reports[i + 1]["date"] if i + 1 < len(reports) else None
        next_d = reports[i - 1]["date"] if i > 0 else None
        ms = _matches(r)
        url = f"/reports/{r['date']}/"
        page("report.html", url, r=r, is_home=False, prev_d=prev_d, next_d=next_d, lastmod=r["date"],
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
                page("match.html", g["url"], g=g, r=r, outs=outs, lastmod=r["date"], jsonld=ld, page_title=title, page_desc=desc[:155])
    page("archive.html", "/reports/")
    page("leagues.html", "/leagues/")
    for lg in leagues.values():
        page("league.html", f"/leagues/{lg['slug']}/", lg=lg)
    page("performance.html", "/performance/")
    page("tool.html", "/tool/")
    for name in ("method", "guide", "about", "privacy", "terms", "contact", "responsible", "odds", "support"):
        page(f"{name}.html", f"/{name}/")

    _write(config.DIST / "404.html", env.get_template("404.html").render(**ctx, path="/404"))
    write_json(config.DIST / "data" / "today.json", _slip_payload(latest))
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
