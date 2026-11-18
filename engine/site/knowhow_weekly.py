"""노하우 '주간 리포트': 매주 자동으로 새 글을 만들어 쌓는다(한 번 만든 글은 고정, 다시 계산하지 않음).

- 지난주(월~일, 한국 시간) 베트맨 발매 경기의 실제 결과로 3편: 이변 리포트, 정배 리포트, 언더오버 리포트.
- 글 제목에 날짜를 쓰지 않고 번호를 붙인다(예: '프로토 이변 리포트 #3'). 글 안에도 날짜 대신 '이번 회차 묶음' 표현.
- 저장: data/knowhow_weekly/<주 키>.json (글 목록). 데이터 커밋으로 남아, 사이트 노하우 '주간 리포트'에 계속 쌓인다.
- 경기가 적은 주(30경기 미만)는 만들지 않는다.
"""
from __future__ import annotations

import html
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from .. import config

log = logging.getLogger("engine.kh_weekly")
DIR = config.DATA / "knowhow_weekly"
KST = timezone(timedelta(hours=9))
CAT = "주간 리포트"


def _e(s) -> str:
    return html.escape(str(s))


def _p(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.1f}%"


def _week_bounds(now: datetime) -> tuple[datetime, datetime, str]:
    """지난주 월요일 00:00 ~ 이번 주 월요일 00:00(KST), 주 키."""
    mon = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = mon - timedelta(days=7)
    y, w, _ = start.isocalendar()
    return start, mon, f"{y}w{w:02d}"


def _games(rows: list[list], start: datetime, end: datetime) -> list[dict]:
    seen, out = set(), []
    a_ms, b_ms = start.timestamp() * 1000, end.timestamp() * 1000
    ou = defaultdict(list)
    for r in rows:
        try:
            sp, lg, mk, line, l, d, rr, res, ko, under_left, h, a, hs, as_ = r[:14]
        except ValueError:
            continue
        if not ko or not (a_ms <= ko < b_ms):
            continue
        if mk == "OU" and res in (0, 2) and line is not None:
            ou[(ko, h, a)].append((line, (res == 0) == (not under_left)))
        if mk not in ("1X2", "WL") or hs is None or as_ is None or not l or not rr:
            continue
        k = (ko, h, a)
        if k in seen:
            continue
        seen.add(k)
        out.append({"sport": sp, "league": lg, "home": h, "away": a, "hs": int(hs), "as": int(as_), "oh": l, "od": d or 0, "oa": rr, "key": k})
    for g in out:
        g["ou"] = ou.get(g["key"], [])
    return out


