"""쓰레드용 카드 이미지(1080×1350). 조합 폴더 위주, 카드마다 일부 경기를 가려서 사이트로 오게 한다.

카드: ① 적중 확률 높은 경기 ② 역배 후보 ③ 공격형 조합 ④ 로또폴더 ⑤ 사이트 주소
배당은 사이트 화면과 같이 베트맨(구매) 배당. HTML 로 그려 Playwright(Chromium)로 PNG 저장.
"""
from __future__ import annotations

import html
from datetime import date
from pathlib import Path

from . import config

FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
WEEK = "월화수목금토일"
W, H = 1080, 1350


def _e(s) -> str:
    return html.escape(str(s))


def _bub(l: dict) -> str:
    mk, k, line = l.get("market"), l.get("outcome"), l.get("line")
    if mk == "OU":
        return f"{'오버' if k == 'O' else '언더'} {line:g}" if line is not None else ("오버" if k == "O" else "언더")
    if mk == "HANDICAP":
        return f"핸디승 {line:+g}" if k == "H" else "핸디무" if k == "D" else "핸디패"
    return {"H": "승", "D": "무", "A": "패"}.get(k, k)


def _when(l: dict) -> str:
    ko = l.get("kickoff", "")
    return f"{int(ko[5:7])}/{int(ko[8:10])} {ko[11:16]}" if len(ko) >= 16 else ""


def _key(l: dict) -> str:
    return f"{l.get('kickoff', '')[:16]}|{l.get('home')}|{l.get('away')}"


def _round(legs: list[dict]) -> str:
    rs = []
    for l in legs:
        t = str(l.get("round") or "")
        lb = f"{int(t[2:])}회차" if t.isdigit() and len(t) == 6 else ""
        if lb and lb not in rs:
            rs.append(lb)
    return " · ".join(rs)


def _no(l: dict) -> str:
    return f"{l['game_no']}번 · " if l.get("game_no") else ""


def _day(d: str) -> str:
    x = date.fromisoformat(d)
    return f"{x.month}월 {x.day}일 ({WEEK[x.weekday()]})"


