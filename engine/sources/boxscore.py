"""경기 점수판(쿼터·이닝·세트·전후반, 축구 골 시간·득점자) 수집.

- 출처: ESPN 공개 점수판(site.api.espn.com). 키·요금 없음. 다루지 않는 리그(KBO·NPB·KBL·KOVO·K리그 등)는 건너뛴다.
- 베트맨 지난 경기(승패·승무패 행의 실제 점수)를 리그 + 킥오프 시각(±3시간) + 최종 점수로 ESPN 경기와 맞춘다.
  팀 이름 번역이 필요 없고, 같은 시각·같은 점수가 둘 이상이면 틀릴 수 있으니 저장하지 않는다.
- 저장: data/history/box/<YYYY-MM>.json  {"날짜|홈|원정": 점수판}. 못 찾은 경기는 data/state/box_miss.json 에 세어
  두 번 넘게 실패하면 다시 찾지 않는다(요청 낭비 방지).
- 한 번 실행에 요청 수 상한(MAX_REQ)을 둬서 첫 백필도 여러 번에 나눠 끝난다.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import config
from ..util import http, read_json, write_json

log = logging.getLogger("engine.box")
KST = timezone(timedelta(hours=9))
DIR = config.DATA / "history" / "box"
MISS = config.STATE / "box_miss.json"
BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
MAX_REQ = 80        # 실행당 ESPN 요청 상한
BACK_DAYS = 120     # 이 기간 안의 경기만 찾는다
MAX_MISS = 2
UA = {"User-Agent": "sports-report/1.0"}  # ESPN 은 주소가 들어간 User-Agent 를 막는다

# 베트맨 리그 이름(띄어쓰기 뺀 것) → ESPN 경로
LEAGUES = {
    "MLB": "baseball/mlb", "NBA": "basketball/nba", "WNBA": "basketball/wnba", "NHL": "hockey/nhl",
    "잉글랜드프리미어리그": "soccer/eng.1", "잉글랜드챔피언십": "soccer/eng.2", "잉글랜드리그컵": "soccer/eng.league_cup",
    "잉글랜드FA컵": "soccer/eng.fa", "스페인라리가": "soccer/esp.1", "이탈리아세리에A": "soccer/ita.1",
    "독일분데스리가": "soccer/ger.1", "프랑스리그1": "soccer/fra.1", "네덜란드에레디비시": "soccer/ned.1",
    "독일FA컵": "soccer/ger.dfb_pokal", "이탈리아FA컵": "soccer/ita.coppa_italia", "프랑스FA컵": "soccer/fra.coupe_de_france",
    "UEFA챔피언스리그": "soccer/uefa.champions", "UEFA유로파리그": "soccer/uefa.europa", "UEFA컨퍼런스리그": "soccer/uefa.europa.conf",
    "UEFA네이션스리그": "soccer/uefa.nations", "UEFA슈퍼컵": "soccer/uefa.super_cup",
    "미국메이저리그사커": "soccer/usa.1", "미국FA컵": "soccer/usa.open", "리그스컵": "soccer/concacaf.leagues.cup",
    "CONCACAF네이션스리그": "soccer/concacaf.nations.league", "CONCACAF챔피언스컵": "soccer/concacaf.champions",
    "일본J1리그": "soccer/jpn.1", "AFC챔피언스리그엘리트": "soccer/afc.champions", "AFC챔피언스리그2": "soccer/afc.cup",
    "노르웨이엘리테세리엔": "soccer/nor.1", "중국슈퍼리그": "soccer/chn.1", "호주A리그": "soccer/aus.1",
    "코파리베르타도레스": "soccer/conmebol.libertadores", "남자축구국제친선경기": "soccer/fifa.friendly",
    "축구월드컵": "soccer/fifa.world", "축구클럽친선경기": "soccer/club.friendly",
}


def path_for(league: str) -> str | None:
    return LEAGUES.get(re.sub(r"\s+", "", league or ""))


def key_of(date: str, home: str, away: str) -> str:
    return f"{date}|{home}|{away}"


# ── 저장소 ──────────────────────────────────────────────
def load_all() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if DIR.exists():
        for f in sorted(DIR.glob("*.json")):
            out.update(read_json(f, {}) or {})
    return out


def _save(new: dict[str, dict]) -> None:
    by_month: dict[str, dict] = {}
    for k, v in new.items():
        by_month.setdefault(k[:7], {})[k] = v
    DIR.mkdir(parents=True, exist_ok=True)
    for mon, items in by_month.items():
        p: Path = DIR / f"{mon}.json"
        cur = read_json(p, {}) or {}
        cur.update(items)
        write_json(p, dict(sorted(cur.items())))


# ── ESPN 응답 → 점수판 ──────────────────────────────────
def _num(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _minute(txt: str) -> tuple[int, int]:
    """"45'+2'" → (45, 2), "90'" → (90, 0)."""
    m = re.findall(r"\d+", txt or "")
    return (int(m[0]) if m else 0, int(m[1]) if len(m) > 1 else 0)


def _soccer(c: dict, home_id: str, sh: dict, sa: dict) -> dict | None:
    goals = []
    for x in c.get("details") or []:
        if not x.get("scoringPlay"):
            continue
        typ = (x.get("type") or {}).get("text") or ""
        if "Shootout" in typ:
            continue
        tid = str((x.get("team") or {}).get("id") or "")
        side = "h" if tid == home_id else "a"
        names = [a.get("displayName") or a.get("shortName") for a in x.get("athletesInvolved") or []]
        tag = "PK" if "Penalty" in typ else ("자책" if "Own" in typ else "")
        clock = (x.get("clock") or {}).get("displayValue") or ""
        goals.append([clock, side, names[0] if names else "", tag])
    th, ta = _num(sh.get("score")), _num(sa.get("score"))
    if th is None or ta is None:
        return None
    # 골 목록이 최종 점수와 맞지 않으면(자책골 귀속 차이 등) 자책골 방향을 바꿔 본다, 그래도 안 맞으면 골 목록은 버린다
    def tally(gs):
        return sum(1 for g in gs if g[1] == "h"), sum(1 for g in gs if g[1] == "a")
    if tally(goals) != (th, ta):
        flipped = [[g[0], ("a" if g[1] == "h" else "h") if g[3] == "자책" else g[1], g[2], g[3]] for g in goals]
        goals = flipped if tally(flipped) == (th, ta) else []
    name = ((c.get("status") or {}).get("type") or {}).get("name") or ""
    et = "AET" in name or "PEN" in name or any(_minute(g[0])[0] > 90 for g in goals)
    out = {"k": "sc", "t": [th, ta], "g": goals}
    if goals or (th, ta) == (0, 0):
        cols = ["전반", "후반"] + (["연장"] if et else [])
        per = {c_: [0, 0] for c_ in cols}
        for g in goals:
            mn, _ = _minute(g[0])
            col = "전반" if mn <= 45 else ("후반" if mn <= 90 or not et else "연장")
            per[col][0 if g[1] == "h" else 1] += 1
        out.update(cols=cols, h=[per[c_][0] for c_ in cols], a=[per[c_][1] for c_ in cols])
        if et:  # 베트맨 승무패는 연장 전 점수로 채점된다
            out["r90"] = [sum(per[c_][0] for c_ in cols[:2]), sum(per[c_][1] for c_ in cols[:2])]
    ph, pa = _num(sh.get("shootoutScore")), _num(sa.get("shootoutScore"))
    if ph is not None and pa is not None and (ph or pa):
        out["pen"] = [ph, pa]
    return out


def _lines(sh: dict, sa: dict) -> tuple[list, list]:
    return ([_num(l.get("value")) for l in sh.get("linescores") or []],
            [_num(l.get("value")) for l in sa.get("linescores") or []])


def _period_cols(n: int, kind: str) -> list[str]:
    if kind == "bk":
        reg, lab = 4, "{}Q"
    elif kind == "hk":
        reg, lab = 3, "{}P"
    else:
        return [str(i + 1) for i in range(n)]
    cols = [lab.format(i + 1) for i in range(min(n, reg))]
    extra = n - reg
    for i in range(max(0, extra)):
        cols.append("연장" if extra == 1 else f"연장{i + 1}")
    return cols


def parse_event(e: dict, path: str) -> dict | None:
    try:
        c = e["competitions"][0]
        st = (c.get("status") or {}).get("type") or {}
        if not st.get("completed"):
            return None
        sh = next(t for t in c["competitors"] if t.get("homeAway") == "home")
        sa = next(t for t in c["competitors"] if t.get("homeAway") == "away")
    except (KeyError, IndexError, StopIteration, TypeError):
        return None
    sport = path.split("/")[0]
    if sport == "soccer":
        box = _soccer(c, str((sh.get("team") or {}).get("id") or ""), sh, sa)
    else:
        kind = {"basketball": "bk", "hockey": "hk", "baseball": "bb"}.get(sport)
        th, ta = _num(sh.get("score")), _num(sa.get("score"))
        lh, la = _lines(sh, sa)
        if kind is None or th is None or ta is None or not la:
            return None
        n = max(len(lh), len(la))
        if kind == "bb":
            lh += [None] * (n - len(lh))   # 9회말 공격이 없었으면 'X'
        box = {"k": kind, "t": [th, ta], "cols": _period_cols(n, kind), "h": lh, "a": la}
        if kind == "bb":
            box["x"] = {"H": [_num(sh.get("hits")), _num(sa.get("hits"))], "E": [_num(sh.get("errors")), _num(sa.get("errors"))]}
        if kind == "hk" and "SO" in (st.get("shortDetail") or ""):
            box["so"] = True
        if sum(v or 0 for v in lh) != th or sum(v or 0 for v in la) != ta:
            if kind != "hk":  # 승부치기 점수는 이닝 합과 다를 수 있다
                return None
    if not box:
        return None
    box["ko"] = e.get("date")
    box["names"] = [(sh.get("team") or {}).get("displayName"), (sa.get("team") or {}).get("displayName")]
    box["src"] = "ESPN"
    return box


# ── 맞추기 ──────────────────────────────────────────────
def _scores_match(box: dict, hs, as_) -> bool | None:
    """True 같은 순서, False 홈·원정이 뒤바뀜, None 불일치."""
    cands = [tuple(box["t"])]
    if box.get("r90"):
        cands.append(tuple(box["r90"]))
    for h, a in cands:
        if (h, a) == (hs, as_):
            return True
    for h, a in cands:
        if (a, h) == (hs, as_):
            return False
    return None


def _flip(box: dict) -> dict:
    b = dict(box)
    b["t"] = box["t"][::-1]
    b["h"], b["a"] = box.get("a"), box.get("h")
    if box.get("r90"):
        b["r90"] = box["r90"][::-1]
    if box.get("pen"):
        b["pen"] = box["pen"][::-1]
    if box.get("x"):
        b["x"] = {k: v[::-1] for k, v in box["x"].items()}
    if box.get("g"):
        b["g"] = [[g[0], "a" if g[1] == "h" else "h", g[2], g[3]] for g in box["g"]]
    b["names"] = (box.get("names") or [None, None])[::-1]
    b["flip"] = True
    return b


def match(game: dict, events: list[dict], learned: dict | None = None) -> dict | None:
    """game: {ko(ms), hs, as, home, away}. events: parse_event 결과들. 하나로 정해질 때만 돌려준다.

    비슷한 시각에 같은 점수가 둘 이상이면, 이미 확인된 경기에서 배운 '한글 팀명 → ESPN 팀명'으로 가린다."""
    ko = game["ko"] / 1000
    hits = []
    for b in events:
        try:
            t = datetime.fromisoformat(str(b["ko"]).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            continue
        dt = abs(t - ko)
        if dt > 3 * 3600:
            continue
        same = _scores_match(b, game["hs"], game["as"])
        if same is None:
            continue
        hits.append((dt, b if same else _flip(b)))
    if not hits:
        return None
    hits.sort(key=lambda x: x[0])
    if len(hits) > 1 and hits[1][0] - hits[0][0] < 1800:  # 비슷한 시각에 같은 점수가 또 있으면 이름으로 가린다
        lr = learned or {}
        want = (lr.get(game.get("home")), lr.get(game.get("away")))
        ok = [b for _, b in hits if any(w and w == n for w, n in zip(want, b.get("names") or []))]
        return ok[0] if len(ok) == 1 else None
    return hits[0][1]


def learn(boxes: dict[str, dict]) -> dict[str, str]:
    """확인된 경기들에서 베트맨 팀명 → ESPN 팀명."""
    out: dict[str, str] = {}
    for k, b in boxes.items():
        parts = k.split("|")
        nm = b.get("names") or []
        if len(parts) == 3 and len(nm) == 2:
            out.setdefault(parts[1], nm[0])
            out.setdefault(parts[2], nm[1])
    return out


def _query_dates(ko_ms: int) -> list[str]:
    u = datetime.fromtimestamp(ko_ms / 1000, timezone.utc)
    et = u - timedelta(hours=5)
    return sorted({u.strftime("%Y%m%d"), et.strftime("%Y%m%d")})


def collect(history_rows: list[list], *, max_req: int = MAX_REQ) -> int:
    """베트맨 지난 경기 중 아직 점수판이 없는 경기를 ESPN 에서 찾아 저장. 새로 저장한 수를 돌려준다."""
    have = load_all()
    miss = read_json(MISS, {}) or {}
    now = datetime.now(KST)
    todo: dict[str, dict] = {}
    for r in history_rows:
        try:
            sport, league, mk, ko, home, away, hs, as_ = r[0], r[1], r[2], int(r[8]), r[10], r[11], r[12], r[13]
        except (IndexError, TypeError, ValueError):
            continue
        if mk not in ("WL", "1X2") or hs is None or as_ is None:
            continue
        path = path_for(league)
        if not path:
            continue
        dt = datetime.fromtimestamp(ko / 1000, KST)
        if (now - dt).days > BACK_DAYS or now - dt < timedelta(hours=3):
            continue
        k = key_of(dt.date().isoformat(), home, away)
        if k in have or miss.get(k, 0) >= MAX_MISS:
            continue
        todo[k] = {"path": path, "ko": ko, "hs": int(hs), "as": int(as_), "home": home, "away": away}
    if not todo:
        return 0
    cache: dict[tuple[str, str], list[dict] | None] = {}
    req = 0
    new: dict[str, dict] = {}
    learned = learn(have)
    pending: list[tuple[str, dict, list]] = []
    # 최근 경기부터
    for k, g in sorted(todo.items(), key=lambda kv: -kv[1]["ko"]):
        evs: list[dict] = []
        tried, failed = True, False
        for d in _query_dates(g["ko"]):
            ck = (g["path"], d)
            if ck not in cache:
                if req >= max_req:
                    tried = False
                    break
                req += 1
                try:
                    j = http("GET", BASE.format(path=g["path"]), params={"dates": d, "limit": 300}, retries=2, headers=UA).json()
                    cache[ck] = [b for b in (parse_event(e, g["path"]) for e in j.get("events") or []) if b]
                except Exception as e:  # noqa: BLE001
                    log.info("ESPN %s %s 실패: %s", g["path"], d, e)
                    cache[ck] = None
            if cache[ck] is None:
                failed = True  # 접속 실패는 '못 찾음'으로 세지 않는다(다음 실행에 다시)
            else:
                evs += cache[ck]
        if not tried:
            break
        b = match(g, evs, learned)
        if not b and failed:
            continue
        if b:
            new[k] = {kk: v for kk, v in b.items() if kk != "ko"}
            miss.pop(k, None)
        else:
            pending.append((k, g, evs))
    # 이번에 새로 확인된 경기로 이름을 더 배운 뒤 한 번 더
    learned = learn({**have, **new})
    for k, g, evs in pending:
        b = match(g, evs, learned)
        if b:
            new[k] = {kk: v for kk, v in b.items() if kk != "ko"}
            miss.pop(k, None)
        else:
            miss[k] = miss.get(k, 0) + 1
    if new:
        _save(new)
    # 오래된 실패 기록 정리
    cut = (now - timedelta(days=BACK_DAYS + 5)).date().isoformat()
    write_json(MISS, {k: v for k, v in miss.items() if k[:10] >= cut})
    log.info("점수판: 새로 %d건 (요청 %d회, 남은 대상 %d)", len(new), req, len(todo) - len(new))
    return len(new)
