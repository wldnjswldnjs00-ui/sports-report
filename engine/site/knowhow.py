"""노하우: 쌓인 기록으로 매일 다시 계산해 쓰는 글.

원칙(CLAUDE.md·HANDOFF.md)
- 모든 숫자는 빌드할 때마다 기록에서 다시 계산한다. 사람이 고칠 것이 없다.
- 글에 날짜를 쓰지 않는다. 표본이 모자라면 그 글(또는 그 표·문단)은 만들지 않는다.
- 한 글 1,000자 이상. 리그 이름만 바꾼 같은 문장이 되지 않게, 결과에 따라 문장을 고른다.
- 부정적인 문구·AI 말투를 피하고, 숫자가 말하게 한다.

데이터
- 베트맨 지난 회차(betman_history.load_all): [종목, 리그, 마켓, 기준점, 왼칸, 무, 오른칸, 결과칸, 킥오프ms, 왼칸이언더, 홈, 원정, 홈점수, 원정점수, 첫 왼칸, 첫 무, 첫 오른칸]
- 유럽 축구(football-data.co.uk, data/history/overseas/<시즌>_<리그>.json): [홈, 무, 원정 배당, 결과, 오버2.5, 언더2.5, 총득점, 홈득점, 원정득점]
- NBA·MLB 10시즌(data/history/us/*.json): [홈 승리확률, 홈점수, 원정점수, 합계 기준점]
"""
from __future__ import annotations

import html
import itertools
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from .. import config

KST = timezone(timedelta(hours=9))
MIN_CHARS = 100
SPORT_KO = {"soccer": "축구", "basketball": "농구", "baseball": "야구", "volleyball": "배구"}
FD_NAME = {"E0": "잉글랜드 프리미어리그", "E1": "잉글랜드 챔피언십", "SP1": "스페인 라리가", "SP2": "스페인 라리가2",
           "I1": "이탈리아 세리에A", "I2": "이탈리아 세리에B", "D1": "독일 분데스리가", "D2": "독일 분데스리가2",
           "F1": "프랑스 리그1", "F2": "프랑스 리그2", "N1": "네덜란드 에레디비시", "P1": "포르투갈 프리메이라리가",
           "B1": "벨기에 프로리그", "T1": "튀르키예 쉬페르리그", "SC0": "스코틀랜드 프리미어십", "G1": "그리스 슈퍼리그"}


# ───────────────────────── 작은 도구 ─────────────────────────
def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def pp(x):
    """퍼센트포인트 차이(부호 포함)."""
    v = round(x * 100, 1)
    return "0.0%p" if v == 0 else f"{v:+.1f}%p"


def josa(word, a="은", b="는"):
    """받침 있으면 a, 없으면 b. 영문·숫자로 끝나면 읽는 소리 기준으로 대략 맞춘다."""
    w = str(word).strip()
    if not w:
        return b
    c = w[-1]
    if "가" <= c <= "힣":
        return a if (ord(c) - 0xAC00) % 28 else b
    return a if c.lower() in "lmnr0136789" else b


def esc(s):
    return html.escape(str(s))


def fair(odds):
    inv = [1 / o for o in odds if o and o > 1]
    s = sum(inv)
    return [(1 / o) / s if o and o > 1 else 0 for o in odds]


def plain_len(body: str) -> int:
    return len(re.sub(r"<[^>]+>", "", body).replace("\n", "").replace(" ", ""))