CSS = f"""
@font-face{{font-family:JO;src:url('{(FONTS / 'Jost.ttf').as_uri()}')}}
@font-face{{font-family:PT;font-weight:500;src:url('{(FONTS / 'Pretendard-Medium.otf').as_uri()}')}}
@font-face{{font-family:PT;font-weight:700;src:url('{(FONTS / 'Pretendard-Bold.otf').as_uri()}')}}
*{{box-sizing:border-box}}html,body{{margin:0}}
.card{{width:{W}px;height:{H}px;padding:70px 64px;display:flex;flex-direction:column;font-family:JO,PT;color:#121414;
  background:radial-gradient(circle at 20% 0%,#ffffff 0,#edf2ef 55%);position:relative;overflow:hidden}}
.top{{display:flex;align-items:center;gap:16px;font:500 30px JO,PT;color:#5c6662}}
.mark{{width:46px;height:46px;border-radius:50%;background:conic-gradient(from 90deg,#ff3d7f,#ffd23d,#18c4b0,#6c7bff,#ff3d7f);box-shadow:inset 0 0 0 6px rgba(255,255,255,.4)}}
.brand{{font:700 36px JO,PT;color:#121414}}.brand b{{font:700 20px JO;color:#ff3d7f;margin-left:4px}}
.date{{margin-left:auto}}
.body{{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:safe center;padding-top:18px}}
.body h1,.body .sub,.body .note{{text-align:center}}
h1{{font:700 84px/1.1 JO,PT;margin:0 0 10px}}
.sub{{font:500 30px PT;color:#5c6662;margin:0 0 34px}}
.list{{display:flex;flex-direction:column;gap:18px}}
.list.many{{gap:12px}}.list.many .row{{padding:18px 28px}}.list.many .match{{font-size:32px}}.list.many .meta{{font-size:22px}}
.row{{background:#fff;border:2px solid #d9e2de;border-radius:28px;padding:26px 30px;display:grid;grid-template-columns:1fr auto;gap:6px 20px;align-items:center}}
.meta{{font:500 24px PT;color:#7b8581}}
.match{{font:700 36px/1.25 PT;word-break:keep-all}}
.match i{{font:600 22px JO;color:#9aa3a0;font-style:normal;padding:0 8px}}
.right{{grid-row:1/3;grid-column:2;text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:10px}}
.bub{{display:inline-block;background:#121414;color:#fff;font:700 28px PT;padding:10px 20px;border-radius:999px;white-space:nowrap}}
.odds{{font:700 34px JO;letter-spacing:-1px}}
.pct{{font:700 26px PT;color:#0b9a7e}}
.lock{{background:repeating-linear-gradient(135deg,#f6f9f7 0 18px,#edf2ef 18px 36px);border-style:dashed}}
.lock .match{{color:#9aa3a0}}
.lock .bub{{background:#ff3d7f}}
.ticket{{background:#fff;border:2px solid #d9e2de;border-radius:36px;padding:34px 34px 30px;display:flex;flex-direction:column;gap:14px}}
.thead{{display:flex;align-items:baseline;justify-content:space-between;border-bottom:3px dashed #d9e2de;padding-bottom:20px;margin-bottom:6px}}
.total{{font:700 76px JO;letter-spacing:-3px}}
.size{{font:700 30px PT;color:#5c6662}}
.leg{{display:grid;grid-template-columns:1fr auto auto;gap:18px;align-items:center;padding:12px 0;border-bottom:1px solid #edf2ef}}
.leg:last-child{{border-bottom:0}}
.leg .match{{font-size:32px}}
.leg .odds{{font-size:30px;min-width:96px;text-align:right}}
.leg.lock{{background:none;border-radius:16px;padding:12px 16px;margin:0 -16px;background:repeating-linear-gradient(135deg,#fff 0 16px,#fbeef3 16px 32px)}}
.foot{{margin-top:auto;display:flex;justify-content:space-between;align-items:center;font:500 28px PT;color:#5c6662}}
.foot b{{color:#ff3d7f;font-weight:700}}
.cta{{align-items:center;justify-content:center;text-align:center;background:radial-gradient(circle at 50% 40%,#202426 0,#121414 65%);color:#fff}}
.cta .big{{width:300px;height:300px;border-radius:50%;background:conic-gradient(from 90deg,#ff3d7f,#ffd23d,#18c4b0,#6c7bff,#ff3d7f);box-shadow:inset 0 0 0 36px rgba(255,255,255,.4),0 0 120px rgba(108,123,255,.35)}}
.cta h2{{font:700 72px/1.25 JO,PT;margin:0 0 50px}}
.url{{display:inline-flex;align-items:center;gap:18px;background:#fff;color:#121414;border-radius:999px;padding:26px 46px;font:700 64px JO,PT}}
.url b{{font:700 34px JO;color:#ff3d7f}}
.url .lockic{{font-size:40px}}
.cta p{{font:500 30px PT;color:#bfc1c4;margin:36px 0 0}}
.slogan{{font:600 40px JO,PT!important;color:#fff!important;margin:0 0 40px!important}}
.free{{font:600 34px JO,PT!important;color:#fff!important;margin:34px 0 0!important}}.free b{{color:#ffd23d}}
.care{{position:absolute;left:64px;right:64px;bottom:64px;font:500 24px/1.6 PT;color:#9a9ea3;border-top:1px solid #2a2c30;padding-top:28px}}
.care b{{color:#fff;font-weight:700;font-size:28px}}
.note{{font:500 24px PT;color:#7b8581;margin-top:18px}}
.cover{{background:radial-gradient(circle at 50% 40%,#202426 0,#121414 65%);color:#fff}}
.cv-top{{display:flex;align-items:center;gap:16px}}.cover .brand{{color:#fff}}
.cv-mid{{flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center}}
.cv-date{{font:700 96px JO,PT;letter-spacing:-2px;margin:0;line-height:1}}
.cv-date span{{font:600 56px JO,PT;letter-spacing:0;color:#bfc1c4;margin-left:14px;vertical-align:8px}}
.cv-round{{font:600 36px JO,PT;color:#121414;background:#fff;border-radius:999px;padding:12px 34px;margin:36px 0 0}}
.cv-title{{font:800 132px/1.08 JO,PT;letter-spacing:-3px;margin:60px 0 0;color:#fff}}
.cv-slogan{{font:500 40px JO,PT;color:#bfc1c4;margin:40px 0 0}}
.cv-chips{{display:flex;flex-wrap:wrap;justify-content:center;gap:12px}}
.cv-chips span{{font:600 26px JO,PT;color:#bfc1c4;border:2px solid #34373b;border-radius:999px;padding:10px 22px}}
.many{{gap:6px;padding-top:26px}}.many .leg{{padding:6px 0}}.many .leg .match{{font-size:29px}}.many .meta{{font-size:21px}}.many .total{{font-size:64px}}.many .leg.lock{{margin:0;padding:8px 14px}}
"""


