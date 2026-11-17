"""배당 흐름 차트(경기 페이지). 베트맨 배당 변동(시각별)과 해외 배당 기록을 SVG 선으로 그린다.

- 선 색: 승·오버 초록, 패·언더 빨강, 무 노랑(사이트 색 규칙과 같음). 해외 배당은 같은 색 점선.
- 배당이 내려간 쪽 = 그쪽 구매가 몰린 쪽. 요약 문장으로 알려준다.
- 기록이 처음·지금 두 점뿐인 예전 리포트도 그린다.
"""
from __future__ import annotations

from datetime import datetime

from markupsafe import Markup, escape

COL = {"H": "#2fbf71", "O": "#2fbf71", "A": "#ef5a5a", "U": "#ef5a5a", "D": "#e3b341"}
W, H, PL, PR, PT, PB = 640, 200, 44, 96, 14, 30


def _t(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y%m%d%H%M") if s else None
    except ValueError:
        return None


def series(m: dict) -> tuple[list, list]:
    """(베트맨 점들, 해외 점들). 점 = (시각 또는 None, {선택: 배당})."""
    fl = m.get("flow") or {}
    pts = [(_t(t), o) for t, o in (fl.get("pts") or []) if o]
    if not pts and (fl.get("from") or fl.get("to")):
        pts = [(None, fl.get("from") or {}), (_t(fl.get("at") or ""), fl.get("to") or {})]
    if not pts and m.get("odds"):
        pts = [(None, m["odds"])]
    xs = [(_t(t), o) for t, o in (m.get("xh") or []) if o]
    return pts, xs


def summary(m: dict, label) -> str:
    pts, _ = series(m)
    if len(pts) < 2:
        return ""
    a, b = pts[0][1], pts[-1][1]
    moves = {k: (b[k] - a[k]) / a[k] for k in a if k in b and a[k] > 1}
    if not moves:
        return ""
    k = min(moves, key=moves.get)
    if moves[k] > -0.02:
        return "배당이 거의 움직이지 않았습니다."
    parts = [f"{label(m, x)} {a[x]:.2f} → {b[x]:.2f}" for x in moves]
    return f"{' · '.join(parts)}. 배당이 내려간 {label(m, k)} 쪽으로 구매가 몰렸습니다."


def svg(m: dict, label) -> Markup:
    """처음 발매 배당 대비 변화율(%)로 그린다. 배당 크기가 달라도(1.09와 11.00) 움직임이 같은 눈금으로 보인다."""
    pts, xs = series(m)
    if len(pts) < 2 and len(xs) < 2:
        return Markup("")
    keys = [k for k in ("H", "D", "A", "O", "U") if any(k in o for _, o in pts)]
    base = {k: next((o[k] for _, o in pts if k in o), None) for k in keys}
    xbase = {k: next((o[k] for _, o in xs if k in o), None) for k in keys}

    def pct(v, b0):
        return (v / b0 - 1) * 100 if b0 else 0.0

    vals = [pct(o[k], base[k]) for _, o in pts for k in keys if k in o and base[k]]
    vals += [pct(o[k], xbase[k]) for _, o in xs for k in keys if k in o and xbase[k]]
    m_ = max([5.0] + [abs(v) for v in vals]) * 1.15
    lo, hi = -m_, m_
    times = [t for t, _ in pts + xs if t]
    t0, t1 = (min(times), max(times)) if times else (None, None)
    span = (t1 - t0).total_seconds() if t0 and t1 and t1 > t0 else 0

    def X(i, t, n):
        if span and t:
            return PL + 18 + (W - PL - PR - 18) * (t - t0).total_seconds() / span
        if t is None and i == 0:
            return PL
        return PL + 18 + (W - PL - PR - 18) * (i / max(1, n - 1))

    def Y(v):
        return PT + (H - PT - PB) * (hi - v) / (hi - lo)

    out = [f'<svg class="flow-svg" viewBox="0 0 {W} {H}" role="img" aria-label="배당 흐름(처음 대비 변화율)">']
    for v in (hi / 1.15, hi / 2.3, 0, lo / 2.3, lo / 1.15):
        y = Y(v)
        cls = "z" if v == 0 else "g"
        lab = "처음" if v == 0 else f"{v:+.0f}%"
        out.append(f'<line class="{cls}" x1="{PL}" x2="{W - PR}" y1="{y:.1f}" y2="{y:.1f}"/><text class="ax" x="{PL - 6}" y="{y + 4:.1f}" text-anchor="end">{lab}</text>')
    ends = []
    for k in keys:
        c = COL.get(k, "#9aa")
        seq = [(X(i, t, len(pts)), pct(o[k], base[k]), o[k]) for i, (t, o) in enumerate(pts) if k in o and base[k]]
        if seq:
            d = f"M{seq[0][0]:.1f},{Y(seq[0][1]):.1f}"
            for _, (x1, v1, _o) in zip(seq, seq[1:]):
                d += f"H{x1:.1f}V{Y(v1):.1f}"
            d += f"H{W - PR:.1f}"
            out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2.4"/>')
            for x, v, _o in seq:
                out.append(f'<circle cx="{x:.1f}" cy="{Y(v):.1f}" r="2.6" fill="{c}"/>')
            name = str(label(m, k)).split(" ")[0]
            ends.append([Y(seq[-1][1]), f"{name} {seq[-1][2]:.2f}", c])
        xseq = [(X(i, t, len(xs)), pct(o[k], xbase[k])) for i, (t, o) in enumerate(xs) if k in o and xbase[k]]
        if xseq:
            d = " ".join(f"{'M' if j == 0 else 'L'}{x:.1f},{Y(v):.1f}" for j, (x, v) in enumerate(xseq))
            if len(xseq) == 1:
                d += f" L{W - PR:.1f},{Y(xseq[0][1]):.1f}"
            out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="1.4" stroke-dasharray="4 4" opacity=".75"/>')
    # 끝 글자가 겹치지 않게 위아래로 띄운다(최소 14px)
    ends.sort(key=lambda e: e[0])
    for i in range(1, len(ends)):
        if ends[i][0] - ends[i - 1][0] < 14:
            ends[i][0] = ends[i - 1][0] + 14
    over = (ends[-1][0] - (H - PB)) if ends else 0
    if over > 0:
        for e in ends:
            e[0] -= over
    for y, txt, c in ends:
        out.append(f'<text class="end" x="{W - PR + 6}" y="{y + 4:.1f}" fill="{c}">{escape(txt)}</text>')
    out.append(f'<text class="ax" x="{PL}" y="{H - 8}">처음 발매</text>')
    if t1:
        out.append(f'<text class="ax" x="{W - PR}" y="{H - 8}" text-anchor="end">{t1.month}/{t1.day} {t1:%H:%M}</text>')
    out.append("</svg>")
    return Markup("".join(out))


def has_flow(m: dict) -> bool:
    pts, xs = series(m)
    return len(pts) >= 2 or len(xs) >= 2
