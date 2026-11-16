"""정적 사이트 생성기. data/ → dist/

서버 없이 HTML 파일만 만든다. 방문자가 늘어도 서버 CPU 를 쓰지 않는다.
"""
from __future__ import annotations

import json
import logging
import shutil
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import config
from ..analysis.combos import STRATEGIES
from ..analysis.grading import load_perf
from ..schema import MARKET_LABEL, OUTCOME_LABEL, SPORT_LABEL
from ..util import read_json, slug, write_json

log = logging.getLogger("engine.build")
HERE = Path(__file__).resolve().parent
WEEK = "월화수목금토일"


def _pct(x, d=0):
    return "–" if x is None else f"{x * 100:.{d}f}%"


def _signed(x, d=1):
    return "–" if x is None else f"{x * 100:+.{d}f}%"


def _odds(x):
    return "–" if not x else f"{x:.2f}"


def _won(x):
    return "–" if x is None else f"{int(x):,}원"


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


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    env.filters.update(pct=_pct, signed=_signed, odds=_odds, won=_won, kdate=_kdate, ktime=_ktime, kdt=_kdt, slug=slug)
    env.globals.update(
        cfg=config, STRATEGIES=STRATEGIES, MARKET_LABEL=MARKET_LABEL, SPORT_LABEL=SPORT_LABEL,
        outcome=_outcome, now=config.now_kst(), asset_v=config.now_kst().strftime("%Y%m%d%H%M"),
        nav=[("/", "오늘"), ("/reports/", "지난 리포트"), ("/leagues/", "리그"), ("/performance/", "성과"),
             ("/tool/", "조합 계산기"), ("/method/", "분석 방법"), ("/guide/", "가이드")],
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


def _slip_payload(r: dict | None) -> dict:
    """조합 계산기·내 조합 기능용 최소 데이터."""
    if not r:
        return {"date": None, "legs": []}
    legs = []
    for m in r.get("markets", []):
        a = m.get("analysis")
        if not a or not m.get("odds"):
            continue
        for k, o in m["odds"].items():
            legs.append({"id": f"{m['id']}|{k}", "match": f"{m['kickoff'][:10]}|{m['home']}|{m['away']}", "league": m["league"],
                         "label": f"{m['home']} vs {m['away']}", "pick": _outcome(m, k), "odds": o,
                         "p": a["p"].get(k), "ko": m["kickoff"], "no": m.get("game_no")})
    return {"date": r["date"], "legs": legs}


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

    summaries = [_report_summary(r) for r in reports]
    leagues = _leagues(reports[:60])
    ctx = dict(perf=perf, demo=is_demo, balls=_season_balls(today), summaries=summaries, leagues=leagues)
    urls: list[tuple[str, str]] = []

    def page(tpl: str, out: str, **kw):
        html = env.get_template(tpl).render(**ctx, path=out, **kw)
        _write(config.DIST / out.strip("/") / "index.html" if out != "/" else config.DIST / "index.html", html)
        urls.append((out, kw.get("lastmod") or today.isoformat()))

    page("report.html", "/", r=latest, is_home=True, lastmod=(latest or {}).get("date"))
    for i, r in enumerate(reports):
        prev_d = reports[i + 1]["date"] if i + 1 < len(reports) else None
        next_d = reports[i - 1]["date"] if i > 0 else None
        page("report.html", f"/reports/{r['date']}/", r=r, is_home=False, prev_d=prev_d, next_d=next_d, lastmod=r["date"])
    page("archive.html", "/reports/")
    page("leagues.html", "/leagues/")
    for lg in leagues.values():
        page("league.html", f"/leagues/{lg['slug']}/", lg=lg)
    page("performance.html", "/performance/")
    page("tool.html", "/tool/")
    for name in ("method", "guide", "about", "privacy", "terms", "contact", "responsible"):
        page(f"{name}.html", f"/{name}/")

    _write(config.DIST / "404.html", env.get_template("404.html").render(**ctx, path="/404"))
    write_json(config.DIST / "data" / "today.json", _slip_payload(latest))
    _write(config.DIST / "sitemap.xml", env.get_template("sitemap.xml").render(urls=urls))
    _write(config.DIST / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {config.SITE_URL}/sitemap.xml\n")
    if config.ADSENSE_CLIENT:
        pub = config.ADSENSE_CLIENT.replace("ca-", "")
        _write(config.DIST / "ads.txt", f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n")
    _write(config.DIST / "_headers", (HERE / "headers.txt").read_text(encoding="utf-8"))
    log.info("빌드 완료: %d 페이지 → %s", len(urls), config.DIST)
