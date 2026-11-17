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
.body{{flex:1;display:flex;flex-direction:column;justify-content:center}}
.body h1,.body .sub,.body .note{{text-align:center}}
h1{{font:700 84px/1.1 JO,PT;margin:0 0 10px}}
.sub{{font:500 30px PT;color:#5c6662;margin:0 0 34px}}
.list{{display:flex;flex-direction:column;gap:18px}}
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
    return _page(d, picks, f'<h1>적중 확률 높은 경기</h1><p class="sub">해외 배당 기준 분석 · 배당은 베트맨</p><div class="list">{rows}</div>')


def card_upsets(d: str, ups: list[dict], hide: int = 2) -> str:
    hid = _hidden(ups, hide)
    rows = "".join(_locked_row() if i in hid else _row(l, f'<span class="bub">{_e(_bub(l))}</span><span class="odds">{l["odds"]:.2f}</span>')
                   for i, l in enumerate(ups))
    return _page(d, ups, f'<h1>역배 후보</h1><p class="sub">해외 시장은 열세로 보지만 기록·레이팅이 받쳐주는 팀</p><div class="list">{rows}</div>')


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
            '<p>매일 밤 10시 · 아침 7시 업데이트</p>'
            '<div class="care"><b>잃어도 괜찮은 소액으로, 재미로만 즐기세요.</b><br>분석은 참고용이며 적중을 보장하지 않습니다. 만 19세 이상 · 베트맨 공식 채널에서만<br>도박 문제 상담 1336 (24시간 무료)</div></div>')


def _best(cs: list[dict]) -> dict | None:
    live = [c for c in cs or [] if c.get("result") not in ("lose", "win")]
    return max(live, key=lambda c: c.get("joint_p", 0)) if live else None


def build(rep: dict, slot: str = "night", exclude: set[str] | None = None) -> tuple[list[str], list[str]]:
    """(카드 HTML 목록, 쓴 경기 키). 아침에는 밤에 쓴 경기·조합을 피한다."""
    used = set(exclude or ())
    d = rep["date"]
    out: list[str] = []
    shown: list[str] = []

    def take(pool, n):
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
        return res

    out.append(card_cover(d, rep, slot))
    tops = list(rep.get("top_picks") or [])
    if slot == "morning":
        tops = sorted(tops + list(rep.get("handi_picks") or []) + list(rep.get("ou_picks") or []), key=lambda l: -l["p"])
    picks = take(tops, 4)
    if picks:
        out.append(card_picks(d, picks, 2))
    ups = take(list(rep.get("upsets") or []), 4)
    if ups:
        out.append(card_upsets(d, ups, 2))
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


def render(cards: list[str], out_dir: Path, prefix: str) -> list[Path]:
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        import os
        exe = os.getenv("CHROMIUM_PATH") or None  # 미리 깔린 크롬을 쓸 때만(GitHub Actions 는 playwright install 기본 경로)
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