class A:
    """글 하나. sections: [(소제목, [문단 또는 ('table', 머리, 행들)])]"""

    def __init__(self, slug, title, cat, lead, sections, league=None, sport=None, tags=()):
        self.slug, self.title, self.cat, self.lead = slug, title, cat, lead
        self.sections, self.league, self.sport, self.tags = sections, league, sport, list(tags)

    def html(self) -> str:
        out = []
        for h, parts in self.sections:
            if h:
                out.append(f"<h2>{esc(h)}</h2>")
            for p in parts:
                if isinstance(p, tuple) and p and p[0] == "table":
                    _, head, rows = p
                    th = "".join(f'<th class="{"n" if i else ""}">{esc(x)}</th>' for i, x in enumerate(head))
                    trs = "".join("<tr>" + "".join(f'<td class="{"n" if i else ""}">{esc(c)}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
                    out.append(f'<div class="tblw"><table class="tbl kh-tbl"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')
                elif p:
                    out.append(f"<p>{p}</p>")
        return "\n".join(out)

    def to_dict(self):
        body = self.html()
        return {"slug": self.slug, "title": self.title, "cat": self.cat, "lead": self.lead, "league": self.league,
                "sport": self.sport, "tags": self.tags, "body": body, "chars": plain_len(self.lead + body)}


# ───────────────────────── 데이터 정리 ─────────────────────────
def _games(rows):
    """승패·승무패 행을 경기 단위로(중복 제거)."""
    seen, out = set(), []
    for r in rows:
        try:
            sp, lg, mk, line, w, d, l, code, ko, uf, h, a, hs, as_ = r[:14]
        except ValueError:
            continue
        if mk not in ("WL", "1X2") or code not in (0, 1, 2) or not ko or not w or not l:
            continue
        k = (ko, h, a)
        if k in seen:
            continue
        seen.add(k)
        op = r[14:17] if len(r) >= 17 else (0, 0, 0)
        out.append({"sport": sp, "league": lg, "lk": lg.replace(" ", ""), "mk": mk, "o": (w, d or 0, l), "res": code, "ko": int(ko),
                    "home": h, "away": a, "hs": hs, "as": as_, "open": op})
    out.sort(key=lambda g: g["ko"])
    return out


def _lines(rows, mk):
    out, seen = [], set()
    for r in rows:
        try:
            sp, lg, m, line, w, d, l, code, ko, uf, h, a = r[:12]
        except ValueError:
            continue
        if m != mk or code not in (0, 1, 2) or not w or not l:
            continue
        k = (ko, h, a, line)
        if k in seen:
            continue
        seen.add(k)
        out.append({"sport": sp, "league": lg, "lk": lg.replace(" ", ""), "line": line, "o": (w, d or 0, l), "res": code, "uf": uf, "ko": int(ko or 0)})
    return out


def _fav(g):
    """(정배 쪽 0/2, 정배 배당, 역배 배당). 배당이 같으면 None."""
    w, d, l = g["o"]
    if w == l:
        return None
    return (0, w, l) if w < l else (2, l, w)


def _band(o, edges):
    for lo, hi in edges:
        if lo <= o < hi:
            return f"{lo:.2f}~{hi:.2f}" if hi < 50 else f"{lo:.2f} 이상"
    return None


def _kst(ms):
    return datetime.fromtimestamp(ms / 1000, KST)


# ───────────────────────── 공통 글 ─────────────────────────
FAV_EDGES = [(1.0, 1.3), (1.3, 1.5), (1.5, 1.7), (1.7, 1.9), (1.9, 2.2), (2.2, 99)]
DOG_EDGES = [(1.5, 2.2), (2.2, 3.0), (3.0, 4.5), (4.5, 7.0), (7.0, 99)]


def fav_by_band(games, edges=FAV_EDGES, min_n=30):
    acc = defaultdict(lambda: [0, 0, 0.0])
    for g in games:
        f = _fav(g)
        if not f:
            continue
        side, fo, _ = f
        b = _band(fo, edges)
        if not b:
            continue
        p = fair(g["o"])[side]
        a = acc[b]
        a[0] += 1
        a[1] += int(g["res"] == side)
        a[2] += p
    out = []
    for lo, hi in edges:
        b = _band(lo, [(lo, hi)])
        n, h, ps = acc.get(b, [0, 0, 0])
        if n >= min_n:
            out.append({"band": b, "n": n, "hit": h / n, "exp": ps / n})
    return out


def art_favorites(games):
    by_sport = {sp: fav_by_band([g for g in games if g["sport"] == sp]) for sp in SPORT_KO}
    allb = fav_by_band(games)
    if len(allb) < 4:
        return None
    tot = sum(b["n"] for b in allb)
    best = max(allb, key=lambda b: b["hit"] - b["exp"])
    worst = min(allb, key=lambda b: b["hit"] - b["exp"])
    low = allb[0]
    secs = [("배당 구간별로 본 정배의 실제 적중률", [
        f"베트맨 승패·승무패 {tot:,}경기에서 배당이 더 낮은 쪽(정배)이 실제로 몇 번 이겼는지 배당 구간별로 셌습니다. "
        f"'배당 기준 확률'은 베트맨 배당에서 발매사 몫(환급률 차이)을 걷어 내고 계산한 확률입니다. 두 숫자가 비슷하면 배당이 결과를 정직하게 반영한 구간이고, 실제가 더 높으면 정배가 배당보다 더 믿을 만했던 구간입니다.",
        ("table", ["정배 배당", "경기 수", "실제 적중", "배당 기준 확률", "차이"],
         [[b["band"], f"{b['n']:,}", pct(b["hit"]), pct(b["exp"]), pp(b["hit"] - b["exp"])] for b in allb]),
        f"가장 낮은 구간({low['band']})의 정배는 {pct(low['hit'])} 이겼습니다. 거의 확실해 보이는 배당이라도 열 번 중 "
        f"{max(1, round((1 - low['hit']) * 10))}번 가까이는 다른 결과가 나온다는 뜻입니다. 이 구간을 여러 경기 묶을 때 이 숫자가 곱해진다는 점이 핵심입니다.",
        f"배당 기준 확률보다 실제가 가장 높았던 곳은 {best['band']} 구간({pp(best['hit'] - best['exp'])}), "
        + (f"가장 낮았던 곳은 {worst['band']} 구간({pp(worst['hit'] - worst['exp'])})입니다. " if worst is not best else "")
        + "차이가 2%p 안쪽이면 표본 흔들림으로 보는 편이 안전하고, 그보다 크게 벌어진 구간은 경기가 쌓일수록 같은 방향을 유지하는지 지켜볼 만합니다.",
    ])]
    rows = []
    for sp, bands in by_sport.items():
        for b in bands:
            rows.append([SPORT_KO[sp], b["band"], f"{b['n']:,}", pct(b["hit"]), pp(b["hit"] - b["exp"])])
    if rows:
        sp_gap = {sp: sum((b["hit"] - b["exp"]) * b["n"] for b in bs) / max(1, sum(b["n"] for b in bs)) for sp, bs in by_sport.items() if bs}
        hi_sp = max(sp_gap, key=sp_gap.get)
        lo_sp = min(sp_gap, key=sp_gap.get)
        secs.append(("종목마다 정배의 무게가 다릅니다", [
            "같은 1.5배라도 종목에 따라 실제로 이기는 비율이 다릅니다. 득점이 적은 종목은 한 번의 실수나 운이 결과를 바꾸기 쉽고, 득점이 많은 종목은 실력 차이가 결과로 이어지기 쉽습니다.",
            ("table", ["종목", "정배 배당", "경기 수", "실제 적중", "배당 대비"], rows),
            f"구간을 합쳐 보면 {SPORT_KO[hi_sp]}의 정배가 배당보다 가장 잘 버텼고({pp(sp_gap[hi_sp])}), "
            f"{SPORT_KO[lo_sp]}가 가장 덜 버텼습니다({pp(sp_gap[lo_sp])}). 종목을 섞어 조합을 짤 때는 같은 배당이라도 이 차이를 감안해 무게를 다르게 두는 편이 낫습니다.",
        ]))
    secs.append(("활용하는 법", [
        "정배를 고를 때는 배당 숫자 하나만 보지 말고, 그 배당 구간이 지금까지 실제로 얼마나 맞았는지를 같이 봅니다. 구간 적중률이 배당 기준 확률보다 꾸준히 높은 곳은 같은 배당이라도 한 번 더 믿어 볼 근거가 됩니다.",
        "반대로 구간 적중률이 배당보다 낮게 이어지는 곳은 정배를 단폴더로 노리기보다 조합의 한 칸 정도로만 쓰는 편이 무리가 없습니다. 이 표는 경기가 쌓일 때마다 자동으로 다시 계산되므로, 같은 구간의 숫자가 흔들리는지 꾸준히 같은 쪽을 가리키는지도 함께 보면 좋습니다.",
    ]))
    return A("favorites-by-odds", "정배는 배당만큼 이길까: 배당 구간별 실제 적중률", "공통",
             "배당이 낮을수록 잘 맞는 건 당연해 보이지만, 구간마다 실제로 이긴 비율은 배당이 말하는 확률과 조금씩 다릅니다. 베트맨 발매 경기 기록으로 직접 셌습니다.", secs, tags=["정배", "배당"])


def art_upsets(games):
    acc = defaultdict(lambda: [0, 0, 0.0])
    for g in games:
        f = _fav(g)
        if not f:
            continue
        side, fo, do = f
        dside = 2 - side
        b = _band(do, DOG_EDGES)
        if not b:
            continue
        a = acc[b]
        a[0] += 1
        a[1] += int(g["res"] == dside)
        a[2] += fair(g["o"])[dside]
    bands = []
    for lo, hi in DOG_EDGES:
        b = _band(lo, [(lo, hi)])
        n, h, ps = acc.get(b, [0, 0, 0])
        if n >= 30:
            bands.append({"band": b, "n": n, "hit": h / n, "exp": ps / n})
    if len(bands) < 3:
        return None
    sweet = max(bands, key=lambda b: b["hit"] - b["exp"])
    n_all = sum(b["n"] for b in bands)
    h_all = sum(b["hit"] * b["n"] for b in bands)
    sp_rows = []
    for sp in SPORT_KO:
        gs = [g for g in games if g["sport"] == sp and _fav(g)]
        if len(gs) < 80:
            continue
        up = sum(1 for g in gs if g["res"] == 2 - _fav(g)[0])
        sp_rows.append([SPORT_KO[sp], f"{len(gs):,}", pct(up / len(gs))])
    secs = [("배당이 높은 쪽이 이긴 비율", [
        f"승패·승무패 {n_all:,}경기에서 배당이 더 높은 쪽(역배)이 이긴 경기는 {int(h_all):,}번입니다. 구간별로 나눠 보면 역배가 언제 현실이 되는지 보입니다.",
        ("table", ["역배 배당", "경기 수", "역배 적중", "배당 기준 확률", "차이"],
         [[b["band"], f"{b['n']:,}", pct(b["hit"]), pct(b["exp"]), pp(b["hit"] - b["exp"])] for b in bands]),
        f"배당 기준 확률보다 실제로 더 자주 터진 구간은 {sweet['band']}입니다({pct(sweet['hit'])}, {pp(sweet['hit'] - sweet['exp'])}). "
        "역배는 한 번 맞으면 크게 돌아오지만, 높은 배당일수록 적중 간격이 길어집니다. 구간별 실제 적중률을 알고 있으면 몇 경기에 한 번 정도 맞는 선택인지 미리 가늠할 수 있습니다.",
    ])]
    if sp_rows:
        secs.append(("종목별 역배 적중", [
            "종목마다 이변의 빈도가 다릅니다. 같은 역배라도 이변이 잦은 종목에서 노리는 편이 기다리는 시간이 짧습니다.",
            ("table", ["종목", "경기 수", "역배 적중"], sp_rows),
        ]))
    hi = bands[-1]
    secs.append(("역배를 다루는 감각", [
        f"가장 높은 구간({hi['band']})의 역배는 {pct(hi['hit'])} 맞았습니다. 대략 {max(2, round(1 / max(hi['hit'], 0.01)))}경기에 한 번꼴입니다. "
        "이 정도 간격이면 한두 번 빗나가는 것은 계산 안의 일입니다. 같은 금액을 여러 번 나눠 쓰는 쪽이 한 번에 크게 거는 쪽보다 기록을 끝까지 가져가기 쉽습니다.",
        "사이트의 '역배 조합'은 배당이 높은 쪽 중에서도 해외 기록과 팀 레이팅이 받쳐 주는 경기만 고릅니다. 아래 표의 구간 숫자를 기준으로 삼고, 그날 고른 역배가 어느 구간에 들어가는지 확인해 보면 기대치를 정하기 쉽습니다.",
    ]))
    return A("underdogs", "역배는 얼마나 자주 터질까: 배당 구간별 이변 기록", "공통",
             "높은 배당은 그만큼 드물게 맞습니다. 그런데 얼마나 드문지는 구간마다 다르고, 배당이 말하는 것보다 자주 터지는 구간도 있습니다.", secs, tags=["역배", "이변"])


def art_draws(games):
    sg = [g for g in games if g["sport"] == "soccer" and g["mk"] == "1X2" and g["o"][1] > 1]
    if len(sg) < 300:
        return None
    d_all = sum(1 for g in sg if g["res"] == 1) / len(sg)
    # 두 팀 배당 차이로 본 무승부
    edges = [(0, 0.3), (0.3, 0.8), (0.8, 1.6), (1.6, 3.0), (3.0, 99)]
    acc = defaultdict(lambda: [0, 0, 0.0])
    for g in sg:
        gap = abs(g["o"][0] - g["o"][2])
        for lo, hi in edges:
            if lo <= gap < hi:
                k = f"{lo:g}~{hi:g}" if hi < 50 else f"{lo:g} 이상"
                a = acc[k]
                a[0] += 1
                a[1] += int(g["res"] == 1)
                a[2] += fair(g["o"])[1]
    rows = []
    for lo, hi in edges:
        k = f"{lo:g}~{hi:g}" if hi < 50 else f"{lo:g} 이상"
        n, h, ps = acc.get(k, [0, 0, 0])
        if n >= 30:
            rows.append([k, f"{n:,}", pct(h / n), pct(ps / n)])
    lg = defaultdict(lambda: [0, 0])
    for g in sg:
        lg[g["league"]][0] += 1
        lg[g["league"]][1] += int(g["res"] == 1)
    lrows = sorted(([k, v[0], v[1] / v[0]] for k, v in lg.items() if v[0] >= 60), key=lambda x: -x[2])
    secs = [("축구 무승부, 생각보다 자주 나옵니다", [
        f"베트맨 축구 승무패 {len(sg):,}경기 가운데 무승부는 {pct(d_all)}였습니다. 대략 {round(1 / d_all)}경기에 한 번입니다. "
        "승무패 조합에 축구를 여러 경기 넣으면 그중 하나가 무승부로 끝날 가능성이 꽤 높아집니다.",
        f"축구 세 경기를 묶으면 셋 다 무승부가 아닐 확률은 대략 {pct((1 - d_all) ** 3, 0)}, 다섯 경기면 {pct((1 - d_all) ** 5, 0)}입니다. "
        "승과 패만 보고 조합을 짜면 이 무승부 몫이 빠집니다.",
    ]), ("두 팀 배당이 비슷할수록", [
        "홈과 원정 배당 차이를 기준으로 나눠 보면, 두 팀이 비슷하게 평가될수록 무승부가 늘어납니다.",
        ("table", ["홈·원정 배당 차이", "경기 수", "무승부", "배당 기준 무 확률"], rows),
        "배당 차이가 작은 경기에서 한쪽 승을 고를 때는 무승부 몫을 따로 떼어 생각해야 합니다. 이런 경기는 승무패보다 핸디캡이나 언더오버로 접근하는 편이 결과를 덜 타기도 합니다.",
    ])]
    if len(lrows) >= 4:
        top, bot = lrows[0], lrows[-1]
        secs.append(("리그별 무승부 비율", [
            ("table", ["리그", "경기 수", "무승부"], [[esc(k), f"{n:,}", pct(r)] for k, n, r in lrows[:12]]),
            f"무승부가 가장 잦았던 리그는 {esc(top[0])}({pct(top[2])}), 가장 드물었던 리그는 {esc(bot[0])}({pct(bot[2])})입니다. "
            "같은 배당 차이라도 리그 성격에 따라 무승부 몫이 달라지므로, 낯선 리그는 이 표로 먼저 감을 잡고 들어가는 편이 좋습니다.",
        ]))
    return A("soccer-draws", "축구 무승부는 얼마나 나올까: 배당 차이와 리그별 기록", "공통",
             "축구 승무패에서 가장 자주 놓치는 결과가 무승부입니다. 두 팀 배당이 비슷할수록, 그리고 리그에 따라 그 비율이 어떻게 달라지는지 셌습니다.", secs, sport="soccer", tags=["축구", "무승부"])


def art_home(games):
    rows, data = [], {}
    for sp in SPORT_KO:
        gs = [g for g in games if g["sport"] == sp]
        if len(gs) < 100:
            continue
        hw = sum(1 for g in gs if g["res"] == 0) / len(gs)
        aw = sum(1 for g in gs if g["res"] == 2) / len(gs)
        exp = sum(fair(g["o"])[0] for g in gs) / len(gs)
        data[sp] = (len(gs), hw, aw, exp)
        rows.append([SPORT_KO[sp], f"{len(gs):,}", pct(hw), pct(aw), pct(exp)])
    if len(rows) < 2:
        return None
    lg = defaultdict(lambda: [0, 0, 0.0])
    for g in games:
        a = lg[(g["sport"], g["league"])]
        a[0] += 1
        a[1] += int(g["res"] == 0)
        a[2] += fair(g["o"])[0]
    lrows = sorted(([SPORT_KO.get(s, s), l, v[0], v[1] / v[0], v[1] / v[0] - v[2] / v[0]] for (s, l), v in lg.items() if v[0] >= 120), key=lambda x: -x[4])
    strongest = max(data, key=lambda s: data[s][1])
    secs = [("종목별 홈 승률", [
        "홈 경기는 이동 피로가 없고 익숙한 환경에서 뛴다는 이점이 있습니다. 그 이점이 실제 결과에서 얼마나 되는지 종목별로 셌습니다. "
        "'배당 기준 홈 확률'은 배당이 이미 홈 이점을 얼마나 반영했는지 보여 줍니다.",
        ("table", ["종목", "경기 수", "홈 승", "원정 승", "배당 기준 홈 확률"], rows),
        f"홈 승률이 가장 높은 종목은 {SPORT_KO[strongest]}({pct(data[strongest][1])})입니다. 다만 배당이 이미 홈 이점을 반영하고 있으므로, "
        "중요한 건 홈 승률 자체보다 실제 홈 승률과 배당 기준 확률의 차이입니다.",
    ])]
    if len(lrows) >= 4:
        a, z = lrows[0], lrows[-1]
        secs.append(("배당보다 홈이 더 강했던 리그, 덜 강했던 리그", [
            ("table", ["종목", "리그", "경기 수", "홈 승", "배당 대비"], [[s, esc(l), f"{n:,}", pct(h), pp(d)] for s, l, n, h, d in lrows[:14]]),
            f"{esc(a[1])}에서는 홈팀이 배당보다 {pp(a[4])} 더 이겼고, {esc(z[1])}에서는 {pp(z[4])}였습니다. "
            "배당보다 홈이 꾸준히 더 강한 리그라면 홈 정배를 조금 더 믿을 근거가 되고, 반대인 리그에서는 원정팀 쪽을 다시 볼 이유가 생깁니다.",
        ]))
    secs.append(("홈 이점을 읽는 순서", [
        "홈·원정만으로 고르지 말고, 먼저 그 리그의 홈 승률이 배당 기준 확률보다 높은지 낮은지 확인합니다. 그다음 그 경기의 배당 구간과 두 팀 최근 흐름을 봅니다. 홈 이점은 배당에 대부분 녹아 있어서, 차이가 나는 리그를 아는 것 자체가 쓸모 있는 정보입니다.",
    ]))
    return A("home-advantage", "홈 이점은 얼마나 될까: 종목·리그별 홈 승률과 배당", "공통",
             "홈팀이 유리하다는 말은 누구나 압니다. 그런데 그 유리함이 배당에 이미 얼마나 들어가 있는지, 리그마다 어떻게 다른지는 기록을 봐야 알 수 있습니다.", secs, tags=["홈", "원정"])


def art_overunder(rows):
    ou = _lines(rows, "OU")
    if len(ou) < 300:
        return None
    by = defaultdict(lambda: [0, 0])
    for x in ou:
        over = x["res"] == (2 if x["uf"] else 0)
        a = by[x["sport"]]
        a[0] += 1
        a[1] += int(over)
    trows = [[SPORT_KO.get(s, s), f"{v[0]:,}", pct(v[1] / v[0])] for s, v in by.items() if v[0] >= 50]
    lg = defaultdict(lambda: [0, 0])
    for x in ou:
        a = lg[(x["sport"], x["league"])]
        a[0] += 1
        a[1] += int(x["res"] == (2 if x["uf"] else 0))
    lrows = sorted(([SPORT_KO.get(s, s), l, v[0], v[1] / v[0]] for (s, l), v in lg.items() if v[0] >= 80), key=lambda r: -r[3])
    tot = sum(v[0] for v in by.values())
    ov = sum(v[1] for v in by.values()) / tot
    secs = [("언더오버는 반반일까", [
        f"베트맨 언더오버 {tot:,}경기에서 오버로 끝난 비율은 {pct(ov)}입니다. 기준점은 양쪽이 비슷해지도록 정해지기 때문에 전체로 보면 반반 근처에 모입니다. "
        "그래서 언더오버는 '어느 쪽이 많이 나오나'보다 '어느 리그·종목에서 한쪽으로 기울었나'를 보는 마켓입니다.",
        ("table", ["종목", "경기 수", "오버"], trows),
    ])]
    if len(lrows) >= 4:
        hi, lo = lrows[0], lrows[-1]
        secs.append(("리그별로 보면 기울기가 보입니다", [
            ("table", ["종목", "리그", "경기 수", "오버"], [[s, esc(l), f"{n:,}", pct(r)] for s, l, n, r in lrows[:14]]),
            f"오버가 가장 잦았던 곳은 {esc(hi[1])}({pct(hi[3])}), 언더가 가장 잦았던 곳은 {esc(lo[1])}(오버 {pct(lo[3])})입니다. "
            "기준점이 리그의 득점 성향을 따라가지 못하는 동안에는 한쪽이 계속 우세할 수 있습니다. 표본이 쌓일수록 차이가 줄어드는지, 유지되는지가 판단 기준입니다.",
        ]))
    secs.append(("언더오버를 고를 때", [
        "한 경기의 언더오버는 두 팀의 최근 득점·실점, 그리고 그 리그의 오버 비율을 같이 봅니다. 사이트 경기 분석에는 오늘 기준점을 두 팀 최근 경기에 대입한 기록이 나오므로, 리그 경향과 팀 기록이 같은 쪽을 가리킬 때가 근거가 겹치는 경우입니다.",
        "언더오버는 승패와 달리 어느 팀을 응원할 필요가 없어서 감정이 덜 섞입니다. 승패 판단이 어려운 경기에서 대안이 되기도 합니다.",
    ]))
    return A("over-under", "언더오버는 어느 쪽으로 기울까: 종목·리그별 오버 비율", "공통",
             "언더오버 기준점은 양쪽이 비슷해지도록 정해집니다. 그래도 리그와 종목에 따라 한쪽이 꾸준히 더 많이 나오는 곳이 있습니다.", secs, tags=["언더오버"])


def art_handicap(rows):
    hc = _lines(rows, "HANDICAP")
    if len(hc) < 300:
        return None
    by = defaultdict(lambda: [0, 0, 0, 0])
    for x in hc:
        a = by[x["sport"]]
        a[0] += 1
        a[1 + x["res"]] += 1
    trows = [[SPORT_KO.get(s, s), f"{v[0]:,}", pct(v[1] / v[0]), pct(v[2] / v[0]), pct(v[3] / v[0])] for s, v in by.items() if v[0] >= 50]
    # 핸디를 받은 쪽(+) 기준
    plus = defaultdict(lambda: [0, 0])
    for x in hc:
        if not x["line"]:
            continue
        side = 0 if x["line"] > 0 else 2   # 기준점은 홈 기준: 홈이 +면 홈이 핸디를 받은 쪽
        a = plus[x["sport"]]
        a[0] += 1
        a[1] += int(x["res"] == side)
    prow = [[SPORT_KO.get(s, s), f"{v[0]:,}", pct(v[1] / v[0])] for s, v in plus.items() if v[0] >= 50]
    soc = by.get("soccer")
    secs = [("핸디캡 결과는 세 갈래", [
        "베트맨 핸디캡은 홈팀 점수에 기준점을 더해 결과를 정합니다. 축구는 정수 기준점이 많아 '핸디무'가 생기고, 농구·야구는 소수 기준점이라 승과 패 둘로만 갈립니다.",
        ("table", ["종목", "경기 수", "핸디승", "핸디무", "핸디패"], trows),
    ] + ([f"축구 핸디캡에서는 핸디무가 {pct(soc[2] / soc[0])}였습니다. 정수 기준점 경기에서 승이나 패 한쪽만 고르면 이 몫을 비워 두는 셈입니다."] if soc else []))]
    if prow:
        secs.append(("핸디를 받은 쪽은 얼마나 버텼나", [
            "기준점이 플러스인 쪽, 즉 약팀으로 평가돼 점수를 미리 받은 쪽이 핸디캡에서 이긴 비율입니다.",
            ("table", ["종목", "경기 수", "핸디 받은 쪽 적중"], prow),
            "이 비율이 50%보다 높다면 강팀이 기준점만큼 이기지 못한 경기가 더 많았다는 뜻입니다. 큰 기준점일수록 막판 점수 관리나 주전 휴식 같은 변수가 결과를 흔듭니다.",
        ]))
    secs.append(("핸디캡을 쓰는 상황", [
        "정배 배당이 너무 낮아 승패로는 남는 게 없을 때 핸디캡이 대안이 됩니다. 이때는 강팀이 '이기느냐'가 아니라 '몇 점 차로 이기느냐'를 따져야 합니다. 사이트 경기 분석에는 오늘 기준점을 두 팀 최근 경기에 대입한 기록이 있으니 함께 보면 판단이 빨라집니다.",
    ]))
    return A("handicap", "핸디캡은 어떻게 끝날까: 종목별 결과와 핸디 받은 쪽의 기록", "공통",
             "핸디캡은 강팀과 약팀의 차이를 기준점으로 맞춘 마켓입니다. 기준점이 실제 점수 차를 얼마나 잘 맞혔는지 종목별로 셌습니다.", secs, tags=["핸디캡"])


def art_payout(games):
    acc = defaultdict(list)
    for g in games:
        inv = sum(1 / o for o in g["o"] if o and o > 1)
        if inv:
            acc[(g["sport"], g["mk"])].append(1 / inv)
    rows = [[SPORT_KO.get(s, s), "승무패" if m == "1X2" else "승패", f"{len(v):,}", pct(sum(v) / len(v))]
            for (s, m), v in sorted(acc.items()) if len(v) >= 50]
    if len(rows) < 2:
        return None
    allv = [x for v in acc.values() for x in v]
    r = sum(allv) / len(allv)
    secs = [("배당에 들어 있는 몫", [
        "모든 결과의 배당을 확률로 바꿔 더하면 100%를 조금 넘습니다. 넘는 만큼이 발매사의 몫이고, 반대로 1을 그 합으로 나눈 값이 '환급률'입니다. "
        f"베트맨 승패·승무패의 평균 환급률은 {pct(r)}였습니다.",
        ("table", ["종목", "마켓", "경기 수", "평균 환급률"], rows),
        "환급률이 높을수록 같은 경기라도 받는 배당이 후합니다. 같은 판단을 하더라도 환급률이 높은 종목·마켓에서 하는 편이 길게 보면 유리합니다.",
    ]), ("조합에서 환급률이 겹치는 방식", [
        f"한 경기의 환급률이 {pct(r)}라면, 두 경기를 묶은 조합은 대략 {pct(r ** 2)}, 세 경기는 {pct(r ** 3)}, 다섯 경기는 {pct(r ** 5)}가 됩니다. "
        "폴더가 늘수록 배당은 커지지만, 묶을 때마다 이 몫도 같이 곱해집니다.",
        "그래서 조합은 폴더 수를 늘리는 것보다 확신이 있는 경기만 고르는 쪽이 효율적입니다. 사이트의 안정형 조합이 2~3폴더에 머무는 이유도 여기에 있습니다.",
    ]), ("숫자로 정리하면", [
        "배당을 볼 때 '몇 배인가'보다 '이 배당이 실제 확률보다 후한가'를 먼저 봅니다. 사이트가 해외 배당으로 확률을 계산하고 화면에는 베트맨 배당을 보여 주는 것도, 두 숫자를 나란히 놓고 비교할 수 있게 하려는 것입니다.",
    ])]
    return A("payout-rate", "배당 안에 숨은 몫: 환급률과 조합 폴더 수", "공통",
             "배당에는 발매사의 몫이 들어 있습니다. 그 크기를 알면 왜 폴더 수를 무작정 늘리면 안 되는지, 어떤 마켓이 상대적으로 후한지 보입니다.", secs, tags=["환급률", "조합"])


def art_folders(games):
    by_day = defaultdict(list)
    for g in games:
        f = _fav(g)
        if f and 1.25 <= f[1] < 1.8:
            by_day[_kst(g["ko"]).date()].append((int(g["res"] == f[0]), f[1]))
    days = [v for v in by_day.values() if len(v) >= 5]
    if len(days) < 20:
        return None
    single = [x for v in days for x in v]
    p1 = sum(h for h, _ in single) / len(single)
    rng = random.Random(7)
    rows = []
    for n in (2, 3, 4, 5):
        hits = tot = 0
        odds = []
        for v in days:
            for _ in range(min(60, len(v) * 4)):
                c = rng.sample(v, n) if len(v) >= n else None
                if not c:
                    continue
                tot += 1
                hits += all(h for h, _ in c)
                o = 1.0
                for _, x in c:
                    o *= x
                odds.append(o)
        if tot >= 200:
            rows.append([f"{n}폴더", f"{tot:,}", pct(hits / tot), f"{sorted(odds)[len(odds) // 2]:.2f}배"])
    if len(rows) < 3:
        return None
    secs = [("같은 날 정배끼리 실제로 묶어 보면", [
        f"정배 배당 1.25~1.80 사이 경기들을 같은 날끼리 무작위로 묶어 실제 결과로 확인했습니다. 한 경기만 보면 이 구간 정배는 {pct(p1)} 맞았습니다.",
        ("table", ["폴더 수", "조합 수", "실제 적중", "보통의 배당"], rows),
        f"두 폴더만 돼도 적중은 {rows[0][2]}로 내려가고, 다섯 폴더면 {rows[-1][2]}입니다. 한 경기 한 경기는 높은 확률이어도 곱해지면 빠르게 줄어듭니다.",
    ]), ("체감과 실제의 차이", [
        "'다 70% 넘는 경기니까 넷 다 맞겠지'라는 느낌은 자연스럽지만, 네 경기의 적중은 대략 70%의 네제곱인 24% 근처입니다. 이 차이를 숫자로 알고 있으면 조합을 고를 때 욕심을 조절하기 쉬워집니다.",
        "조합에서 가장 흔한 아쉬움은 한 경기 차이입니다. 그 한 경기는 대개 확신이 가장 낮았던 경기입니다. 묶기 전에 가장 자신 없는 한 경기를 빼 보는 습관만으로도 적중이 눈에 띄게 달라집니다.",
    ]), ("폴더 수를 정하는 기준", [
        "목표 배당을 먼저 정하고 그에 맞춰 폴더 수를 고르는 방식보다, 확신하는 경기 수에 맞춰 폴더 수를 정하는 편이 기록이 안정적입니다. 사이트 전략별 조합의 안정형·밸런스형·공격형도 같은 원리로 폴더 수와 배당 구간을 나눠 둔 것입니다.",
    ])]
    return A("folders", "폴더를 늘리면 적중은 얼마나 줄까: 실제 기록으로 묶어 본 조합", "공통",
             "조합은 폴더가 늘 때마다 배당이 커지는 대신 적중이 줄어듭니다. 그 속도가 얼마나 빠른지, 지난 경기들을 실제로 묶어서 확인했습니다.", secs, tags=["조합", "폴더"])


def art_streaks(games):
    seq = defaultdict(list)
    for g in games:
        for side, team in ((0, g["home"]), (2, g["away"])):
            seq[(g["sport"], team)].append((g, side))
    acc = {"lose3": [0, 0, 0.0], "win3": [0, 0, 0.0]}
    for (sp, team), lst in seq.items():
        streak_w = streak_l = 0
        for g, side in lst:
            p = fair(g["o"])[side]
            won = g["res"] == side
            if streak_l >= 3:
                a = acc["lose3"]; a[0] += 1; a[1] += int(won); a[2] += p
            if streak_w >= 3:
                a = acc["win3"]; a[0] += 1; a[1] += int(won); a[2] += p
            if won:
                streak_w, streak_l = streak_w + 1, 0
            elif g["res"] == 1:
                streak_w = streak_l = 0
            else:
                streak_l, streak_w = streak_l + 1, 0
    if acc["lose3"][0] < 60 or acc["win3"][0] < 60:
        return None
    L, W = acc["lose3"], acc["win3"]
    lh, le = L[1] / L[0], L[2] / L[0]
    wh, we = W[1] / W[0], W[2] / W[0]
    secs = [("연패 팀은 반등할까", [
        f"3연패 이상인 팀이 다음 경기에서 이긴 비율은 {pct(lh)}였습니다({L[0]:,}경기). 같은 경기들의 배당 기준 승리 확률은 {pct(le)}였습니다. "
        + ("배당이 말한 것과 거의 같습니다. '이제 이길 때가 됐다'는 느낌은 결과에 따로 보태지는 게 없다는 뜻입니다." if abs(lh - le) < 0.03 else
           f"배당보다 {pp(lh - le)} {'더 이겼습니다' if lh > le else '덜 이겼습니다'}. 표본이 더 쌓이면서 이 차이가 유지되는지가 관건입니다."),
    ]), ("연승 팀은 계속 이길까", [
        f"3연승 이상인 팀은 다음 경기에서 {pct(wh)} 이겼고, 배당 기준 확률은 {pct(we)}였습니다. "
        + ("이것도 배당과 비슷합니다. 연승 흐름은 이미 배당에 들어가 있습니다." if abs(wh - we) < 0.03 else
           f"배당보다 {pp(wh - we)} 차이가 났습니다. 흐름이 배당에 다 담기지 않았을 가능성이 있는 대목입니다."),
        ("table", ["직전 흐름", "경기 수", "다음 경기 승", "배당 기준 확률"],
         [["3연패 이상", f"{L[0]:,}", pct(lh), pct(le)], ["3연승 이상", f"{W[0]:,}", pct(wh), pct(we)]]),
    ]), ("흐름을 보는 올바른 방법", [
        "연승·연패는 눈에 잘 들어오는 정보라 판단에 크게 끼어듭니다. 하지만 배당을 정하는 쪽도 같은 정보를 보고 있습니다. 흐름만으로 반대쪽을 고르거나 같은 쪽을 고르기보다, 흐름이 생긴 이유(부상 복귀, 일정, 상대 수준)를 보는 편이 의미 있습니다.",
        "내 기록도 마찬가지입니다. 몇 번 연속 빗나간 뒤 '이번엔 맞겠지' 하며 금액을 키우는 것은 위 숫자와 같은 착각에 기대는 것입니다. 직전 결과와 관계없이 같은 기준, 같은 금액을 유지하는 쪽이 오래 갑니다.",
    ])]
    return A("streaks", "연승·연패는 다음 경기에 영향을 줄까", "공통",
             "'연패 팀은 반등한다', '흐름 탄 팀은 계속 이긴다'는 말을 실제 기록으로 확인했습니다. 결과는 배당과 나란히 놓고 봐야 의미가 있습니다.", secs, tags=["흐름", "심리"])


def art_movement(games):
    acc = {"drop": [0, 0, 0.0], "rise": [0, 0, 0.0]}
    for g in games:
        op = g["open"]
        if not op or not op[0] or not op[2]:
            continue
        for i in (0, 2):
            if not op[i] or not g["o"][i]:
                continue
            ch = (g["o"][i] - op[i]) / op[i]
            p = fair(g["o"])[i]
            hit = int(g["res"] == i)
            k = "drop" if ch <= -0.03 else "rise" if ch >= 0.03 else None
            if k:
                a = acc[k]; a[0] += 1; a[1] += hit; a[2] += p
    if acc["drop"][0] < 80 or acc["rise"][0] < 80:
        return None
    D, R = acc["drop"], acc["rise"]
    secs = [("처음 배당과 마지막 배당", [
        "베트맨 배당은 발매 뒤에도 바뀝니다. 한쪽에 구매가 몰리면 그쪽 배당이 내려가고 반대쪽이 올라갑니다. 처음 배당보다 3% 이상 내려간 쪽과 올라간 쪽이 실제로 어떻게 끝났는지 셌습니다.",
        ("table", ["배당 변화", "선택 수", "실제 적중", "마지막 배당 기준 확률", "차이"],
         [["3% 이상 내려감", f"{D[0]:,}", pct(D[1] / D[0]), pct(D[2] / D[0]), pp(D[1] / D[0] - D[2] / D[0])],
          ["3% 이상 올라감", f"{R[0]:,}", pct(R[1] / R[0]), pct(R[2] / R[0]), pp(R[1] / R[0] - R[2] / R[0])]]),
        "마지막 배당은 이미 변화를 반영한 숫자입니다. 그래서 '내려간 쪽이 많이 이긴다'만으로는 부족하고, 마지막 배당 기준 확률보다 더 이겼는지를 봐야 합니다.",
    ]), ("읽는 법", [
        ("내려간 쪽이 마지막 배당보다도 더 이겼다면, 구매가 몰린 방향에 배당이 다 담지 못한 정보가 있었다는 뜻입니다. " if D[1] / D[0] > D[2] / D[0] + 0.01 else
         "내려간 쪽도 마지막 배당이 말한 만큼만 이겼습니다. 구매 쏠림은 배당에 충분히 반영된다는 뜻이고, 쏠림을 따라가는 것만으로 생기는 이점은 크지 않습니다. "),
        "배당 변화는 경기 페이지의 배당 흐름 차트에서 시각별로 볼 수 있습니다. 변화가 큰 경기는 부상·결장 같은 소식이 있었을 가능성이 있으니 이유를 한 번 확인해 보는 계기로 쓰면 좋습니다.",
        "배당이 크게 움직인 경기일수록 처음 판단을 고집하기보다, 바뀐 배당으로 다시 계산해 보는 편이 맞습니다. 같은 선택이라도 배당이 내려가면 기대치가 달라집니다.",
    ])]
    return A("odds-movement", "배당이 움직인 쪽은 이길까: 처음 배당과 마지막 배당", "공통",
             "발매 뒤 배당이 내려간 쪽과 올라간 쪽, 실제 결과는 어떻게 갈렸을까요. 마지막 배당과 나란히 놓고 비교했습니다.", secs, tags=["배당 흐름"])


def art_timeofday(games):
    acc = defaultdict(lambda: [0, 0, 0.0])
    for g in games:
        f = _fav(g)
        if not f:
            continue
        h = _kst(g["ko"]).hour
        slot = "새벽(0~6시)" if h < 7 else "오전(7~11시)" if h < 12 else "오후(12~17시)" if h < 18 else "저녁(18~23시)"
        a = acc[(g["sport"], slot)]
        a[0] += 1; a[1] += int(g["res"] == f[0]); a[2] += fair(g["o"])[f[0]]
    order = ["새벽(0~6시)", "오전(7~11시)", "오후(12~17시)", "저녁(18~23시)"]
    rows = [[SPORT_KO.get(s, s), t, f"{v[0]:,}", pct(v[1] / v[0]), pp(v[1] / v[0] - v[2] / v[0])]
            for s in SPORT_KO for t in order for v in [acc.get((s, t))] if v and v[0] >= 60]
    if len(rows) < 4:
        return None
    best = max(rows, key=lambda r: float(r[4].replace("%p", "")))
    secs = [("한국 시간으로 본 경기 시작 시각", [
        "베트맨에는 국내 경기와 해외 경기가 함께 발매되어 경기 시각이 새벽부터 밤까지 퍼져 있습니다. 시작 시각대별로 정배의 실제 적중을 배당과 비교했습니다.",
        ("table", ["종목", "시간대", "경기 수", "정배 적중", "배당 대비"], rows),
        f"배당보다 정배가 가장 잘 버틴 칸은 {best[0]} {best[1]}({best[4]})입니다. 시간대는 곧 리그의 차이이기도 합니다. 새벽은 유럽·미주 경기, 저녁은 국내·일본 경기가 많습니다.",
    ]), ("시간대를 활용하는 법", [
        "새벽 경기는 결과를 보기 전에 잠드는 경우가 많아 확인이 늦어집니다. 조합에 새벽 경기를 섞을 때는 같은 회차의 다른 경기들과 시간 간격도 함께 생각해 두면 좋습니다.",
        "시간대 차이가 배당 대비 크게 벌어지는 칸은 표본이 쌓이면서 다시 확인합니다. 이 표도 매일 자동으로 다시 계산됩니다.",
    ])]
    return A("time-of-day", "경기 시각에 따라 달라질까: 시간대별 정배 기록", "공통",
             "새벽에 열리는 해외 경기와 저녁의 국내 경기, 시간대에 따라 정배의 무게가 달라지는지 확인했습니다.", secs, tags=["시간대"])


def art_us_margins(us):
    nba, mlb = us.get("nba") or [], us.get("mlb") or []
    if len(nba) < 2000 or len(mlb) < 2000:
        return None
    nm = [abs(h - a) for _, h, a, _ in nba]
    mm = [abs(h - a) for _, h, a, _ in mlb]
    def share(lst, f):
        return sum(1 for x in lst if f(x)) / len(lst)
    rows = [["NBA 5점 차 이내", pct(share(nm, lambda x: x <= 5))], ["NBA 10점 차 이상", pct(share(nm, lambda x: x >= 10))],
            ["NBA 20점 차 이상", pct(share(nm, lambda x: x >= 20))], ["MLB 1점 차", pct(share(mm, lambda x: x == 1))],
            ["MLB 3점 차 이상", pct(share(mm, lambda x: x >= 3))]]
    fav_n = [(p, h > a) for p, h, a, _ in nba]
    big = [w for p, w in fav_n if p >= 0.8]
    over_n = [(h + a) > t for _, h, a, t in nba if t]
    over_m = [(h + a) > t for _, h, a, t in mlb if t and (h + a) != t]
    secs = [("점수 차는 어떻게 나뉘나", [
        f"NBA {len(nba):,}경기와 MLB {len(mlb):,}경기의 최종 점수 차를 셌습니다. 핸디캡 기준점을 볼 때 '이 정도 차이가 얼마나 흔한가'를 아는 기준표입니다.",
        ("table", ["구분", "비율"], rows),
        "NBA는 접전과 대승이 고루 섞여 있어서 큰 기준점도 자주 넘어갑니다. MLB는 1점 차 경기가 많아 런라인(-1.5) 같은 기준점에서 결과가 크게 갈립니다.",
    ]), ("강한 정배가 지는 경우", [
        (f"배당 기준 승리 확률 80% 이상인 NBA 경기에서 정배는 {pct(sum(big) / len(big))} 이겼습니다({len(big):,}경기). " if len(big) >= 100 else "")
        + "확률이 높아도 열 번 중 한두 번은 뒤집힙니다. 시즌 막판 주전 휴식이나 연전 일정이 이런 경기의 주된 원인입니다.",
    ]), ("합계 점수 기준점", [
        f"NBA 합계 기준점 경기에서 오버는 {pct(sum(over_n) / len(over_n))}, MLB는 {pct(sum(over_m) / len(over_m))}였습니다. 기준점은 반반에 가깝게 정해지기 때문에, 오래 쌓인 기록에서도 한쪽으로 크게 기울지 않습니다.",
        "그래서 합계 점수는 리그 전체 경향보다 두 팀의 최근 페이스와 일정(연전, 원정 연속)을 보는 쪽이 판단 근거가 됩니다.",
    ])]
    return A("nba-mlb-margins", "NBA·MLB 점수 차와 합계 점수: 10시즌 기록으로 본 기준", "공통",
             "핸디캡과 언더오버 기준점을 볼 때 필요한 감각은 '이 점수 차가 얼마나 흔한가'입니다. 미국 프로농구·야구 10시즌 기록으로 기준표를 만들었습니다.", secs, sport="basketball", tags=["NBA", "MLB", "핸디캡", "언더오버"])


def art_bankroll(games):
    """금액 관리: 정배 적중률로 연속 빗나감이 얼마나 흔한지 계산."""
    fav = [(int(g["res"] == f[0]), f[1]) for g in games for f in [_fav(g)] if f and 1.4 <= f[1] < 1.9]
    if len(fav) < 300:
        return None
    p = sum(h for h, _ in fav) / len(fav)
    # 100번 중 가장 긴 연속 빗나감(실제 순서)
    runs, cur = [], 0
    for h, _ in fav:
        if h:
            if cur:
                runs.append(cur)
            cur = 0
        else:
            cur += 1
    longest = max(runs) if runs else 0
    r3 = sum(1 for r in runs if r >= 3) / max(1, len(fav)) * 100
    secs = [("적중률이 높아도 연속으로 빗나갑니다", [
        f"정배 배당 1.40~1.90 경기 {len(fav):,}개를 시간 순서대로 늘어놓으면, 이 구간 정배는 {pct(p)} 맞았습니다. "
        f"그래도 같은 순서 안에서 연속으로 빗나간 가장 긴 구간은 {longest}경기였고, 3경기 이상 연속으로 빗나간 구간은 100경기당 {r3:.1f}번 나왔습니다.",
        "확률이 높은 선택을 꾸준히 해도 몇 번 연속으로 빗나가는 구간은 반드시 옵니다. 문제는 그 구간이 아니라 그 구간에서 금액을 키우는 습관입니다.",
    ]), ("금액을 정하는 기준", [
        "한 번에 쓰는 금액을 전체 예산의 작은 비율로 고정하면, 연속으로 빗나가는 구간이 와도 기록을 이어갈 수 있습니다. 사이트 금액 계산기의 켈리 기준 금액은 확률과 배당으로 이 비율을 계산해 줍니다.",
        "켈리 기준은 이론상 가장 빨리 늘어나는 비율이지만 흔들림도 큽니다. 계산기 기본값이 그 일부만 쓰는 이유입니다. 처음에는 계산된 금액보다 작게 시작해 내 기록과 숫자가 비슷하게 가는지 확인하는 편이 좋습니다.",
    ]), ("오래 가는 사람들의 공통점", [
        "잃어도 괜찮은 소액으로, 미리 정한 기준대로만 합니다. 결과가 좋든 나쁘든 다음 선택의 금액이 바뀌지 않습니다. 기록을 남기고 한 달에 한 번 숫자로 돌아봅니다. 사이트의 성과 페이지가 같은 방식으로 모든 픽을 남겨 두는 이유입니다.",
        "과몰입이 느껴질 때는 한국도박문제예방치유원 국번 없이 1336(24시간, 무료)에서 상담받을 수 있습니다.",
    ])]
    return A("bankroll", "연속으로 빗나가는 구간은 반드시 옵니다: 금액 관리의 기준", "공통",
             "적중률이 높은 선택만 해도 연속으로 빗나가는 날은 옵니다. 실제 기록으로 그 길이를 확인하고, 금액을 어떻게 정해야 오래 가는지 정리했습니다.", secs, tags=["금액 관리", "심리"])


# ───────────────────────── 리그 비교(유럽 축구 장기 기록) ─────────────────────────
def _fd_stats(fd):
    out = {}
    for code, rows in fd.items():
        if len(rows) < 800:
            continue
        n = len(rows)
        hw = sum(1 for r in rows if r[3] == 0) / n
        dr = sum(1 for r in rows if r[3] == 1) / n
        goals = sum(r[6] for r in rows) / n
        o25 = sum(1 for r in rows if r[6] >= 3) / n
        favs = [(min(r[0], r[2]), (r[3] == 0) if r[0] < r[2] else (r[3] == 2), fair(r[:3])[0 if r[0] < r[2] else 2]) for r in rows if r[0] and r[2] and r[0] != r[2]]
        fv = [x for x in favs if x[0] < 1.6]
        fhit = sum(1 for x in fv if x[1]) / len(fv) if fv else 0
        fexp = sum(x[2] for x in fv) / len(fv) if fv else 0
        nil = sum(1 for r in rows if len(r) > 8 and (r[7] == 0 or r[8] == 0)) / n
        out[code] = {"n": n, "home": hw, "draw": dr, "away": 1 - hw - dr, "goals": goals, "o25": o25, "fav16": fhit, "fav16e": fexp, "nfav": len(fv), "nil": nil}
    return out


def art_compare(fd):
    st = _fd_stats(fd)
    if len(st) < 8:
        return []
    arts = []
    def table(key, fmt, head):
        rk = sorted(st.items(), key=lambda kv: -kv[1][key])
        return rk, ("table", ["리그", "경기 수", head], [[FD_NAME.get(c, c), f"{v['n']:,}", fmt(v[key])] for c, v in rk])
    rk, t = table("goals", lambda x: f"{x:.2f}골", "경기당 골")
    rk2, t2 = table("o25", pct, "3골 이상")
    hi, lo = rk[0], rk[-1]
    arts.append(A("compare-goals", "골이 많은 리그, 적은 리그: 유럽 16개 리그 비교", "리그 비교",
                  "언더오버를 고르기 전에 그 리그가 원래 골이 많은 곳인지 알아야 합니다. 유럽 16개 리그 여러 시즌 기록으로 비교했습니다.",
                  [("경기당 골", [f"가장 골이 많은 곳은 {FD_NAME.get(hi[0], hi[0])}({hi[1]['goals']:.2f}골), 가장 적은 곳은 {FD_NAME.get(lo[0], lo[0])}({lo[1]['goals']:.2f}골)입니다. 경기당 0.5골 차이는 크지 않아 보여도 2.5 기준점에서는 결과를 자주 바꿉니다.", t]),
                   ("3골 이상 나온 비율(오버 2.5)", ["언더오버 2.5 기준으로 오버가 나온 비율입니다. 50%를 넘는 리그는 기본적으로 오버 쪽으로 기울어 있고, 40%대 리그는 언더 쪽 선택이 자연스럽습니다.", t2,
                     f"오버 비율 1위 {FD_NAME.get(rk2[0][0], rk2[0][0])}({pct(rk2[0][1]['o25'])})와 꼴찌 {FD_NAME.get(rk2[-1][0], rk2[-1][0])}({pct(rk2[-1][1]['o25'])})의 차이는 {pp(rk2[0][1]['o25'] - rk2[-1][1]['o25'])}입니다. 같은 2.5 기준점이라도 리그에 따라 출발점이 이만큼 다릅니다."]),
                   ("활용", ["리그 평균은 출발점일 뿐이고, 실제 판단은 두 팀의 득점·실점 흐름을 더해서 합니다. 골이 많은 리그에서 수비가 약한 두 팀이 만나면 오버 근거가 겹치고, 골이 적은 리그에서 수비가 좋은 팀이 만나면 언더 근거가 겹칩니다.",
                             "1부와 2부 리그를 비교해 보면 2부가 대체로 골이 적은 편입니다. 전력 차가 크지 않아 조심스러운 경기가 많기 때문입니다."])],
                  tags=["리그 비교", "언더오버", "축구"], sport="soccer"))
    rk, t = table("draw", pct, "무승부")
    arts.append(A("compare-draws", "무승부가 많은 리그: 유럽 16개 리그 무승부·홈 승률 비교", "리그 비교",
                  "승무패 조합에서 무승부는 가장 자주 계산에서 빠지는 결과입니다. 리그별 무승부 비율과 홈 승률을 나란히 봤습니다.",
                  [("리그별 무승부", [t, f"무승부가 가장 잦은 곳은 {FD_NAME.get(rk[0][0], rk[0][0])}({pct(rk[0][1]['draw'])}), 가장 드문 곳은 {FD_NAME.get(rk[-1][0], rk[-1][0])}({pct(rk[-1][1]['draw'])})입니다. 무승부가 잦은 리그는 승무패에서 한쪽 승을 고르기보다 핸디캡이나 언더오버가 편할 때가 많습니다."]),
                   ("리그별 홈 승률", [("table", ["리그", "홈 승", "무", "원정 승"], [[FD_NAME.get(c, c), pct(v["home"]), pct(v["draw"]), pct(v["away"])] for c, v in sorted(st.items(), key=lambda kv: -kv[1]["home"])]),
                                    "홈 승률이 높은 리그일수록 원정 정배가 덜 믿을 만합니다. 원정 팀이 정배로 나온 경기는 이 표의 홈 승률과 같이 보면 판단이 빨라집니다."]),
                   ("무승부를 계산에 넣는 법", ["무승부 비율이 25%인 리그에서 세 경기를 묶으면 셋 다 무승부가 아닐 확률은 대략 42%입니다. 승과 패만 보고 고른 조합은 이 몫을 비워 둔 채로 시작하는 셈입니다. 무승부가 잦은 리그는 조합에서 한 칸 이하로 줄이는 것만으로도 기록이 안정됩니다."])],
                  tags=["리그 비교", "무승부", "축구"], sport="soccer"))
    rk = sorted(st.items(), key=lambda kv: -(kv[1]["fav16"] - kv[1]["fav16e"]))
    arts.append(A("compare-favorites", "정배가 믿을 만한 리그: 유럽 리그별 1.6배 미만 정배 기록", "리그 비교",
                  "같은 1.5배 정배라도 리그에 따라 실제로 이기는 비율이 다릅니다. 배당과 실제 결과의 차이를 리그별로 비교했습니다.",
                  [("1.6배 미만 정배의 실제 적중", [("table", ["리그", "정배 경기", "실제 적중", "배당 기준 확률", "차이"],
                                                  [[FD_NAME.get(c, c), f"{v['nfav']:,}", pct(v["fav16"]), pct(v["fav16e"]), pp(v["fav16"] - v["fav16e"])] for c, v in rk if v["nfav"] >= 150]),
                                                 f"배당보다 정배가 더 잘 버틴 리그는 {FD_NAME.get(rk[0][0], rk[0][0])}({pp(rk[0][1]['fav16'] - rk[0][1]['fav16e'])}), 덜 버틴 리그는 {FD_NAME.get(rk[-1][0], rk[-1][0])}({pp(rk[-1][1]['fav16'] - rk[-1][1]['fav16e'])})입니다."]),
                   ("왜 리그마다 다를까", ["상위권과 하위권의 전력 차가 큰 리그는 강팀이 꾸준히 이깁니다. 전력이 고른 리그는 약팀의 홈 경기에서 이변이 자주 나옵니다. 배당은 이 차이를 대부분 반영하지만 완전히 따라가지는 못합니다.",
                                        "정배를 조합의 기둥으로 쓸 때는 배당보다 꾸준히 더 이긴 리그의 경기를 먼저 넣고, 배당만큼 이기지 못한 리그는 한 칸 정도로만 두는 편이 무리가 없습니다."])],
                  tags=["리그 비교", "정배", "축구"], sport="soccer"))
    return arts


# ───────────────────────── 리그별 글(베트맨 기록) ─────────────────────────
def art_league(lk, name, sport, games, ou, hc):
    gs = [g for g in games if g["lk"] == lk]
    if len(gs) < 150:
        return None
    n = len(gs)
    hw = sum(1 for g in gs if g["res"] == 0) / n
    dr = sum(1 for g in gs if g["res"] == 1) / n
    aw = 1 - hw - dr
    hexp = sum(fair(g["o"])[0] for g in gs) / n
    favs = [(g, _fav(g)) for g in gs if _fav(g)]
    fhit = sum(1 for g, f in favs if g["res"] == f[0]) / len(favs)
    fexp = sum(fair(g["o"])[f[0]] for g, f in favs) / len(favs)
    upset = sum(1 for g, f in favs if g["res"] == 2 - f[0]) / len(favs)
    bands = fav_by_band(gs, min_n=25)
    lou = [x for x in ou if x["lk"] == lk]
    over = sum(1 for x in lou if x["res"] == (2 if x["uf"] else 0)) / len(lou) if len(lou) >= 60 else None
    lhc = [x for x in hc if x["lk"] == lk and x["line"]]
    plus = sum(1 for x in lhc if x["res"] == (0 if x["line"] > 0 else 2)) / len(lhc) if len(lhc) >= 60 else None
    margins = [abs((g["hs"] or 0) - (g["as"] or 0)) for g in gs if g["hs"] is not None and g["as"] is not None]
    close = sum(1 for m in margins if m <= (1 if sport in ("soccer", "baseball") else 5 if sport == "basketball" else 0)) / len(margins) if margins else None
    sp = SPORT_KO.get(sport, sport)
    home_txt = ("홈팀이 배당보다 더 이겼습니다" if hw - hexp > 0.02 else "원정팀이 배당이 말한 것보다 선전했습니다" if hw - hexp < -0.02 else "홈 이점이 배당에 거의 그대로 반영돼 있습니다")
    fav_txt = ("정배가 배당보다 꾸준히 더 이긴 리그입니다. 조합의 기둥으로 쓰기 좋은 편입니다." if fhit - fexp > 0.02 else
               "정배가 배당만큼 이기지 못한 리그입니다. 이변을 한 번 더 의심해 볼 만합니다." if fhit - fexp < -0.02 else
               "정배가 배당이 말한 만큼 이긴 리그입니다. 배당을 그대로 믿어도 크게 어긋나지 않았습니다.")
    secs = [(f"{name} 기본 숫자", [
        f"베트맨에 발매된 {name} {n:,}경기의 결과입니다. 홈 승 {pct(hw)}, " + (f"무승부 {pct(dr)}, " if dr > 0.001 else "") + f"원정 승 {pct(aw)}였고, 배당 기준 홈 확률은 {pct(hexp)}였습니다. {home_txt}.",
        ("table", ["항목", "값"], [r for r in [
            ["경기 수", f"{n:,}"], ["홈 승", pct(hw)], ["무승부", pct(dr)] if dr > 0.001 else None, ["원정 승", pct(aw)],
            ["정배 적중", pct(fhit)], ["역배 적중", pct(upset)],
            ["오버 비율", pct(over)] if over is not None else None,
            ["핸디 받은 쪽 적중", pct(plus)] if plus is not None else None,
            [("1점 차 이내" if sport in ("soccer", "baseball") else "5점 차 이내" if sport == "basketball" else "접전") + " 경기", pct(close)] if close is not None and sport != "volleyball" else None,
        ] if r]),
    ]), ("정배와 역배", [
        f"{name}에서 배당이 낮은 쪽은 {pct(fhit)} 이겼고, 배당 기준 확률은 {pct(fexp)}였습니다. {fav_txt} "
        f"반대로 역배가 이긴 경기는 {pct(upset)}로, 대략 {max(2, round(1 / max(upset, 0.01)))}경기에 한 번꼴입니다.",
    ] + ([("table", ["정배 배당", "경기 수", "실제 적중", "배당 기준 확률"], [[b["band"], f"{b['n']:,}", pct(b["hit"]), pct(b["exp"])] for b in bands])] if len(bands) >= 2 else []))]
    hf = [(g, f) for g, f in favs if f[0] == 0]
    af = [(g, f) for g, f in favs if f[0] == 2]
    hfr = sum(1 for g, f in hf if g["res"] == 0) / len(hf) if len(hf) >= 40 else None
    afr = sum(1 for g, f in af if g["res"] == 2) / len(af) if len(af) >= 40 else None
    tot = [((g["hs"] or 0) + (g["as"] or 0)) for g in gs if g["hs"] is not None and g["as"] is not None]
    mv = [(g, i) for g in gs for i in (0, 2) if g["open"] and g["open"][i] and (g["o"][i] - g["open"][i]) / g["open"][i] <= -0.03]
    para = []
    if hfr is not None and afr is not None:
        para.append(f"홈팀이 정배일 때는 {pct(hfr)}({len(hf):,}경기), 원정팀이 정배일 때는 {pct(afr)}({len(af):,}경기) 이겼습니다. "
                    + ("원정 정배가 눈에 띄게 덜 버티는 리그라 원정 정배는 조합에서 무게를 덜어 두는 편이 좋습니다." if hfr - afr > 0.05 else
                       "원정 정배가 오히려 더 잘 버틴 리그입니다. 원정팀이 정배로 나왔다면 전력 차가 뚜렷한 경우가 많았다는 뜻입니다." if afr - hfr > 0.05 else
                       "홈과 원정 정배의 차이가 크지 않아, 정배 여부는 배당대로 판단해도 무리가 적습니다."))
    if tot:
        unit = "골" if sport == "soccer" else "점"
        para.append(f"한 경기 평균 합계는 {sum(tot) / len(tot):.1f}{unit}이었습니다. 언더오버 기준점이 이 평균에서 크게 벗어나 있다면 그날 경기에 특별한 사정이 있는지 먼저 확인해 볼 만합니다.")
    if len(mv) >= 40:
        mh = sum(1 for g, i in mv if g["res"] == i) / len(mv)
        me = sum(fair(g["o"])[i] for g, i in mv) / len(mv)
        para.append(f"발매 뒤 배당이 3% 이상 내려간 쪽은 {len(mv):,}번 중 {pct(mh)} 이겼고, 마지막 배당 기준 확률은 {pct(me)}였습니다. "
                    + ("구매가 몰린 쪽이 배당보다도 더 이겨, 이 리그에서는 배당 흐름을 참고할 가치가 있습니다." if mh > me + 0.02 else
                       "배당이 내려간 쪽도 배당만큼만 이겨, 구매 쏠림만 보고 따라가는 이점은 크지 않았습니다."))
    if para:
        secs.append(("홈 정배와 원정 정배, 점수와 배당 흐름", para))
    extra = []
    if over is not None:
        extra.append(f"언더오버는 {len(lou):,}경기 중 오버가 {pct(over)}였습니다. " + ("오버 쪽으로 기운 리그라 언더를 고를 때는 근거를 한 번 더 확인하는 편이 좋습니다." if over > 0.53 else
                     "언더 쪽으로 기운 리그라 오버를 고를 때는 두 팀 득점 흐름이 받쳐 주는지 확인하는 편이 좋습니다." if over < 0.47 else "어느 한쪽으로 크게 기울지 않아 경기별 판단이 중요합니다."))
    if plus is not None:
        extra.append(f"핸디캡에서 기준점을 받은 쪽(약팀)은 {len(lhc):,}경기 중 {pct(plus)} 버텼습니다. " + ("강팀이 기준점만큼 이기지 못한 경기가 많았다는 뜻입니다." if plus > 0.52 else
                     "강팀이 기준점 이상으로 이긴 경기가 많았다는 뜻입니다." if plus < 0.48 else "기준점이 점수 차를 잘 맞힌 리그입니다."))
    if close is not None and sport != "volleyball":
        extra.append(f"점수 차가 작은 경기는 {pct(close)}였습니다. " + ("접전이 많아 핸디캡 기준점 근처에서 결과가 자주 갈립니다." if close > 0.4 else "한쪽으로 크게 기우는 경기가 많아 큰 기준점도 자주 넘어갑니다."))
    if extra:
        secs.append(("언더오버·핸디캡·점수 차", extra))
    secs.append((f"{name} 경기를 볼 때", [
        f"{name} 경기는 위 숫자를 출발점으로 삼고, 그날 두 팀의 최근 흐름과 배당 변화를 더해 판단합니다. 리그 순위와 팀별 기록은 리그·순위 메뉴의 {name} 페이지에서, 경기별 분석은 첫 화면과 경기 분석 메뉴에서 볼 수 있습니다.",
        f"이 글의 숫자는 {sp} 경기 결과가 쌓일 때마다 자동으로 다시 계산됩니다. 경기 수가 적은 항목은 다음 결과에 따라 쉽게 움직이니, 큰 차이보다 꾸준한 방향을 보는 편이 좋습니다.",
    ]))
    return A(f"league-{re.sub(r'[^0-9a-z가-힣]+', '-', lk.lower()).strip('-')}", f"{name} 기록으로 본 특징: 정배·홈·언더오버", "리그별",
             f"베트맨에 발매된 {name} 경기만 모아 홈 승률, 정배와 역배, 언더오버와 핸디캡 결과를 정리했습니다. 숫자는 경기가 쌓일 때마다 자동으로 다시 계산됩니다.",
             secs, league=name, sport=sport, tags=[name, sp])


def art_fd_league(code, rows, allst=None):
    if len(rows) < 800:
        return None
    st = _fd_stats({code: rows})[code]
    name = FD_NAME.get(code, code)
    edges = [(1.0, 1.4), (1.4, 1.8), (1.8, 2.3), (2.3, 99)]
    acc = defaultdict(lambda: [0, 0, 0.0])
    for r in rows:
        if not r[0] or not r[2] or r[0] == r[2]:
            continue
        side = 0 if r[0] < r[2] else 2
        b = _band(min(r[0], r[2]), edges)
        a = acc[b]; a[0] += 1; a[1] += int(r[3] == side); a[2] += fair(r[:3])[side]
    brow = [[b, f"{v[0]:,}", pct(v[1] / v[0]), pct(v[2] / v[0])] for lo, hi in edges for b in [_band(lo, [(lo, hi)])] for v in [acc.get(b)] if v and v[0] >= 50]
    gd = Counter(min(r[6], 6) for r in rows)
    grow = [[("6골 이상" if k == 6 else f"{k}골"), pct(v / len(rows))] for k, v in sorted(gd.items())]
    secs = [(f"{name} 기본 숫자", [
        f"{name} {st['n']:,}경기(최근 여러 시즌)의 결과입니다. 홈 승 {pct(st['home'])}, 무승부 {pct(st['draw'])}, 원정 승 {pct(st['away'])}, 경기당 {st['goals']:.2f}골이 나왔고 3골 이상 경기는 {pct(st['o25'])}였습니다.",
        ("table", ["정배 배당", "경기 수", "실제 적중", "배당 기준 확률"], brow) if brow else "",
    ]), ("골 수 분포", [
        "한 경기에 나온 골 수의 비율입니다. 언더오버 기준점을 고를 때 어느 구간이 가장 흔한지 보는 표입니다.",
        ("table", ["총 골", "비율"], grow),
        ("이 리그는 3골 이상 경기가 절반을 넘어 오버 2.5가 기본값에 가깝습니다." if st["o25"] > 0.52 else
         "이 리그는 2골 이하 경기가 더 많아 언더 2.5 쪽이 기본값에 가깝습니다." if st["o25"] < 0.48 else
         "3골 이상과 2골 이하가 거의 반반이라 경기별 판단이 중요한 리그입니다.")
        + f" 한 팀이라도 득점하지 못한 경기는 {pct(st['nil'])}였습니다.",
    ]), ("무승부와 홈 이점", [
        f"무승부 {pct(st['draw'])}는 " + ("유럽 리그 가운데 높은 편으로, 승무패 조합에 넣을 때 무승부 몫을 크게 잡아야 합니다." if st["draw"] > 0.27 else
                                       "유럽 리그 가운데 낮은 편으로, 승패가 갈리는 경기가 많습니다." if st["draw"] < 0.24 else "유럽 리그 평균 수준입니다.")
        + f" 홈 승률 {pct(st['home'])}는 " + ("홈 이점이 뚜렷한 편입니다." if st["home"] > 0.46 else "홈 이점이 약한 편이라 원정 정배도 충분히 고려할 만합니다." if st["home"] < 0.42 else "평균적인 수준입니다."),
        f"{name} 경기가 베트맨에 발매되면 첫 화면 경기 목록에서 이 리그로 묶여 나옵니다. 위 숫자를 출발점으로 그날의 배당과 두 팀 흐름을 더해 보면 됩니다.",
    ])]
    n = len(rows)
    tg = [r[6] for r in rows]
    lines = [[f"{x - 0.5:g}", pct(sum(1 for t in tg if t >= x) / n)] for x in (1, 2, 3, 4)]
    secs.insert(2, ("기준점별 오버 비율", [
        "같은 경기라도 기준점이 바뀌면 판단이 달라집니다. 이 리그에서 기준점별로 오버가 나온 비율입니다.",
        ("table", ["기준점", "오버"], lines),
        f"오버 1.5는 {lines[1][1]}, 오버 3.5는 {lines[3][1]}였습니다. 2.5가 애매하게 느껴지는 경기는 한 칸 낮추거나 높인 기준점의 비율을 함께 보면 감이 잡힙니다.",
    ]))
    fv = [r for r in rows if r[0] and r[2] and min(r[0], r[2]) < 1.6 and r[0] != r[2]]
    if len(fv) >= 150:
        hf = [r for r in fv if r[0] < r[2]]
        af = [r for r in fv if r[2] < r[0]]
        dr = sum(1 for r in fv if r[3] == 1) / len(fv)
        ls = sum(1 for r in fv if r[3] == (2 if r[0] < r[2] else 0)) / len(fv)
        hh = sum(1 for r in hf if r[3] == 0) / len(hf) if len(hf) >= 50 else None
        ah = sum(1 for r in af if r[3] == 2) / len(af) if len(af) >= 50 else None
        o_exp = [fair([r[4], r[5]])[0] for r in rows if r[4] and r[5]]
        o_act = [int(r[6] >= 3) for r in rows if r[4] and r[5]]
        secs.insert(-1, ("정배가 넘어질 때", [
            f"1.6배 미만 정배 {len(fv):,}경기에서 정배가 이기지 못한 경기는 무승부 {pct(dr)}, 패배 {pct(ls)}였습니다. "
            + ("넘어질 때 대부분 무승부라서, 이 리그 정배는 '지지 않는 쪽'으로 보면 훨씬 단단합니다." if dr > ls * 1.5 else
               "무승부보다 패배로 끝나는 경우가 많지 않아, 정배가 넘어질 때는 비기는 경우와 지는 경우가 비슷하게 섞여 있습니다." if dr > ls else
               "넘어질 때 무승부보다 패배가 많아, 정배를 고를 때 상대의 역습 능력까지 봐야 하는 리그입니다."),
            (f"홈 정배는 {pct(hh)}, 원정 정배는 {pct(ah)} 이겼습니다. " if hh is not None and ah is not None else "")
            + ("같은 배당대라도 원정 정배가 덜 버텨, 원정 정배를 고를 때는 한 번 더 확인하는 편이 좋습니다." if hh is not None and ah is not None and hh - ah > 0.04 else
               "홈과 원정 정배의 차이가 크지 않아 배당대만 보고 판단해도 무리가 적습니다." if hh is not None and ah is not None else ""),
        ] + ([f"오버 2.5 배당이 말한 확률은 평균 {pct(sum(o_exp) / len(o_exp))}, 실제 3골 이상은 {pct(sum(o_act) / len(o_act))}였습니다. "
              + ("시장이 이 리그의 골을 조금 적게 본 셈입니다." if sum(o_act) / len(o_act) > sum(o_exp) / len(o_exp) + 0.015 else
                 "시장이 이 리그의 골을 조금 많이 본 셈입니다." if sum(o_act) / len(o_act) < sum(o_exp) / len(o_exp) - 0.015 else
                 "시장의 기준점이 이 리그 골 수를 잘 맞혔습니다.")] if len(o_exp) >= 300 else [])))
    if allst and len(allst) >= 6:
        def rk(key, hi, lo):
            vals = sorted((v[key] for v in allst.values()), reverse=True)
            r = vals.index(st[key]) + 1
            return f"{hi} {r}위" if r <= len(vals) // 2 else f"{lo} {len(vals) - r + 1}위"
        others = sorted(((c, v) for c, v in allst.items() if c != code), key=lambda cv: abs(cv[1]["goals"] - st["goals"]) + abs(cv[1]["draw"] - st["draw"]))
        twin = FD_NAME.get(others[0][0], others[0][0]) if others else None
        secs.insert(-1, ("유럽 다른 리그와 비교", [
            f"유럽 {len(allst)}개 리그와 비교하면 {name}{josa(name)} 골 수 {rk('goals', '많은 순', '적은 순')}, 무승부 {rk('draw', '많은 순', '적은 순')}, 홈 승률 {rk('home', '높은 순', '낮은 순')}, 1.6배 미만 정배 적중 {rk('fav16', '높은 순', '낮은 순')}입니다.",
            (f"골 수와 무승부 성향이 가장 비슷한 리그는 {twin}입니다. 두 리그 경기는 같은 기준으로 판단해도 크게 어긋나지 않습니다. " if twin else "")
            + ("정배가 배당보다 잘 버티는 편이라 조합의 기둥으로 쓰기 좋습니다." if st["fav16"] > st["fav16e"] + 0.015 else
               "정배가 배당만큼 버티지 못하는 편이라 이변을 한 번 더 의심해 볼 만합니다." if st["fav16"] < st["fav16e"] - 0.015 else
               "정배가 배당과 거의 같은 비율로 이겨 배당을 그대로 믿어도 크게 어긋나지 않습니다."),
        ]))
    return A(f"fd-{code.lower()}", f"{name}{josa(name)} 어떤 리그일까: 골·무승부·정배 기록", "유럽 축구",
             f"{name} 여러 시즌의 결과와 배당 기록으로 이 리그만의 특징을 정리했습니다. 숫자는 새 시즌 기록이 들어올 때마다 자동으로 다시 계산됩니다.",
             secs, league=name, sport="soccer", tags=[name, "축구"])



# ───────────────────────── 공통 글 덧붙임(주제별 설명) ─────────────────────────
EXTRA = {
    "favorites-by-odds": [("배당 기준 확률은 어떻게 계산했나", [
        "베트맨 배당을 그대로 확률로 바꾸면(1÷배당) 모든 결과의 합이 100%를 넘습니다. 넘치는 부분이 발매사의 몫입니다. 이 글의 '배당 기준 확률'은 그 몫을 결과마다 같은 비율로 걷어 내 합이 100%가 되게 맞춘 값입니다. 그래서 실제 적중과 바로 비교할 수 있습니다.",
        "예를 들어 승 1.50, 패 2.50이면 그대로 바꾼 확률은 66.7%와 40.0%로 합이 106.7%입니다. 합으로 나누면 62.5%와 37.5%가 됩니다. 정배 1.50의 배당 기준 확률은 62.5%이고, 이 구간의 실제 적중이 이보다 높았는지 낮았는지를 표에서 본 것입니다."]),
        ("자주 하는 오해", [
        "'1.2배면 거의 확실하다'는 느낌은 표의 숫자와 다릅니다. 확률이 높은 것과 확실한 것은 다르고, 그 차이는 여러 경기를 묶을 때 크게 드러납니다. 낮은 배당 여러 개를 묶어 2배를 만드는 조합이 생각보다 자주 한 경기에서 끊기는 이유입니다.",
        "또 하나는 '배당이 낮으면 기대치도 높다'는 생각입니다. 기대치는 확률과 배당을 함께 봐야 정해집니다. 실제 적중이 배당 기준 확률보다 높은 구간이 기대치가 좋은 구간입니다."])],
    "underdogs": [("역배가 이기는 경기의 모습", [
        "역배가 이기는 경기에는 몇 가지 공통점이 있습니다. 강팀의 일정이 빡빡하거나, 순위 경쟁에서 동기 차이가 나거나, 주전 결장이 배당에 늦게 반영된 경우입니다. 숫자만으로는 이런 사정이 보이지 않지만, 배당 흐름이 갑자기 움직였다면 그런 소식이 있었을 가능성이 큽니다.",
        "사이트의 역배 조합은 해외 시장이 그 팀을 낮게 보는데도 해외 과거 기록이나 팀 레이팅이 받쳐 주는 경기만 고릅니다. 높은 배당만 보고 고르는 것과 근거가 겹치는 역배를 고르는 것은 적중 간격이 다릅니다."]),
        ("기대치로 보면", [
        "역배의 기대치는 '적중률 × 배당'이 1을 넘는지로 판단합니다. 표에서 실제 적중이 배당 기준 확률보다 높은 구간은 그 곱이 1에 가까워지거나 넘어서는 구간입니다. 반대로 실제가 확률보다 낮은 구간은 배당이 커 보여도 기대치가 낮은 구간입니다.",
        "한두 번의 큰 적중보다 구간 전체의 숫자를 기준으로 삼아야 하는 이유가 여기에 있습니다. 역배는 기억에 남는 한 방 때문에 실제보다 자주 맞는 것처럼 느껴지기 쉽습니다."])],
    "soccer-draws": [("무승부가 늘어나는 상황", [
        "무승부는 두 팀 전력이 비슷할 때, 그리고 한쪽이라도 지지 않는 것이 중요한 경기에서 늘어납니다. 시즌 막판 순위가 굳어진 팀끼리, 혹은 다음 경기를 앞두고 무리하지 않는 팀이 만날 때가 대표적입니다.",
        "또 득점이 적은 리그일수록 무승부가 많습니다. 0대0이나 1대1로 끝날 가능성이 높아지기 때문입니다. 무승부 비율과 골 수는 같은 성향의 다른 얼굴입니다."]),
        ("승무패 대신 쓸 수 있는 선택", [
        "무승부가 걱정되는 경기는 핸디캡의 정수 기준점이나 언더오버로 바꿔 보는 방법이 있습니다. 예를 들어 홈팀이 비기거나 이기면 되는 판단이라면 '패'가 아닌 쪽을 고를 수 있는 핸디캡이 더 맞을 때가 있습니다.",
        "무승부 자체를 노리는 것도 방법입니다. 배당 차이가 작은 경기의 무승부 배당은 대개 3배 이상이고, 표에서 보듯 이런 경기의 무승부는 배당 기준 확률과 비슷하거나 그보다 자주 나옵니다."])],
    "home-advantage": [("홈 이점이 생기는 이유", [
        "홈 이점은 이동 거리, 익숙한 경기장, 관중, 그리고 일정에서 옵니다. 이동 거리가 긴 리그나 경기장 환경이 특이한 리그일수록 홈 이점이 큽니다. 반대로 같은 도시 팀끼리 겨루거나 중립 경기장이 많은 대회에서는 홈 이점이 거의 사라집니다.",
        "국제 대회나 컵 대회는 홈·원정 구분이 형식적인 경우가 있어 이 표에서 따로 봐야 합니다. 리그별 표에서 홈 승률이 유난히 낮은 대회가 있다면 이런 사정일 가능성이 큽니다."]),
        ("원정 정배를 고를 때", [
        "원정팀이 정배로 나온 경기는 전력 차가 홈 이점을 넘어선다는 시장의 판단입니다. 이런 경기에서 원정 정배를 고를 때는, 그 리그의 홈 승률이 배당 기준 확률보다 높은지 먼저 봅니다. 홈이 배당보다 강한 리그라면 원정 정배의 무게를 조금 덜어 두는 편이 안전합니다."])],
    "over-under": [("기준점이 정해지는 방식", [
        "언더오버 기준점은 양쪽에 비슷한 금액이 모이도록 정해집니다. 그래서 기준점은 '예상 점수'라기보다 '양쪽 판단이 갈리는 지점'에 가깝습니다. 리그 평균에서 크게 벗어난 기준점이 나왔다면 그만한 이유(결장, 날씨, 일정)가 있을 가능성이 큽니다.",
        "축구는 2.5 근처, 농구는 두 팀 페이스에 따라 200점대, 야구는 선발 투수에 따라 7~9점 근처에서 기준점이 정해지는 경우가 많습니다."]),
        ("두 근거가 겹칠 때", [
        "리그 전체가 오버로 기운 상황에서 두 팀 최근 경기도 오버가 많았다면 근거가 겹친 경우입니다. 반대로 리그는 오버인데 두 팀은 언더 경기가 많았다면 근거가 엇갈리는 경우이니 그 경기는 다른 마켓으로 보는 편이 낫습니다."])],
    "handicap": [("기준점의 크기와 결과", [
        "기준점이 클수록 강팀이 그 이상으로 이겨야 하므로 변수가 많아집니다. 경기 막판 주전 교체, 큰 점수 차에서의 느슨한 운영, 마지막 순간의 득점 하나가 결과를 바꿉니다. 그래서 큰 기준점에서는 핸디를 받은 쪽이 생각보다 자주 버팁니다.",
        "반대로 작은 기준점은 사실상 승패와 비슷하게 움직입니다. 승패 배당이 너무 낮을 때 작은 기준점의 핸디캡으로 옮기면 배당은 오르고 판단은 크게 달라지지 않습니다."]),
        ("핸디무를 다루는 법", [
        "축구 정수 기준점에서 핸디무는 정확히 그 점수 차로 끝난 경우입니다. 강팀이 정확히 한 골, 두 골 차로 이기는 경기는 생각보다 많습니다. 핸디무가 나올 몫을 계산에 넣지 않으면 승이나 패 한쪽만 골랐을 때 기대보다 자주 빗나갑니다."])],
    "payout-rate": [("환급률이 다른 이유", [
        "마켓마다, 종목마다 환급률이 조금씩 다릅니다. 결과가 셋으로 갈리는 승무패는 둘로 갈리는 승패보다 발매사 몫이 커지기 쉽고, 관심이 큰 리그는 배당이 촘촘하게 매겨지는 편입니다.",
        "같은 판단이라면 환급률이 높은 마켓에서 하는 것이 유리합니다. 예를 들어 축구에서 한쪽 승을 확신한다면 승무패와 핸디캡 배당을 함께 보고, 확률 대비 더 후한 쪽을 고를 수 있습니다."]),
        ("단폴더와 조합", [
        "한 경기만 사는 단폴더는 환급률이 한 번만 적용됩니다. 확신하는 경기가 하나뿐인 날 억지로 조합을 만들기보다 단폴더로 사는 편이 숫자로는 더 합리적입니다. 사이트 전략별 조합에 단폴더 탭이 있는 이유입니다."])],
    "folders": [("묶을 때 지켜볼 것", [
        "같은 리그, 같은 날 경기를 여러 개 묶으면 결과가 서로 엮일 수 있습니다. 날씨나 심판 성향처럼 여러 경기에 같이 작용하는 요인이 있기 때문입니다. 사이트 조합은 같은 리그·같은 날 경기가 겹치면 결합 확률을 조금 깎아서 계산합니다.",
        "회차가 다른 경기는 한 장으로 살 수 없다는 점도 기억해야 합니다. 조합은 같은 회차 안에서만 만들어집니다."]),
        ("배당 목표보다 확률 목표", [
        "조합을 고를 때 '몇 배를 만들까'보다 '이 조합이 맞을 확률이 몇 %인가'를 먼저 보면 선택이 달라집니다. 사이트 조합 카드에 예상 적중률이 크게 적혀 있는 이유입니다. 같은 배당이라도 예상 적중률이 높은 쪽이 기대치가 좋은 조합입니다."])],
    "streaks": [("숫자가 말하는 흐름의 의미", [
        "흐름은 의미가 없다는 뜻이 아닙니다. 연승 중인 팀은 실제로 전력이 좋을 가능성이 높고, 그래서 배당도 낮게 나옵니다. 흐름은 이미 배당에 들어간 정보라는 뜻입니다. 흐름만 보고 고르면 배당이 이미 말한 것을 한 번 더 세는 셈입니다.",
        "의미 있는 흐름은 배당이 따라가지 못한 흐름입니다. 예를 들어 주전이 돌아온 뒤의 연승처럼 이유가 있는 흐름은 배당이 늦게 반영할 수 있습니다."])],
    "odds-movement": [("배당이 움직이는 이유", [
        "배당이 움직이는 이유는 크게 둘입니다. 한쪽에 구매가 몰려서이거나, 부상·결장 같은 새 소식이 나와서입니다. 앞의 것은 사람들의 쏠림이고 뒤의 것은 정보입니다. 결과와 이어지는 것은 대개 뒤의 것입니다.",
        "해외 배당도 함께 움직였다면 정보일 가능성이 높고, 베트맨 배당만 움직였다면 국내 구매 쏠림일 가능성이 높습니다. 사이트가 해외 배당을 분석 기준으로 쓰는 이유 가운데 하나입니다."])],
    "time-of-day": [("시간대와 리그", [
        "새벽 시간대는 유럽 축구와 미국 농구·야구가, 오후는 일본·한국 낮 경기가, 저녁은 국내 프로 경기와 일본 야구가 많습니다. 시간대별 차이는 결국 리그 성격의 차이와 겹칩니다.",
        "그래서 이 표는 '몇 시 경기가 잘 맞는다'보다 '이 시간대에 몰린 리그들의 정배가 배당보다 어땠는가'로 읽는 편이 정확합니다."])],
    "nba-mlb-margins": [("기준점 감각 익히기", [
        "NBA 핸디캡 기준점이 7.5라면 표에서 10점 차 이상 비율을 떠올리면 됩니다. 정배가 이기는 경기 가운데 상당수가 10점 넘게 벌어지지만, 접전으로 끝나는 경기도 적지 않습니다. 기준점이 클수록 경기 막판 운영이 결과를 좌우합니다.",
        "MLB 런라인 -1.5는 정배가 2점 차 이상으로 이겨야 합니다. 1점 차 경기가 많은 야구에서는 정배가 이기고도 런라인에서 빗나가는 경우가 흔합니다."])],
    "bankroll": [("기록을 남기는 습관", [
        "날짜, 고른 경기, 배당, 금액, 결과를 짧게라도 적어 두면 한 달 뒤 내 선택이 어떤 배당 구간에서 잘 맞고 어디서 자주 빗나가는지 보입니다. 기억은 맞힌 경기를 크게, 빗나간 경기를 작게 남기기 때문에 기록이 필요합니다.",
        "사이트의 '내 조합'에 담아 두면 같은 회차 안에서 조합 배당과 예상 적중률을 바로 볼 수 있습니다. 실제 구매는 반드시 베트맨 공식 사이트와 판매점에서만 합니다."])],
    "compare-goals": [("숫자를 고를 때 주의할 점", [
        "리그 평균은 여러 시즌을 합친 값이라 이번 시즌 흐름과 다를 수 있습니다. 감독 교체나 승격·강등으로 팀 구성이 바뀌면 리그 성향도 조금씩 움직입니다. 리그 평균에 이번 시즌 두 팀 기록을 더해 보는 것이 순서입니다."])],
    "compare-draws": [("무승부가 많은 리그에서 고르는 법", [
        "무승부가 잦은 리그에서는 한쪽 승보다 '지지 않는 쪽'을 고르는 접근이 자연스럽습니다. 핸디캡에서 플러스 기준점을 받은 쪽이 그런 선택입니다. 홈 승률이 높은 리그라면 홈팀의 패하지 않는 쪽이 근거가 겹칩니다."])],
    "compare-favorites": [("리그를 고르는 것도 전략입니다", [
        "같은 날 여러 리그 경기가 발매되면 조합의 기둥을 어느 리그에서 고를지 정해야 합니다. 정배가 배당보다 꾸준히 잘 버틴 리그의 경기를 기둥으로 삼고, 이변이 잦은 리그의 경기는 따로 떼어 보는 것만으로 조합의 흔들림이 줄어듭니다.",
        "이 표의 숫자도 새 시즌 기록이 쌓이면 자동으로 다시 계산됩니다. 순위가 한두 칸 바뀌는 것보다 위아래 끝에 있는 리그가 계속 그 자리를 지키는지가 의미 있는 신호입니다."])],
}

EXTRA2 = {
    "handicap": [("실제 예시로 보는 핸디캡", [
        "농구에서 홈팀 기준점이 -6.5라면 홈팀이 7점 이상 이겨야 핸디승입니다. 6점 차로 이기면 승패에서는 맞고 핸디캡에서는 빗나갑니다. 야구 -1.5는 2점 이상, 축구 -1은 두 골 이상 차이로 이겨야 승이고 정확히 한 골 차면 핸디무입니다.",
        "그래서 핸디캡을 고를 때는 '이긴다'와 '몇 점 차로 이긴다'를 나눠서 생각합니다. 강팀이 이길 확률이 70%여도 기준점 이상으로 이길 확률은 그보다 훨씬 낮습니다. 사이트 분석 확률은 이 차이를 반영해 마켓별로 따로 계산합니다."]),
        ("기준점이 홈 기준이라는 점", [
        "베트맨 핸디캡 기준점은 항상 홈팀 쪽에 붙습니다. 원정팀이 강할 때는 홈팀이 플러스 기준점을 받습니다. 화면에서 '핸디승'과 '핸디패'가 어느 팀 기준인지 헷갈리기 쉬우니, 기준점의 부호와 홈팀을 같이 확인하는 습관이 필요합니다."])],
    "payout-rate": [("후한 배당을 찾는 순서", [
        "먼저 해외 배당으로 계산한 확률을 봅니다. 그다음 베트맨 배당에 그 확률을 곱해 봅니다. 곱이 1을 넘으면 그 선택은 베트맨 배당이 상대적으로 후한 선택입니다. 사이트의 분석 확률과 화면의 베트맨 배당을 나란히 보여 주는 것이 이 계산을 쉽게 하기 위해서입니다.",
        "예를 들어 분석 확률 62%에 베트맨 배당 1.70이면 곱은 1.05로 1을 넘습니다. 같은 확률에 배당 1.55면 곱은 0.96입니다. 같은 경기, 같은 선택이라도 배당에 따라 판단이 달라지는 이유입니다."])],
    "folders": [("가장 자신 없는 한 경기", [
        "조합을 짠 뒤 각 경기의 분석 확률을 나란히 적어 보면, 대개 하나가 눈에 띄게 낮습니다. 그 한 경기를 빼면 배당은 줄지만 예상 적중률은 크게 올라갑니다. 사이트 조합 카드의 예상 적중률을 비교하면 이 차이를 바로 볼 수 있습니다.",
        "반대로 배당을 키우려고 한 경기를 더 넣을 때는 그 경기의 확률을 곱해 보는 습관을 들입니다. 60% 경기를 하나 더 넣으면 전체 적중률은 정확히 60%를 곱한 만큼 줄어듭니다."])],
    "streaks": [("숫자로 확인하는 습관", [
        "'요즘 이 팀이 잘 나간다'는 말을 들으면 그 팀의 최근 경기 배당과 결과를 같이 봅니다. 배당이 계속 낮았는데 이겼다면 원래 강한 팀이 이긴 것이고, 배당이 높았는데 이겼다면 시장보다 잘한 것입니다. 뒤쪽이 의미 있는 흐름입니다.",
        "사이트 팀 페이지에는 정배일 때와 역배일 때의 승률이 따로 나옵니다. 역배일 때도 자주 이긴 팀은 시장이 과소평가하는 팀일 가능성이 있습니다."])],
    "odds-movement": [("발매 직후와 마감 직전", [
        "배당은 발매 직후보다 마감 직전에 더 많은 정보를 담습니다. 선발 명단, 날씨, 마지막 부상 소식이 반영되기 때문입니다. 시간이 있다면 마감에 가까운 시각에 배당을 다시 확인하는 것만으로도 놓친 정보를 잡을 수 있습니다.",
        "사이트는 하루 여러 번 배당을 다시 수집하고, 바뀐 배당으로 확률과 조합을 다시 계산합니다. 첫 화면의 숫자가 아침과 저녁에 다를 수 있는 이유입니다."])],
    "time-of-day": [("새벽 경기와 아침 결과", [
        "새벽 경기를 조합에 넣으면 결과를 아침에 한꺼번에 확인하게 됩니다. 이때 한 경기가 먼저 끝나 결과를 알게 되면 나머지 경기에 대한 판단이 흔들리기 쉽습니다. 조합은 사기 전에 한 번에 판단하고, 산 뒤에는 결과를 차분히 확인하는 편이 좋습니다.",
        "구매 마감 시각도 생각해야 합니다. 프로토 구매는 정해진 시간에만 가능하므로, 다음 날 새벽 경기는 전날 마감 전에 미리 판단해 두어야 합니다. 사이트가 오후 7시에 다음 구매일 분석을 올리는 이유입니다."])],
    "nba-mlb-margins": [("한국 리그와 비교할 때", [
        "KBL과 KBO도 같은 원리로 읽습니다. 리그별 글에 베트맨 발매 경기 기준 접전 비율이 나와 있습니다. 미국 리그보다 접전 비율이 높다면 같은 기준점이라도 핸디를 받은 쪽이 더 자주 버틴다고 볼 수 있습니다.",
        "점수 차 분포는 시즌이 바뀌어도 크게 변하지 않는 편이라, 오래 쌓인 기록으로 감을 잡아 두면 매 시즌 쓸 수 있는 기준이 됩니다."])],
    "bankroll": [("예산을 나누는 방법", [
        "한 달 예산을 먼저 정하고, 회차마다 쓸 금액을 그 안에서 나눕니다. 한 회차 금액은 한 달 예산의 작은 일부로 고정합니다. 이렇게 하면 한 회차 결과가 다음 회차의 판단을 흔들지 않습니다.",
        "예산을 다 쓴 달은 거기서 멈춥니다. 다음 달 예산을 당겨 쓰지 않는 것이 가장 단순하면서 가장 지키기 어려운 규칙입니다."])],
    "compare-favorites": [("정배가 흔들리는 리그의 공통점", [
        "정배가 배당보다 덜 버티는 리그는 대체로 전력이 고르고, 홈 이점이 크거나 무승부가 많습니다. 강팀이 원정에서 비기는 경기가 쌓이면 정배 적중이 내려갑니다. 그런 리그에서는 승무패 정배보다 핸디캡 플러스 쪽이나 언더가 대안이 됩니다."])],
}

EXTRA3 = {
    "streaks": [("내 선택에도 같은 원리가", [
        "연패 뒤 반등을 기대하는 마음은 팀을 볼 때만이 아니라 내 기록을 볼 때도 생깁니다. 세 번 연속 빗나간 뒤 네 번째는 맞을 것 같은 느낌이 들지만, 네 번째 선택의 확률은 앞의 결과와 상관없이 그 경기 자체로 정해집니다.",
        "그래서 연속으로 빗나간 날일수록 평소와 같은 기준으로, 평소와 같은 금액으로 고르는 것이 기록을 지키는 방법입니다. 사이트가 매일 같은 방식으로 분석하고 결과를 지우지 않는 것도 같은 이유입니다."])],
    "odds-movement": [("배당 흐름 차트 읽기", [
        "경기 페이지의 배당 흐름 차트는 처음 배당 대비 몇 % 바뀌었는지를 시각별로 보여 줍니다. 한쪽 선이 계속 내려가고 반대쪽이 올라가면 그쪽으로 구매가 꾸준히 몰린 것입니다. 마감 직전에 갑자기 꺾였다면 막판 소식이 있었을 가능성이 큽니다.",
        "흐름이 내 판단과 반대로 움직였다면 판단을 바꾸라는 뜻이 아니라, 내가 놓친 정보가 있는지 확인하라는 신호로 받아들이는 편이 좋습니다."])],
    "nba-mlb-margins": [("합계 점수에서 보는 것", [
        "NBA 합계 기준점은 두 팀의 공격 속도와 수비 효율로 정해집니다. 연전 두 번째 경기나 원정 연속 일정에서는 체력 때문에 득점이 줄어드는 경향이 있습니다. MLB는 선발 투수와 구장 크기, 바람이 합계에 큰 영향을 줍니다.",
        "합계 점수는 승패를 맞히지 않아도 된다는 장점이 있습니다. 두 팀 중 어느 쪽이 이길지 판단이 서지 않는 경기에서 경기 흐름만 판단하면 되기 때문입니다."])],
    "bankroll": [("숫자로 보는 금액 관리", [
        "같은 적중률이라도 금액을 고정한 사람과 결과에 따라 금액을 바꾼 사람의 기록은 크게 다릅니다. 연속으로 빗나간 뒤 금액을 두 배로 늘리는 방식은 몇 번만 이어져도 처음 금액의 수십 배가 됩니다. 위에서 본 가장 긴 연속 빗나감 길이를 떠올리면 이 방식이 왜 위험한지 바로 보입니다.",
        "금액 계산기는 예산, 확률, 배당을 넣으면 켈리 기준 금액을 보여 줍니다. 계산 결과가 0원이면 그 선택은 확률에 비해 배당이 낮다는 뜻이니 건너뛰는 것이 맞습니다."])],
}


# ───────────────────────── 주제별 짧은 글(종목·리그마다) ─────────────────────────
def _pick(key, *variants):
    """같은 뜻의 여러 문장 중 하나를 글마다 다르게(같은 글은 항상 같은 문장)."""
    h = sum(ord(c) * (i + 1) for i, c in enumerate(key))
    return variants[h % len(variants)]


def _slug(x):
    return re.sub(r"[^0-9a-z가-힣]+", "-", str(x).lower()).strip("-")


def t_fav(key, name, gs, cat, sport, league=None):
    bands = fav_by_band(gs, min_n=20)
    if len(bands) < 2:
        return None
    n = sum(b["n"] for b in bands)
    hit = sum(b["hit"] * b["n"] for b in bands) / n
    exp = sum(b["exp"] * b["n"] for b in bands) / n
    top = max(bands, key=lambda b: b["hit"] - b["exp"])
    low = bands[0]
    gap = hit - exp
    v = (_pick(key, "배당이 말한 것보다 정배가 더 단단했습니다.", "정배가 배당 이상으로 버틴 편입니다.", "정배를 믿어도 배당보다 더 맞아 준 기록입니다.") if gap > 0.015 else
         _pick(key, "정배가 배당만큼 이기지 못했습니다.", "배당이 말한 것보다 정배가 자주 미끄러졌습니다.", "정배를 그대로 믿기엔 아쉬운 기록입니다.") if gap < -0.015 else
         _pick(key, "배당과 실제가 거의 같습니다.", "배당이 결과를 정직하게 짚은 편입니다.", "정배가 딱 배당만큼 이겼습니다."))
    return A(f"fav-{_slug(key)}", f"{name} 정배, 배당만큼 이길까", cat,
             f"{name} 정배 {n:,}경기를 배당 구간별로 나눠 실제로 이긴 비율을 셌습니다.",
             [(None, [
                 f"{name}에서 배당이 낮은 쪽은 {pct(hit)} 이겼고 배당 기준 확률은 {pct(exp)}였습니다({pp(gap)}). {v}",
                 ("table", ["정배 배당", "경기 수", "실제 적중", "배당 기준", "차이"], [[b["band"], f"{b['n']:,}", pct(b["hit"]), pct(b["exp"]), pp(b["hit"] - b["exp"])] for b in bands]),
                 f"가장 낮은 배당대({low['band']})는 {pct(low['hit'])}, 배당보다 가장 잘 버틴 구간은 {top['band']}({pp(top['hit'] - top['exp'])})입니다. "
                 + _pick(key + "b", "조합의 기둥은 이 구간에서 고르는 편이 무난합니다.", "여러 경기를 묶을 때 이 구간 숫자를 기준으로 삼으면 됩니다.", "정배를 고를 때 먼저 이 구간을 찾아보면 좋습니다."),
             ])], league=league, sport=sport, tags=[name, "정배"])


def t_home(key, name, gs, cat, sport, league=None):
    if len(gs) < 100:
        return None
    n = len(gs)
    hw = sum(1 for g in gs if g["res"] == 0) / n
    dr = sum(1 for g in gs if g["res"] == 1) / n
    he = sum(fair(g["o"])[0] for g in gs) / n
    favs = [(g, _fav(g)) for g in gs if _fav(g)]
    hf = [g for g, f in favs if f[0] == 0]
    af = [g for g, f in favs if f[0] == 2]
    hfr = sum(1 for g in hf if g["res"] == 0) / len(hf) if len(hf) >= 30 else None
    afr = sum(1 for g in af if g["res"] == 2) / len(af) if len(af) >= 30 else None
    gap = hw - he
    rows = [["홈 승", pct(hw)]] + ([["무승부", pct(dr)]] if dr > 0.001 else []) + [["원정 승", pct(1 - hw - dr)], ["배당 기준 홈 확률", pct(he)]]
    if hfr is not None and afr is not None:
        rows += [["홈팀이 정배일 때", f"{pct(hfr)} ({len(hf):,})"], ["원정팀이 정배일 때", f"{pct(afr)} ({len(af):,})"]]
    return A(f"home-{_slug(key)}", f"{name} 홈 이점은 얼마나 될까", cat,
             f"{name} {n:,}경기의 홈·원정 결과를 배당 기준 확률과 비교했습니다.",
             [(None, [
                 f"{name} 홈팀은 {pct(hw)} 이겼습니다. 배당 기준 홈 확률 {pct(he)}보다 {pp(gap)} " + ("더 이겼습니다." if gap > 0 else "덜 이겼습니다." if gap < 0 else "같습니다.")
                 + " " + (_pick(key, "홈 경기의 무게를 배당보다 조금 더 실어도 되는 리그입니다.", "홈팀 쪽 선택이 배당 이상으로 맞아 준 기록입니다.") if gap > 0.02 else
                          _pick(key, "원정팀이 생각보다 잘 버티는 리그입니다.", "홈이라는 이유만으로 무게를 싣기엔 근거가 약합니다.") if gap < -0.02 else
                          _pick(key, "홈 이점은 배당에 거의 그대로 들어가 있습니다.", "홈·원정 자체보다 그날 전력 차를 보는 편이 맞습니다.")),
                 ("table", ["항목", "값"], rows),
                 (f"홈 정배와 원정 정배의 차이는 {pp(hfr - afr)}입니다. " + ("원정 정배는 한 번 더 확인하고 고르는 편이 좋습니다." if hfr - afr > 0.05 else "원정 정배가 오히려 잘 버텼습니다." if afr - hfr > 0.05 else "정배라면 홈·원정을 크게 가리지 않아도 됩니다.")) if hfr is not None and afr is not None else "",
             ])], league=league, sport=sport, tags=[name, "홈"])


def t_ou(key, name, lst, cat, sport, league=None):
    if len(lst) < 60:
        return None
    n = len(lst)
    ov = sum(1 for x in lst if x["res"] == (2 if x["uf"] else 0)) / n
    by = defaultdict(lambda: [0, 0])
    for x in lst:
        a = by[x["line"]]
        a[0] += 1
        a[1] += int(x["res"] == (2 if x["uf"] else 0))
    rows = [[f"{k:g}", f"{v[0]:,}", pct(v[1] / v[0])] for k, v in sorted(by.items(), key=lambda kv: -kv[1][0])[:8] if v[0] >= 10]
    rows.sort(key=lambda r: float(r[0]))
    lean = ("오버" if ov > 0.53 else "언더" if ov < 0.47 else None)
    return A(f"ou-{_slug(key)}", f"{name} 언더오버, 어느 쪽으로 기울까", cat,
             f"{name} 언더오버 {n:,}경기에서 오버와 언더가 어떻게 나뉘었는지 기준점별로 정리했습니다.",
             [(None, [
                 f"{name} 언더오버는 오버 {pct(ov)}, 언더 {pct(1 - ov)}로 끝났습니다. "
                 + (_pick(key, f"{lean} 쪽으로 기운 기록입니다.", f"기준점보다 {lean}로 끝난 경기가 더 많았습니다.", f"꾸준히 {lean} 쪽이 우세했습니다.") if lean else
                    _pick(key, "어느 한쪽으로 기울지 않았습니다.", "거의 반반으로 갈렸습니다.", "기준점이 양쪽을 잘 맞춘 편입니다.")),
                 ("table", ["기준점", "경기 수", "오버"], rows) if len(rows) >= 2 else "",
                 _pick(key + "u", "기준점별로 보면 같은 리그 안에서도 오버가 잘 나오는 숫자와 언더가 잘 나오는 숫자가 갈립니다.",
                       "자주 나오는 기준점일수록 표본이 많아 숫자를 믿을 만합니다.",
                       "그날 기준점이 표의 어디에 해당하는지 찾아보면 출발점이 잡힙니다."),
             ])], league=league, sport=sport, tags=[name, "언더오버"])


def t_hc(key, name, lst, cat, sport, league=None):
    lst = [x for x in lst if x["line"]]
    if len(lst) < 60:
        return None
    n = len(lst)
    plus = sum(1 for x in lst if x["res"] == (0 if x["line"] > 0 else 2)) / n
    draw = sum(1 for x in lst if x["res"] == 1) / n
    by = defaultdict(lambda: [0, 0])
    for x in lst:
        k = abs(x["line"])
        a = by[k]
        a[0] += 1
        a[1] += int(x["res"] == (0 if x["line"] > 0 else 2))
    rows = [[f"{k:g}", f"{v[0]:,}", pct(v[1] / v[0])] for k, v in sorted(by.items()) if v[0] >= 10][:10]
    return A(f"hc-{_slug(key)}", f"{name} 핸디캡, 받은 쪽은 얼마나 버틸까", cat,
             f"{name} 핸디캡 {n:,}경기에서 기준점을 받은 쪽(약팀)이 얼마나 버텼는지 기준점 크기별로 셌습니다.",
             [(None, [
                 f"기준점을 받은 쪽은 {pct(plus)} 버텼습니다" + (f"(핸디무 {pct(draw)})" if draw > 0.01 else "") + ". "
                 + (_pick(key, "강팀이 기준점만큼 벌리지 못한 경기가 많았습니다.", "받은 쪽이 꾸준히 버틴 기록입니다.") if plus > 0.52 else
                    _pick(key, "강팀이 기준점 이상으로 벌린 경기가 많았습니다.", "주는 쪽이 꾸준히 넘어선 기록입니다.") if plus < 0.48 else
                    _pick(key, "기준점이 점수 차를 잘 맞힌 편입니다.", "받는 쪽과 주는 쪽이 거의 반반입니다.")),
                 ("table", ["기준점 크기", "경기 수", "받은 쪽 적중"], rows) if len(rows) >= 2 else "",
                 _pick(key + "h", "기준점이 커질수록 받은 쪽 숫자가 어떻게 바뀌는지 보면, 이 리그에서 강팀이 몇 점 차까지 벌리는지 감이 옵니다.",
                       "작은 기준점은 승패와 비슷하게, 큰 기준점은 경기 막판 운영에 따라 갈립니다.",
                       "같은 기준점이라도 리그에 따라 숫자가 다르니 이 표를 그 리그의 기준으로 삼으면 됩니다."),
             ])], league=league, sport=sport, tags=[name, "핸디캡"])


def t_upset(key, name, gs, cat, sport, league=None):
    favs = [(g, _fav(g)) for g in gs if _fav(g)]
    if len(favs) < 100:
        return None
    acc = defaultdict(lambda: [0, 0])
    for g, f in favs:
        b = _band(f[2], DOG_EDGES)
        if b:
            acc[b][0] += 1
            acc[b][1] += int(g["res"] == 2 - f[0])
    rows = [[b, f"{v[0]:,}", pct(v[1] / v[0]), f"{max(1, round(v[0] / max(1, v[1])))}경기에 한 번"] for lo, hi in DOG_EDGES for b in [_band(lo, [(lo, hi)])] for v in [acc.get(b)] if v and v[0] >= 15]
    if len(rows) < 2:
        return None
    up = sum(1 for g, f in favs if g["res"] == 2 - f[0]) / len(favs)
    return A(f"upset-{_slug(key)}", f"{name} 역배는 몇 경기에 한 번 터질까", cat,
             f"{name}에서 배당이 높은 쪽이 이긴 경기를 배당 구간별로 셌습니다.",
             [(None, [
                 f"{name} 역배는 {len(favs):,}경기 중 {pct(up)} 이겼습니다. " + _pick(key, "구간별로 보면 기다리는 간격이 보입니다.", "배당이 높아질수록 간격이 어떻게 벌어지는지 표로 정리했습니다.", "아래 표의 간격을 알고 있으면 역배를 고를 때 기대치를 정하기 쉽습니다."),
                 ("table", ["역배 배당", "경기 수", "역배 적중", "대략"], rows),
             ])], league=league, sport=sport, tags=[name, "역배"])


def f_topic_articles(code, rows):
    """유럽 리그 하나를 주제별 짧은 글로."""
    name = FD_NAME.get(code, code)
    n = len(rows)
    if n < 600:
        return []
    out = []
    key = code
    # 골 분포
    gd = Counter(min(r[6], 6) for r in rows)
    avg = sum(r[6] for r in rows) / n
    out.append(A(f"goals-{code.lower()}", f"{name} 한 경기에 골은 몇 개 나올까", "유럽 축구",
                 f"{name} {n:,}경기의 골 수 분포와 기준점별 오버 비율입니다.",
                 [(None, [f"{name} 경기당 평균은 {avg:.2f}골입니다. 가장 흔한 결과는 {max(gd, key=gd.get)}골({pct(max(gd.values()) / n)})입니다.",
                          ("table", ["총 골", "비율"], [[("6골 이상" if k == 6 else f"{k}골"), pct(v / n)] for k, v in sorted(gd.items())]),
                          ("table", ["기준점", "오버"], [[f"{x - 0.5:g}", pct(sum(1 for r in rows if r[6] >= x) / n)] for x in (1, 2, 3, 4)]),
                          _pick(key, "2.5가 애매한 경기는 한 칸 위아래 기준점의 비율을 같이 보면 됩니다.", "기준점 1.5와 3.5의 비율 차이가 이 리그 득점의 폭을 보여 줍니다.")])],
                 league=name, sport="soccer", tags=[name, "골"]))
    # 무승부
    gaps = defaultdict(lambda: [0, 0])
    for r in rows:
        if r[0] and r[2]:
            g = abs(r[0] - r[2])
            k = "0.5 미만" if g < 0.5 else "0.5~1.5" if g < 1.5 else "1.5~3" if g < 3 else "3 이상"
            gaps[k][0] += 1
            gaps[k][1] += int(r[3] == 1)
    dr = sum(1 for r in rows if r[3] == 1) / n
    out.append(A(f"draws-{code.lower()}", f"{name} 무승부는 언제 나올까", "유럽 축구",
                 f"{name} {n:,}경기의 무승부를 두 팀 배당 차이별로 나눠 봤습니다.",
                 [(None, [f"{name} 무승부는 {pct(dr)}, 대략 {round(1 / max(dr, 0.01))}경기에 한 번입니다. " + _pick(key, "두 팀 배당이 붙을수록 무승부가 늘어납니다.", "배당 차이가 작은 경기에서 무승부 몫이 커집니다."),
                          ("table", ["홈·원정 배당 차이", "경기 수", "무승부"], [[k, f"{gaps[k][0]:,}", pct(gaps[k][1] / gaps[k][0])] for k in ("0.5 미만", "0.5~1.5", "1.5~3", "3 이상") if gaps[k][0] >= 30]),
                          _pick(key + "d", "배당 차이 0.5 미만 경기의 무승부 비율과 무승부 배당을 곱해 보면 무승부 선택의 기대치를 가늠할 수 있습니다.", "승무패에서 이런 경기를 한쪽 승으로 묶기 전에 무승부 몫을 먼저 떠올리면 좋습니다.")])],
                 league=name, sport="soccer", tags=[name, "무승부"]))
    # 정배
    edges = [(1.0, 1.4), (1.4, 1.8), (1.8, 2.3), (2.3, 99)]
    acc = defaultdict(lambda: [0, 0, 0.0, 0])
    for r in rows:
        if not r[0] or not r[2] or r[0] == r[2]:
            continue
        side = 0 if r[0] < r[2] else 2
        b = _band(min(r[0], r[2]), edges)
        a = acc[b]
        a[0] += 1; a[1] += int(r[3] == side); a[2] += fair(r[:3])[side]; a[3] += int(r[3] == 1)
    brow = [[b, f"{v[0]:,}", pct(v[1] / v[0]), pct(v[2] / v[0]), pct(v[3] / v[0])] for lo, hi in edges for b in [_band(lo, [(lo, hi)])] for v in [acc.get(b)] if v and v[0] >= 40]
    if len(brow) >= 2:
        tot = sum(v[0] for v in acc.values())
        h = sum(v[1] for v in acc.values()) / tot
        e = sum(v[2] for v in acc.values()) / tot
        out.append(A(f"fav-fd-{code.lower()}", f"{name} 정배는 배당보다 잘 버틸까", "유럽 축구",
                     f"{name} 정배를 배당 구간별로 나눠 실제 적중, 배당 기준 확률, 무승부 비율을 같이 봤습니다.",
                     [(None, [f"{name} 정배 전체 적중은 {pct(h)}, 배당 기준 확률은 {pct(e)}입니다({pp(h - e)}). "
                              + ("배당보다 단단한 리그입니다." if h > e + 0.015 else "배당보다 덜 버티는 리그입니다." if h < e - 0.015 else "배당과 거의 같습니다."),
                              ("table", ["정배 배당", "경기 수", "실제 적중", "배당 기준", "무승부"], brow),
                              _pick(key + "f", "정배가 이기지 못할 때 무승부가 차지하는 몫을 보면, '지지 않는 쪽' 선택이 얼마나 단단한지 알 수 있습니다.", "같은 배당대라도 무승부 비율이 높으면 승무패보다 핸디캡 플러스 쪽이 편할 때가 있습니다.")])],
                     league=name, sport="soccer", tags=[name, "정배"]))
    # 오버 2.5 시장 대비
    pairs = [(fair([r[4], r[5]])[0], int(r[6] >= 3)) for r in rows if r[4] and r[5]]
    if len(pairs) >= 300:
        edges2 = [(0, 0.45), (0.45, 0.55), (0.55, 0.65), (0.65, 1.01)]
        rr = []
        for lo, hi in edges2:
            xs = [y for x, y in pairs if lo <= x < hi]
            ex = [x for x, y in pairs if lo <= x < hi]
            if len(xs) >= 40:
                rr.append([f"{lo * 100:.0f}~{min(hi, 1) * 100:.0f}%", f"{len(xs):,}", pct(sum(xs) / len(xs)), pct(sum(ex) / len(ex))])
        if len(rr) >= 2:
            out.append(A(f"o25-{code.lower()}", f"{name} 오버 2.5, 배당이 맞았을까", "유럽 축구",
                         f"{name} 오버 2.5 배당이 말한 확률과 실제 3골 이상 비율을 구간별로 비교했습니다.",
                         [(None, [_pick(key + "o", "시장이 오버를 높게 본 경기일수록 실제로 골이 많이 나왔는지, 그 정도가 배당과 맞았는지 봅니다.", "오버 배당이 낮은 경기와 높은 경기에서 실제 결과를 나눠 봤습니다."),
                                  ("table", ["오버 배당 기준 확률", "경기 수", "실제 오버", "배당 기준"], rr),
                                  "실제가 배당 기준보다 높은 구간은 시장이 골을 적게 본 구간이고, 낮은 구간은 많이 본 구간입니다. 그 경기의 오버 배당이 어느 구간인지 찾아보면 됩니다."])],
                         league=name, sport="soccer", tags=[name, "언더오버"]))
    return out


def scoped_articles(games, ou, hc):
    out = []
    for sp, ko in SPORT_KO.items():
        gs = [g for g in games if g["sport"] == sp]
        out += [t_fav(f"s-{sp}", ko, gs, "종목별", sp), t_home(f"s-{sp}", ko, gs, "종목별", sp),
                t_ou(f"s-{sp}", ko, [x for x in ou if x["sport"] == sp], "종목별", sp),
                t_hc(f"s-{sp}", ko, [x for x in hc if x["sport"] == sp], "종목별", sp), t_upset(f"s-{sp}", ko, gs, "종목별", sp)]
    names = Counter((g["lk"], g["league"], g["sport"]) for g in games)
    disp = {}
    for (lk, nm, sp), c in names.most_common():
        disp.setdefault(lk, (nm, sp))
    for lk, (nm, sp) in disp.items():
        gs = [g for g in games if g["lk"] == lk]
        if len(gs) < 80:
            continue
        out += [t_fav(lk, nm, gs, "리그별", sp, nm), t_home(lk, nm, gs, "리그별", sp, nm),
                t_ou(lk, nm, [x for x in ou if x["lk"] == lk], "리그별", sp, nm),
                t_hc(lk, nm, [x for x in hc if x["lk"] == lk], "리그별", sp, nm), t_upset(lk, nm, gs, "리그별", sp, nm)]
    return out

# ───────────────────────── 전체 ─────────────────────────
def _load_fd():
    out = defaultdict(list)
    d = config.DATA / "history" / "overseas"
    if d.exists():
        for f in sorted(d.glob("*.json")):
            code = f.stem.split("_", 1)[-1]
            try:
                out[code] += json.loads(f.read_text())
            except Exception:  # noqa: BLE001
                continue
    return out


def _sport_avgs(games, ou):
    """종목별 리그 지표 분포(리그별 글에서 같은 종목 안의 위치를 말할 때 쓴다)."""
    by = defaultdict(dict)
    lg = defaultdict(list)
    for g in games:
        lg[(g["sport"], g["lk"], g["league"])].append(g)
    for (sp, lk, nm), gs in lg.items():
        if len(gs) < 150:
            continue
        fv = [(g, _fav(g)) for g in gs if _fav(g)]
        lou = [x for x in ou if x["lk"] == lk]
        by[sp][lk] = {"name": nm, "home": sum(1 for g in gs if g["res"] == 0) / len(gs),
                      "fav": sum(1 for g, f in fv if g["res"] == f[0]) / len(fv),
                      "upset": sum(1 for g, f in fv if g["res"] == 2 - f[0]) / len(fv),
                      "over": (sum(1 for x in lou if x["res"] == (2 if x["uf"] else 0)) / len(lou)) if len(lou) >= 60 else None}
    return by


def _rank_txt(val, vals, hi_word, lo_word):
    vals = sorted(vals, reverse=True)
    r = vals.index(val) + 1
    n = len(vals)
    if r == 1:
        return f"가장 {hi_word}"
    if r == n:
        return f"가장 {lo_word}"
    return f"{r}번째로 {hi_word}" if r <= (n + 1) // 2 else f"{n - r + 1}번째로 {lo_word}"


def _league_compare(a, by):
    """리그별 글에 같은 종목 다른 리그들과의 비교 문단을 넣는다(리그마다 결과가 달라 문장이 달라진다)."""
    sp = a.sport
    lk = None
    for k, v in by.get(sp, {}).items():
        if v["name"] == a.league:
            lk = k
    if not lk or len(by[sp]) < 3:
        a.sections.insert(-1, ("다른 리그와 비교", [
            f"베트맨에 발매되는 {SPORT_KO.get(sp, sp)} 리그 가운데 비교할 만큼 기록이 쌓인 곳이 아직 적어, 이 리그의 숫자는 리그 자체의 기록으로만 읽습니다. 다른 리그 기록이 쌓이면 이 자리에 비교가 자동으로 들어갑니다.",
            "비교 대상이 적을 때는 정배 적중과 배당 기준 확률의 차이, 홈 승률과 배당 기준 홈 확률의 차이를 기준으로 삼는 편이 정확합니다. 두 차이가 같은 쪽으로 2%p 넘게 벌어져 있다면 그 리그만의 성향일 가능성이 있습니다."]))
        return
    me = by[sp][lk]
    vals = by[sp].values()
    ps = [_rank_txt(me["home"], [v["home"] for v in vals], "홈팀이 강한 리그", "홈팀이 약한 리그"),
          _rank_txt(me["fav"], [v["fav"] for v in vals], "정배가 잘 맞는 리그", "정배가 덜 맞는 리그"),
          _rank_txt(me["upset"], [v["upset"] for v in vals], "이변이 잦은 리그", "이변이 드문 리그")]
    if me["over"] is not None:
        ov = [v["over"] for v in vals if v["over"] is not None]
        if len(ov) >= 3:
            ps.append(_rank_txt(me["over"], ov, "오버가 잦은 리그", "언더가 잦은 리그"))
    avg_fav = sum(v["fav"] for v in vals) / len(by[sp])
    avg_home = sum(v["home"] for v in vals) / len(by[sp])
    others = sorted((v for k, v in by[sp].items() if k != lk), key=lambda v: abs(v["fav"] - me["fav"]))
    twin = others[0]["name"] if others else None
    a.sections.insert(-1, ("같은 종목 다른 리그와 비교", [
        f"베트맨 {SPORT_KO.get(sp, sp)} 리그 가운데 기록이 충분한 {len(by[sp])}개 리그와 나란히 놓으면, {a.league}{josa(a.league)} " + ps[0] + "이고 " + ", ".join(ps[1:]) + "입니다.",
        f"{SPORT_KO.get(sp, sp)} 리그 평균 정배 적중은 {pct(avg_fav)}, 평균 홈 승률은 {pct(avg_home)}입니다. {a.league}{josa(a.league)} 정배 적중이 평균보다 {pp(me['fav'] - avg_fav)}, 홈 승률이 {pp(me['home'] - avg_home)} 차이 납니다."
        + (f" 정배 적중이 가장 비슷한 리그는 {twin}{josa(twin, '이라', '라')}, 두 리그 경기를 같은 조합에 넣을 때는 성향이 겹친다고 봐도 됩니다." if twin else ""),
        ("정배 적중이 평균보다 높은 리그는 조합의 기둥 경기를 고르기 좋은 곳입니다. " if me["fav"] > avg_fav + 0.02 else
         "정배 적중이 평균보다 낮은 리그는 정배를 조합의 기둥으로 쓰기보다 한 칸 정도로만 두는 편이 무리가 없습니다. " if me["fav"] < avg_fav - 0.02 else
         "정배 적중이 평균과 비슷해 리그 성향보다 그날 경기의 사정을 더 보는 편이 맞습니다. ")
        + ("이변이 잦은 편이라 역배 조합의 후보가 자주 나오는 리그이기도 합니다." if me["upset"] > sorted(v["upset"] for v in vals)[len(by[sp]) // 2] else
           "이변이 드문 편이라 역배를 고를 때는 근거가 겹치는 경기만 추리는 편이 좋습니다."),
    ]))


def build_all() -> list[dict]:
    from ..sources import betman_history, us_history
    rows = betman_history.load_all()
    games = _games(rows)
    ou, hc = _lines(rows, "OU"), _lines(rows, "HANDICAP")
    us = {lg: us_history.load(lg) for lg in us_history.LEAGUES}
    fd = _load_fd()
    arts: list[A | None] = [
        art_favorites(games), art_upsets(games), art_draws(games), art_home(games), art_overunder(rows),
        art_handicap(rows), art_payout(games), art_folders(games), art_streaks(games), art_movement(games),
        art_timeofday(games), art_us_margins(us), art_bankroll(games),
    ]
    arts += art_compare(fd)
    names = Counter()
    sport_of = {}
    for g in games:
        names[(g["lk"], g["league"])] += 1
        sport_of[g["lk"]] = g["sport"]
    disp = {}
    for (lk, nm), c in names.most_common():
        disp.setdefault(lk, nm)
    for lk, nm in disp.items():
        arts.append(art_league(lk, nm, sport_of[lk], games, ou, hc))
    allst = _fd_stats(fd)
    for code, rws in fd.items():
        arts.append(art_fd_league(code, rws, allst))
        arts += f_topic_articles(code, rws)
    arts += scoped_articles(games, ou, hc)
    sport_avg = _sport_avgs(games, ou)
    out, seen = [], set()
    for a in arts:
        if not a:
            continue
        more = EXTRA.get(a.slug, []) + EXTRA2.get(a.slug, []) + EXTRA3.get(a.slug, [])
        if more:
            a.sections = a.sections[:-1] + more + a.sections[-1:]
        if a.cat == "리그별" and a.slug.startswith("league-"):
            _league_compare(a, sport_avg)
        d = a.to_dict()
        if d["chars"] < MIN_CHARS or d["slug"] in seen:
            continue
        seen.add(d["slug"])
        out.append(d)
    # 리그별·유럽 축구는 같은 리그 글끼리 붙여서(경기가 많은 리그부터), 리그 안에서는 개요 → 정배 → 홈 → 언더오버 → 핸디캡 → 역배 순
    order = ["league-", "fd-", "fav-", "home-", "ou-", "hc-", "upset-", "goals-", "draws-", "o25-"]
    lg_n = Counter()
    for g in games:
        lg_n[g["league"]] += 1
    for code, rws in fd.items():
        lg_n[FD_NAME.get(code, code)] += len(rws)
    def k(a):
        t = next((i for i, p in enumerate(order) if a["slug"].startswith(p)), 99)
        return (-lg_n.get(a["league"], 0), a["league"] or "", t) if a["cat"] in ("리그별", "유럽 축구") else (0, "", 0)
    out.sort(key=k)
    for a in out:
        a["games"] = lg_n.get(a["league"], 0) if a["league"] else 0
    return out