def _table(head, rows) -> str:
    th = "".join(f'<th class="{"n" if i else ""}">{_e(x)}</th>' for i, x in enumerate(head))
    trs = "".join("<tr>" + "".join(f'<td class="{"n" if i else ""}">{_e(c)}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="tblw"><table class="tbl kh-tbl"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def _art(slug, title, lead, parts, n) -> dict:
    body = "\n".join(parts)
    import re
    chars = len(re.sub(r"<[^>]+>", "", lead + body).replace("\n", "").replace(" ", ""))
    return {"slug": slug, "title": title, "cat": CAT, "lead": lead, "league": None, "sport": None, "tags": ["주간"], "body": body,
            "chars": chars, "games": n}


def _upsets(games, no, key) -> dict | None:
    up = []
    for g in games:
        fav_home = g["oh"] < g["oa"]
        dog_odds = g["oa"] if fav_home else g["oh"]
        dog_won = (g["as"] > g["hs"]) if fav_home else (g["hs"] > g["as"])
        if dog_odds >= 2.5:
            up.append((g, dog_odds, dog_won))
    if len(up) < 15:
        return None
    hit = [x for x in up if x[2]]
    by = defaultdict(lambda: [0, 0])
    for g, o, w in up:
        by[g["league"]][0] += 1
        by[g["league"]][1] += w
    rows = sorted(([lg, f"{v[0]}", f"{v[1]}", _p(v[1] / v[0])] for lg, v in by.items() if v[0] >= 3), key=lambda r: -int(r[2]))
    top = sorted(hit, key=lambda x: -x[1])[:8]
    rate = len(hit) / len(up)
    lead = f"지난 한 주 베트맨 발매 경기에서 배당 2.5 이상 역배 {len(up)}경기 중 {len(hit)}경기({_p(rate)})가 이겼습니다."
    parts = [f"<p>{_e(lead)} 배당 2.5는 확률로 약 40%를 뜻하지만, 발행처 몫이 섞여 있어 실제로는 그보다 조금 낮게 봐야 합니다. "
             f"{'이번에는 역배가 평소보다 자주 맞은 편입니다.' if rate > 0.33 else '이번에는 역배가 평소보다 덜 맞은 편입니다.' if rate < 0.25 else '이번에는 평소 수준으로 역배가 맞았습니다.'}</p>",
             "<h2>가장 큰 이변</h2>",
             _table(["리그", "경기", "점수", "역배 배당"], [[g["league"], f"{g['home']} vs {g['away']}", f"{g['hs']}:{g['as']}", f"{o:.2f}"] for g, o, w in top]),
             "<p>배당이 높을수록 맞을 때의 충격이 큽니다. 위 경기들은 시장이 가능성을 낮게 봤지만 실제로 뒤집힌 경기입니다. 이런 경기가 한 주에 몇 개씩은 꼭 나온다는 점이, "
             "정배만 여러 개 묶은 조합이 생각보다 자주 무너지는 이유입니다.</p>",
             "<h2>리그별 역배 결과</h2>", _table(["리그", "역배 경기", "역배 승리", "적중"], rows),
             "<p>한 주의 숫자는 표본이 작아 크게 출렁입니다. 리그별로 이변이 잦은지는 노하우의 리그 비교 글처럼 여러 시즌을 합친 숫자로 판단하는 것이 정확합니다. "
             "주간 리포트는 '최근 흐름이 평소와 같은지 다른지'를 보는 용도로 쓰면 좋습니다.</p>",
             "<h2>이렇게 활용하세요</h2><p>이변이 많이 나온 리그는 다음 주에서 정배 조합에 넣는 경기 수를 줄여 보고, 이변이 적었던 리그는 정배 쪽 신뢰를 조금 더 둘 수 있습니다. "
             "다만 한 번의 흐름보다 긴 기록이 더 중요하다는 점을 함께 기억해 주세요. 만 19세 이상, 베트맨 공식 채널에서만 구매할 수 있습니다.</p>"]
    return _art(f"weekly-{key}-upsets", f"프로토 이변 리포트 #{no}", lead, parts, len(games))


def _favorites(games, no, key) -> dict | None:
    rows, tot_n, tot_h = [], 0, 0
    by = defaultdict(lambda: [0, 0, 0.0])
    for g in games:
        fav_home = g["oh"] < g["oa"]
        fo = min(g["oh"], g["oa"])
        won = (g["hs"] > g["as"]) if fav_home else (g["as"] > g["hs"])
        b = "1.5 미만" if fo < 1.5 else "1.5~1.9" if fo < 1.9 else "1.9 이상"
        by[b][0] += 1
        by[b][1] += won
        tot_n += 1
        tot_h += won
    if tot_n < 30:
        return None
    for b in ("1.5 미만", "1.5~1.9", "1.9 이상"):
        if by[b][0]:
            rows.append([b, f"{by[b][0]}", f"{by[b][1]}", _p(by[b][1] / by[b][0])])
    lg = Counter()
    lgh = Counter()
    for g in games:
        fav_home = g["oh"] < g["oa"]
        lg[g["league"]] += 1
        lgh[g["league"]] += (g["hs"] > g["as"]) if fav_home else (g["as"] > g["hs"])
    lrows = sorted(([k, f"{v}", f"{lgh[k]}", _p(lgh[k] / v)] for k, v in lg.items() if v >= 4), key=lambda r: -int(r[1]))[:12]
    rate = tot_h / tot_n
    lead = f"지난 한 주 베트맨 발매 {tot_n}경기에서 정배가 이긴 비율은 {_p(rate)}입니다."
    parts = [f"<p>{_e(lead)} 정배는 두 팀 중 배당이 낮은 쪽입니다. 무승부가 있는 축구에서는 무승부도 정배가 이기지 못한 결과에 들어갑니다. "
             f"{'지난 한 주은 정배가 단단했습니다.' if rate > 0.62 else '지난 한 주은 정배가 자주 흔들렸습니다.' if rate < 0.52 else '지난 한 주 정배 적중은 평소 수준입니다.'}</p>",
             "<h2>배당 구간별 정배</h2>", _table(["정배 배당", "경기", "정배 승리", "적중"], rows),
             "<p>배당이 낮을수록 잘 맞는 것은 당연하지만, 그 차이가 얼마나 나는지가 중요합니다. 1.5 미만 정배가 생각보다 덜 맞았다면, 낮은 배당 경기를 여러 개 묶은 조합이 "
             "지난 한 주에서 자주 깨졌다는 뜻입니다.</p>",
             "<h2>리그별 정배</h2>", _table(["리그", "경기", "정배 승리", "적중"], lrows),
             "<h2>이렇게 활용하세요</h2><p>정배 적중이 높았던 리그는 조합의 바닥으로 쓰기 좋았던 리그입니다. 다만 한 주 숫자는 출렁임이 크니, 노하우의 리그별 정배 글처럼 "
             "긴 기록과 함께 보는 것이 좋습니다. 만 19세 이상, 베트맨 공식 채널에서만 구매할 수 있습니다.</p>"]
    return _art(f"weekly-{key}-favorites", f"프로토 정배 리포트 #{no}", lead, parts, len(games))


def _overunder(games, no, key) -> dict | None:
    by = defaultdict(lambda: [0, 0])
    n = o = 0
    for g in games:
        for line, over in g["ou"]:
            by[g["league"]][0] += 1
            by[g["league"]][1] += over
            n += 1
            o += over
    if n < 30:
        return None
    rows = sorted(([lg, f"{v[0]}", _p(v[1] / v[0]), _p(1 - v[1] / v[0])] for lg, v in by.items() if v[0] >= 4), key=lambda r: -int(r[1]))[:14]
    rate = o / n
    lead = f"지난 한 주 베트맨 언더오버 {n}경기 중 오버가 {_p(rate)}, 언더가 {_p(1 - rate)}였습니다."
    parts = [f"<p>{_e(lead)} 언더오버 기준점은 원래 오버와 언더가 반반에 가깝게 나오도록 정해집니다. "
             f"{'지난 한 주은 득점이 많은 쪽으로 기울었습니다.' if rate > 0.55 else '지난 한 주은 득점이 적은 쪽으로 기울었습니다.' if rate < 0.45 else '지난 한 주은 거의 반반이었습니다.'}</p>",
             "<h2>리그별 오버·언더</h2>", _table(["리그", "경기", "오버", "언더"], rows),
             "<p>한 리그가 한쪽으로 크게 기울었다면, 그 리그의 득점 흐름이 바뀌고 있거나 단순한 출렁임일 수 있습니다. 같은 방향이 몇 주 이어지는지 다음 리포트와 비교해 보면 구분됩니다.</p>",
             "<h2>이렇게 활용하세요</h2><p>여러 주 연속 오버가 많았던 리그는 기준점이 실제 득점 흐름을 따라가지 못하고 있을 가능성이 있습니다. 반대로 한 주만 튀었다면 평소 기준으로 돌아가는 경우가 많습니다. "
             "만 19세 이상, 베트맨 공식 채널에서만 구매할 수 있습니다.</p>"]
    return _art(f"weekly-{key}-overunder", f"프로토 언더오버 리포트 #{no}", lead, parts, len(games))


def ensure(rows: list[list], now: datetime | None = None) -> int:
    """지난주 리포트가 없으면 만든다. 만든 글 수."""
    now = now or config.now_kst()
    start, end, key = _week_bounds(now)
    DIR.mkdir(parents=True, exist_ok=True)
    p = DIR / f"{key}.json"
    if p.exists():
        return 0
    games = _games(rows, start, end)
    if len(games) < 30:
        return 0
    no = len(list(DIR.glob("*.json"))) + 1
    arts = [a for a in (_upsets(games, no, key), _favorites(games, no, key), _overunder(games, no, key)) if a]
    if not arts:
        return 0
    p.write_text(json.dumps(arts, ensure_ascii=False), encoding="utf-8")
    log.info("주간 리포트 #%d %d편 생성(%s)", no, len(arts), key)
    return len(arts)


def load() -> list[dict]:
    out = []
    if DIR.exists():
        for p in sorted(DIR.glob("*.json"), reverse=True):
            try:
                out += json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
    return out