def _top(d: str, legs: list[dict] | None = None) -> str:
    rd = _round(legs or [])
    return (f'<div class="top"><span class="mark"></span><span class="brand">스포츠분석<b>.kr</b></span>'
            f'<span class="date">{_e(_day(d))}{(" · 베트맨 " + _e(rd)) if rd else ""}</span></div>')


def _page(d: str, legs: list[dict], body: str) -> str:
    return f'<div class="card">{_top(d, legs)}<div class="body">{body}</div></div>'


def _locked_row() -> str:
    return ('<div class="row lock"><div class="meta">🔒 숨김</div><div class="right"><span class="bub">?</span></div>'
            '<div class="match">사이트에서 공개</div></div>')


def _hidden(items: list[dict], n: int) -> set[int]:
    """확률이 가장 높은 n개를 가린다(가장 궁금한 선택은 사이트에서만)."""
    order = sorted(range(len(items)), key=lambda i: -items[i].get("p", 0))
    return set(order[:max(0, min(n, len(items) - 1))])


def _row(l: dict, right: str) -> str:
    return (f'<div class="row"><div class="meta">{_e(_no(l))}{_e(l.get("league", ""))} · {_e(_when(l))}</div>'
            f'<div class="right">{right}</div><div class="match">{_e(l["home"])}<i>vs</i>{_e(l["away"])}</div></div>')


def card_picks(d: str, picks: list[dict], hide: int = 2) -> str:
    hid = _hidden(picks, hide)
    rows = "".join(_locked_row() if i in hid else _row(l, f'<span class="bub">{_e(_bub(l))}</span><span class="pct">{l["p"] * 100:.0f}% · {l["odds"]:.2f}배</span>')
                   for i, l in enumerate(picks))
    return _page(d, picks, f'<h1>적중 확률 높은 경기</h1><p class="sub">해외 배당 기준 분석 · 배당은 베트맨</p><div class="list{" many" if len(picks) >= 5 else ""}">{rows}</div>')


def card_upsets(d: str, ups: list[dict], hide: int = 2) -> str:
    hid = _hidden(ups, hide)
    rows = "".join(_locked_row() if i in hid else _row(l, f'<span class="bub">{_e(_bub(l))}</span><span class="odds">{l["odds"]:.2f}</span>')
                   for i, l in enumerate(ups))
    return _page(d, ups, f'<h1>역배 후보</h1><p class="sub">해외 시장은 열세로 보지만 기록·레이팅이 받쳐주는 팀</p><div class="list{" many" if len(ups) >= 5 else ""}">{rows}</div>')


def card_combo(d: str, title: str, c: dict, hide: int = 2) -> str:
    legs = sorted(c["legs"], key=lambda l: l.get("kickoff", ""))
    hid = _hidden(legs, hide)  # 가장 확실한 경기들은 사이트에서만
    rows = []
    for i, l in enumerate(legs):
        if i in hid:
            rows.append('<div class="leg lock"><div><div class="meta">🔒 숨김</div><div class="match">사이트에서 공개</div></div>'
                        '<span class="bub">?</span><span class="odds">?.??</span></div>')
        else:
            rows.append(f'<div class="leg"><div><div class="meta">{_e(_no(l))}{_e(l.get("league", ""))} · {_e(_when(l))}</div>'
                        f'<div class="match">{_e(l["home"])}<i>vs</i>{_e(l["away"])}</div></div>'
                        f'<span class="bub">{_e(_bub(l))}</span><span class="odds">{l["odds"]:.2f}</span></div>')
    return _page(d, legs, f'<h1>{_e(title)}</h1><p class="sub">예상 적중률 {c["joint_p"] * 100:.1f}% · 1만 원 적중 시 {c["payout"]:,}원</p>'
                 f'<div class="ticket{" many" if len(legs) >= 6 else ""}"><div class="thead"><span class="total">×{c["total_odds"]:.2f}</span><span class="size">{c["size"]}폴더</span></div>{"".join(rows)}</div>'
                 f'<p class="note">숨긴 {len(hid)}경기는 사이트에서 확인하세요.</p>')


