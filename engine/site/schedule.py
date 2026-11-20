"""경기 일정 페이지(한국 시간): '해외축구 경기 일정', 'NBA 경기 일정', 'KBL 경기 일정' 같은 검색에 맞춘 페이지.

베트맨에 발매된 경기(앞으로 2~3일)를 매일 자동으로 모은다. 경기 분석 페이지가 있으면 바로 잇는다.
일정만 보여 주고 픽은 넣지 않는다(분석 공개 시각 규칙과 무관하게 언제나 보여 줄 수 있다).
"""
from __future__ import annotations

from datetime import datetime, timedelta

WEEK = "월화수목금토일"

# key → (검색 키워드, 짧은 이름, 설명용 리그 예시, 언제나 페이지를 만들지)
CATS: dict[str, dict] = {
    "soccer": {"kw": "해외축구 경기 일정", "alt": ["해외축구 일정", "해외축구일정", "해외축구 경기일정"], "short": "해외축구",
               "ex": "프리미어리그·라리가·세리에A·분데스리가·리그1·챔피언스리그", "always": True, "sport": "soccer"},
    "kleague": {"kw": "K리그 경기 일정", "alt": ["K리그 일정", "K리그1 일정"], "short": "K리그", "ex": "K리그1·K리그2",
                "always": True, "sport": "soccer"},
    "nba": {"kw": "NBA 경기 일정", "alt": ["NBA 일정", "NBA 경기일정"], "short": "NBA", "ex": "NBA 정규시즌",
            "always": True, "sport": "basketball"},
    "kbl": {"kw": "KBL 경기 일정", "alt": ["KBL 일정", "프로농구 일정"], "short": "KBL", "ex": "KBL 프로농구",
            "always": True, "sport": "basketball"},
    "wkbl": {"kw": "WKBL 경기 일정", "alt": ["WKBL 일정", "여자프로농구 일정"], "short": "WKBL", "ex": "WKBL 여자프로농구",
             "always": False, "sport": "basketball"},
    "volleyball": {"kw": "배구 경기 일정", "alt": ["V리그 일정", "프로배구 일정"], "short": "배구", "ex": "V리그 남자부·여자부",
                   "always": True, "sport": "volleyball"},
    "basketball": {"kw": "농구 경기 일정", "alt": ["농구 일정"], "short": "농구", "ex": "국제 농구·아시아 리그",
                   "always": False, "sport": "basketball"},
    "baseball": {"kw": "야구 경기 일정", "alt": ["야구 일정", "KBO 일정", "MLB 일정"], "short": "야구", "ex": "KBO·MLB·NPB",
                 "always": False, "sport": "baseball"},
}


def cat_of(m: dict) -> str | None:
    sp, lg = m.get("sport"), str(m.get("league") or "")
    if sp == "soccer":
        return "kleague" if lg.startswith("K리그") else "soccer"
    if sp == "basketball":
        return {"NBA": "nba", "KBL": "kbl", "WKBL": "wkbl"}.get(lg, "basketball")
    if sp == "volleyball":
        return "volleyball"
    if sp == "baseball":
        return "baseball"
    return None


def kday(d: str) -> str:
    t = datetime.fromisoformat(d)
    return f"{t.month}월 {t.day}일 ({WEEK[t.weekday()]})"


def build(reports: list[dict], now: datetime, murl: dict) -> dict[str, dict]:
    """key → {cat, days: [(날짜, [ (리그, [경기...]) ])], n, leagues: Counter 순서 목록}."""
    seen: dict[tuple, dict] = {}
    cut = now - timedelta(hours=2)  # 막 시작한 경기까지(진행 중)
    for r in reports:
        for m in r.get("markets") or []:
            try:
                ko = datetime.fromisoformat(m["kickoff"])
            except (KeyError, ValueError, TypeError):
                continue
            if ko < cut or ko > now + timedelta(days=4):
                continue
            key = (m.get("home"), m.get("away"), m["kickoff"][:16])
            g = seen.get(key)
            if not g:
                g = seen[key] = {"home": m.get("home"), "away": m.get("away"), "kickoff": m["kickoff"], "league": m.get("league"),
                                 "sport": m.get("sport"), "round": m.get("round"), "no": m.get("game_no"), "odds": None, "mk": None,
                                 "url": murl.get((m.get("home"), m.get("away"), m["kickoff"][:10]))}
            # 화면 배당은 베트맨: 승무패(축구) → 승패 순으로 대표 배당
            if m.get("market") in ("1X2", "WL") and m.get("odds") and (g["mk"] != "1X2"):
                g["odds"], g["mk"] = m["odds"], m["market"]
    out: dict[str, dict] = {}
    for g in seen.values():
        c = cat_of(g)
        if not c:
            continue
        out.setdefault(c, {"games": []})["games"].append(g)
    res = {}
    for c, info in CATS.items():
        games = sorted((out.get(c) or {}).get("games", []), key=lambda g: (g["kickoff"], g["no"] or 0))
        if not games and not info["always"]:
            continue
        days: dict[str, dict[str, list]] = {}
        lg_n: dict[str, int] = {}
        for g in games:
            d = g["kickoff"][:10]
            days.setdefault(d, {}).setdefault(g["league"], []).append(g)
            lg_n[g["league"]] = lg_n.get(g["league"], 0) + 1
        res[c] = {"key": c, **info, "url": f"/schedule/{c}/", "n": len(games),
                  "days": [(d, kday(d), sorted(lgs.items(), key=lambda kv: kv[1][0]["kickoff"])) for d, lgs in sorted(days.items())],
                  "leagues": sorted(lg_n.items(), key=lambda kv: -kv[1])}
    return res