def card_cover(d: str, rep: dict, slot: str) -> str:
    """표지(썸네일): 날짜·요일, 베트맨 회차, 제목, 슬로건."""
    x = date.fromisoformat(d)
    rd = _round(list(rep.get("markets") or []))
    n = (rep.get("stats") or {}).get("matches", 0)
    when = "내일 08시 발매" if slot == "night" else "오늘 08시 발매"
    return ('<div class="card cover"><div class="cv-top"><span class="mark"></span><span class="brand">스포츠분석<b>.kr</b></span></div>'
            f'<div class="cv-mid"><p class="cv-date">{x.month}월 {x.day}일 <span>{WEEK[x.weekday()]}요일</span></p>'
            f'<p class="cv-round">{("베트맨 " + _e(rd)) if rd else "베트맨 프로토 승부식"}</p>'
            '<h1 class="cv-title">프로토<br>스포츠 분석</h1>'
            '<p class="cv-slogan">데이터와 수학으로, 분석을 똑똑하게</p></div></div>')


def card_cta(d: str) -> str:
    return ('<div class="card cta"><p class="slogan">데이터와 수학으로, 분석을 똑똑하게</p><h2>숨긴 경기와<br>전체 조합은 여기서</h2>'
            '<div class="url"><span class="lockic">🔗</span>스포츠분석<b>.kr</b></div>'
            '<p class="free">모든 분석과 조합은 <b>무료</b> · 회원가입 없이 바로</p>'
            '<p>프로필 링크를 누르면 바로 이동합니다</p>'
            '<p>매일 자동 업데이트 · 경기 일정과 분석 모두 무료</p>'
            '<div class="care"><b>잃어도 괜찮은 소액으로, 재미로만 즐기세요.</b><br>분석은 참고용이며 적중을 보장하지 않습니다. 만 19세 이상 · 베트맨 공식 채널에서만<br>도박 문제 상담 1336 (24시간 무료)</div></div>')


def _best(cs: list[dict]) -> dict | None:
    live = [c for c in cs or [] if c.get("result") not in ("lose", "win")]
    return max(live, key=lambda c: c.get("joint_p", 0)) if live else None


SHOW_N = 5  # 적중 확률·역배 카드 한 장에 5경기
# 주인 요청(11/21): 두 카드 중 한 장은 3개, 다른 한 장은 2개를 가린다. 게시할 때마다 3개 가리는 카드가 번갈아 바뀐다.
SHOW_MIN, HIDE = 2, 3


def build(rep: dict, slot: str = "night", exclude: set[str] | None = None) -> tuple[list[str], list[str]]:
    """(카드 HTML 목록, 쓴 경기 키). 아침에는 밤에 쓴 경기·조합을 피한다."""
    used = set(exclude or ())
    d = rep["date"]
    out: list[str] = []
    shown: list[str] = []

    def take(pool, n, need=SHOW_MIN):
        """pool 에서 n 개. 아침에 밤 경기를 빼고 나니 보이는 경기가 need 개보다 적으면, 밤에 쓴 경기도 다시 써서 채운다."""
        res = []
        for l in pool:
            k = _key(l)
            if k in used:
                continue
            used.add(k)
            shown.append(k)
            res.append(l)
            if len(res) >= n:
                break
        if len(res) < need + HIDE:
            for l in pool:
                k = _key(l)
                if l in res or k in {_key(x) for x in res}:
                    continue
                res.append(l)
                if k not in shown:
                    shown.append(k)
                if len(res) >= need + HIDE:
                    break
        return res

    # 게시 순서: 밤(D) = 전날 19시, 아침(D) = 당일 7시, 밤(D+1) = 당일 19시 … 이 순서의 홀짝으로 번갈아
    from datetime import date as _date
    order = 2 * _date.fromisoformat(d).toordinal() + (0 if slot == "morning" else -1)
    picks_three = order % 2 == 0

    def hide_n(items, three):
        """5개 중 3개 또는 2개를 가린다(경기가 적으면 최소 1개는 보이게)."""
        return max(0, min(3 if three else 2, len(items) - 1))

    out.append(card_cover(d, rep, slot))
    tops = list(rep.get("top_picks") or [])
    if slot == "morning":
        tops = sorted(tops + list(rep.get("handi_picks") or []) + list(rep.get("ou_picks") or []), key=lambda l: -l["p"])
    picks = take(tops, SHOW_N)
    ups = take(list(rep.get("upsets") or []), SHOW_N)
    if not ups:  # 역배 카드가 없는 날은 적중 확률 카드에서 3개
        picks_three = True
    if picks:
        out.append(card_picks(d, picks, hide_n(picks, picks_three)))
    if ups:
        out.append(card_upsets(d, ups, hide_n(ups, not picks_three)))
    for key, title in (("aggressive", "공격형 조합"), ("lotto", "로또폴더")):
        cs = list((rep.get("combos") or {}).get(key) or [])
        # 아침에는 밤에 올린 조합과 경기가 덜 겹치는 조합을 고른다
        cs.sort(key=lambda c: (sum(_key(l) in (exclude or ()) for l in c["legs"]), -c.get("joint_p", 0)))
        c = cs[0] if cs and slot == "morning" else _best(cs)
        if c:
            out.append(card_combo(d, title, c, 4 if key == "lotto" else 2))
            shown += [_key(l) for l in c["legs"]]
    out.append(card_cta(d))
    return out, shown


PV_CSS = """
.pv-list{display:flex;flex-direction:column;gap:22px;margin-top:8px}
.pv-g{background:#fff;border:2px solid #e3e9e6;border-radius:30px;padding:30px 36px}
.pv-meta{font:600 26px PT;color:#7b8581}
.pv-meta b{color:#121414;font:700 30px JO;margin-right:12px}
.pv-teams{font:800 46px/1.3 JO,PT;letter-spacing:-1px;margin:14px 0 18px;word-break:keep-all}
.pv-teams i{font:500 30px PT;font-style:normal;color:#9aa3a0;margin:0 12px}
.pv-row{display:flex;align-items:center;justify-content:space-between;gap:20px}
.pv-odds{display:flex;gap:22px;font:700 32px JO;color:#3f4744}
.pv-odds i{font:600 24px PT;font-style:normal;color:#9aa3a0;margin-right:6px}
.pv-lock{font:700 26px PT;color:#fff;background:#ff3d7f;border-radius:999px;padding:10px 22px;white-space:nowrap}
"""
CSS += PV_CSS


def card_preview(d: str, title: str, sub: str, games: list[dict]) -> str:
    """빅매치 미리보기: 경기 시간·리그·팀·베트맨 배당. 모델 픽은 사이트에서(가림)."""
    items = []
    for g in games[:3]:
        od = g.get("odds") or {}
        keys = ["H", "D", "A"] if g.get("mk") == "1X2" else ["H", "A"]
        lab = {"H": "승", "D": "무", "A": "패"}
        odds = "".join(f'<span><i>{lab[k]}</i>{od[k]:.2f}</span>' for k in keys if od.get(k))
        items.append(f'<div class="pv-g"><div class="pv-meta"><b>{_e(g["kickoff"][11:16])}</b>{_e(g.get("league", ""))}</div>'
                     f'<div class="pv-teams">{_e(g["home"])}<i>vs</i>{_e(g["away"])}</div>'
                     f'<div class="pv-row"><div class="pv-odds">{odds}</div><span class="pv-lock">🔒 픽은 사이트에서</span></div></div>')
    return (f'<div class="card">{_top(d)}<div class="body"><h1>{_e(title)}</h1><p class="sub">{_e(sub)}</p>'
            f'<div class="pv-list">{"".join(items)}</div></div></div>')


def card_result(d: str, res: dict) -> str:
    """전날 결과 카드 한 장. 숫자만, 부정적인 말 없이(규칙을 정해 매일 같은 모양)."""
    def blk(label, big, small=""):
        return (f'<div class="rs-b"><p class="rs-l">{_e(label)}</p><p class="rs-n">{big}</p>'
                + (f'<p class="rs-s">{_e(small)}</p>' if small else "") + "</div>")
    parts = [f'<h1>어제의 결과</h1><p class="sub">{_e(_day(d))} 프로토 승부식</p>', '<div class="rs-grid">']
    if res.get("hi_n"):
        parts.append(blk("배당 1.50 이상 픽", f'{res["hi_hit"]}<i>/</i>{res["hi_n"]}', "적중"))
    parts.append(blk("전체 픽", f'{res["hit"]}<i>/</i>{res["n"]}', f"적중 {res['rate'] * 100:.0f}%"))
    parts.append(blk("최근 30일 적중률", f'{res["r30"] * 100:.0f}<i>%</i>', f"픽 {res['n30']:,}개 기준"))
    parts.append("</div>")
    if res.get("highlight"):
        parts.append(f'<div class="rs-hi"><p class="rs-l">어제의 한 장면</p><p class="rs-h">{_e(res["highlight"])}</p></div>')
    parts.append('<p class="note">모든 픽 기록은 스포츠분석.kr 성과 페이지에 그대로 남아 있습니다</p>')
    return f'<div class="card">{_top(d)}<div class="body">{"".join(parts)}</div></div>'


RESULT_CSS = """
.rs-grid{display:grid;grid-template-columns:1fr;gap:18px;margin-top:6px}
.rs-b{background:#fff;border:2px solid #d9e2de;border-radius:28px;padding:26px 34px;display:grid;grid-template-columns:1fr auto;align-items:center;gap:4px 20px}
.rs-l{font:600 30px PT;color:#5c6662;margin:0}
.rs-n{grid-row:1/3;grid-column:2;font:700 92px/1 JO;letter-spacing:-3px;margin:0;color:#121414}
.rs-n i{font-style:normal;color:#9aa3a0;font-size:64px;margin:0 6px}
.rs-s{font:500 26px PT;color:#0b9a7e;margin:0}
.rs-hi{margin-top:22px;background:#121414;color:#fff;border-radius:28px;padding:28px 34px}
.rs-hi .rs-l{color:#bfc1c4}
.rs-h{font:700 44px/1.3 PT;margin:8px 0 0;word-break:keep-all}
"""
CSS += RESULT_CSS


# ───────────── 노하우 카드 묶음 ─────────────
KH_CSS = """
.khc{background:radial-gradient(circle at 50% 30%,#202426 0,#121414 70%);color:#fff}
.khc .brand{color:#fff}.khc .top{color:#bfc1c4}
.kh-eye{font:700 30px JO,PT;color:#ff7aa8;letter-spacing:2px;margin:0 0 26px}
.kh-t{font:800 84px/1.18 JO,PT;letter-spacing:-2px;margin:0;word-break:keep-all}
.kh-l{font:500 36px/1.6 PT;color:#d4d6d9;margin:44px 0 0;word-break:keep-all}
.kh-h{font:700 56px/1.25 JO,PT;margin:0 0 30px;word-break:keep-all}
.kh-tbl{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border:2px solid #d9e2de;border-radius:28px;overflow:hidden;font:600 30px PT}
.kh-tbl th{font:700 24px PT;color:#7b8581;text-align:right;padding:20px 22px;background:#f6f9f7;border-bottom:2px solid #d9e2de;white-space:nowrap}
.khc .body h1,.khc .body p{text-align:left}
.kh-tbl th:first-child,.kh-tbl td:first-child{text-align:left}
.kh-tbl td{padding:20px 22px;text-align:right;border-bottom:1px solid #edf2ef;font-variant-numeric:tabular-nums}
.kh-tbl tr:last-child td{border-bottom:0}
.kh-p{font:500 38px/1.65 PT;margin:0 0 30px;word-break:keep-all}
.kh-p b{color:#0b9a7e}
.kh-num{font:800 150px/1 JO;letter-spacing:-5px;margin:40px 0 0;color:#ffd23d}
"""
CSS += KH_CSS


def card_kh_cover(d: str, cat: str, title: str, lead: str, big: str | None = None) -> str:
    return (f'<div class="card khc">{_top(d)}<div class="body"><p class="kh-eye">노하우 · {_e(cat)}</p>'
            f'<h1 class="kh-t">{_e(title)}</h1>' + (f'<p class="kh-num">{_e(big)}</p>' if big else "") + f'<p class="kh-l">{_e(lead)}</p></div></div>')


def card_kh_table(d: str, heading: str, head: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{_e(h)}</th>" for h in head)
    trs = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="card">{_top(d)}<div class="body"><h2 class="kh-h">{_e(heading)}</h2><table class="kh-tbl"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div></div>'


def card_kh_text(d: str, heading: str, paras: list[str]) -> str:
    ps = "".join(f'<p class="kh-p">{_e(x)}</p>' for x in paras)
    return f'<div class="card">{_top(d)}<div class="body"><h2 class="kh-h">{_e(heading)}</h2>{ps}</div></div>'


def card_link(line1: str, line2: str) -> str:
    """마지막 장: 사이트 주소와 안내(노하우·결과 묶음 공통)."""
    return (f'<div class="card cta"><p class="slogan">데이터와 수학으로, 분석을 똑똑하게</p><h2>{_e(line1)}<br>{_e(line2)}</h2>'
            '<div class="url"><span class="lockic">🔗</span>스포츠분석<b>.kr</b></div>'
            '<p class="free">모든 분석과 기록은 <b>무료</b> · 회원가입 없이 바로</p>'
            '<p>프로필 링크를 누르면 바로 이동합니다</p>'
            '<div class="care"><b>잃어도 괜찮은 소액으로, 재미로만 즐기세요.</b><br>분석은 참고용이며 적중을 보장하지 않습니다. 만 19세 이상 · 베트맨 공식 채널에서만<br>도박 문제 상담 1336 (24시간 무료)</div></div>')


# ───────────── 전날 결과 묶음 ─────────────
RES2_CSS = """
.rp{display:grid;grid-template-columns:1fr auto;gap:4px 18px;align-items:center;background:#fff;border:2px solid #d9e2de;border-radius:24px;padding:18px 26px}
.rp .match{font-size:30px}.rp .meta{font-size:22px}
.rp .rt{grid-row:1/3;grid-column:2;display:flex;align-items:center;gap:14px}
.rp .ok{font:700 26px PT;color:#fff;background:#0b9a7e;border-radius:999px;padding:8px 18px}
.rp .no{font:700 26px PT;color:#9aa3a0;background:#edf2ef;border-radius:999px;padding:8px 18px}
.rp.hit{border-color:#0b9a7e}
.rl{display:flex;flex-direction:column;gap:12px}
.rs-row{display:grid;grid-template-columns:1fr auto;align-items:center;background:#fff;border:2px solid #d9e2de;border-radius:24px;padding:22px 30px;font:700 34px PT}
.rs-row em{display:block;font:700 26px PT;font-style:normal;color:#0b9a7e;margin-top:4px}
.rp .dog{display:inline-block;background:#ff3d7f;color:#fff;font:700 22px PT;padding:3px 12px;border-radius:999px;margin-right:10px;vertical-align:1px}
.rs-row span{font:700 46px JO;letter-spacing:-1px}.rs-row span i{font-style:normal;color:#9aa3a0;font-size:34px}
"""
CSS += RES2_CSS


def card_result_picks(d: str, rows: list[dict]) -> str:
    """어제 픽을 확률 높은 순으로(맞힌 것만 고르지 않고 위에서부터 그대로)."""
    items = []
    for r in rows:
        badge = '<span class="ok">적중</span>' if r["hit"] else '<span class="no">—</span>'
        dog = '<b class="dog">역배</b>' if r.get("dog") else ""
        items.append(f'<div class="rp{" hit" if r["hit"] else ""}"><div class="meta">{dog}{_e(r["meta"])}</div>'
                     f'<div class="rt"><span class="bub">{_e(r["pick"])}</span><span class="odds">{r["odds"]:.2f}</span>{badge}</div>'
                     f'<div class="match">{_e(r["home"])}<i>vs</i>{_e(r["away"])}</div></div>')
    return f'<div class="card">{_top(d)}<div class="body"><h1 style="font-size:64px">어제의 픽</h1><p class="sub">{"적중한 역배와 " if any(r.get("dog") for r in rows) else ""}배당 1.50 이상 픽, 경기 시작 순서대로</p><div class="rl">{"".join(items)}</div></div></div>'


def card_result_combos(d: str, rows: list[tuple], best: str | None) -> str:
    rs = "".join(f'<div class="rs-row"><div>{_e(r[0])}' + (f'<em>최고 ×{r[3]:.2f}</em>' if len(r) > 3 and r[3] else "")
                 + f'</div><span>{r[1]}<i>/</i>{r[2]}</span></div>' for r in rows)
    hi = f'<div class="rs-hi"><p class="rs-l">가장 큰 적중</p><p class="rs-h">{_e(best)}</p></div>' if best else ""
    return f'<div class="card">{_top(d)}<div class="body"><h1 style="font-size:64px">전략별 조합</h1><p class="sub">발행한 조합 중 적중</p><div class="rl">{rs}</div>{hi}</div></div>'


KH2_CSS = """
.ks{display:flex;flex-direction:column;gap:22px;margin-top:10px}
.ks-r{display:flex;justify-content:space-between;align-items:baseline;gap:30px;padding:30px 40px;background:#fff;border-radius:32px}
.ks-r span{font:600 38px PT;color:#3f4744;word-break:keep-all}
.ks-r b{font:800 76px/1 JO;letter-spacing:-2px;color:#121414;white-space:nowrap}
.ks-cap{font:600 30px PT;color:#7b8581;margin:0 0 6px}
.kq{font:700 58px/1.5 JO,PT;letter-spacing:-1px;margin:0;word-break:keep-all;text-align:left}
.kq-n{font:700 30px JO;color:#ff3d7f;margin:0 0 30px;text-align:left}
"""
CSS += KH2_CSS


def card_kh_stats(d: str, heading: str, caption: str, rows: list[tuple[str, str]]) -> str:
    """표 대신 핵심 숫자만 크게(최대 4줄)."""
    rs = "".join(f'<div class="ks-r"><span>{_e(a)}</span><b>{_e(b)}</b></div>' for a, b in rows[:4])
    return (f'<div class="card">{_top(d)}<div class="body"><h2 class="kh-h">{_e(heading)}</h2>'
            + (f'<p class="ks-cap">{_e(caption)}</p>' if caption else "") + f'<div class="ks">{rs}</div></div></div>')


def card_kh_quote(d: str, text: str, n: str = "") -> str:
    """정리 문장 한두 개를 한 장에 크게."""
    return (f'<div class="card">{_top(d)}<div class="body">' + (f'<p class="kq-n">{_e(n)}</p>' if n else "")
            + f'<p class="kq">{_e(text)}</p></div></div>')


def render(cards: list[str], out_dir: Path, prefix: str) -> list[Path]:
    """카드 HTML → JPEG. 러너에 깔린 크롬으로 그리다가 어디서든 실패하면 playwright 크롬을 받아 처음부터 다시 그린다."""
    import os
    exe = os.getenv("CHROMIUM_PATH") or None
    try:
        return _render(cards, out_dir, prefix, exe)
    except Exception:  # noqa: BLE001
        if not exe:
            raise
        import subprocess
        import sys
        subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return _render(cards, out_dir, prefix, None)


def _render(cards: list[str], out_dir: Path, prefix: str, exe: str | None) -> list[Path]:
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe, args=["--no-sandbox"] if exe else None)
        pg = b.new_page(viewport={"width": W, "height": H})
        for i, c in enumerate(cards, 1):
            # 빈 페이지(about:blank)에서는 로컬 글꼴 파일이 막히므로 파일로 저장해서 연다
            tmp = out_dir / f"_{prefix}-{i}.html"
            tmp.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{c}</body></html>", encoding="utf-8")
            pg.goto(tmp.as_uri())
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(300)
            path = out_dir / f"{prefix}-{i}.jpg"
            pg.screenshot(path=str(path), type="jpeg", quality=88, clip={"x": 0, "y": 0, "width": W, "height": H})
            paths.append(path)
            tmp.unlink(missing_ok=True)
        b.close()
    return paths
