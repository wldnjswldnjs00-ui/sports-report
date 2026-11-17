"""공유 미리보기 이미지(1200×630, og:image).

카톡·쓰레드·검색 결과에 링크를 붙였을 때 보이는 카드. 페이지마다 그 페이지 내용으로 만든다.
브라우저 없이 Pillow 로만 그려서 Cloudflare 빌드 환경에서도 돈다. 글꼴은 engine/site/fonts(SIL OFL).
"""
from __future__ import annotations

import colorsys
import logging
import math
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("engine.og")
FONTS = Path(__file__).parent / "fonts"
W, H = 1200, 630
BG = (15, 17, 23)
CARD = (26, 29, 39)
LINE = (44, 49, 64)
INK = (238, 240, 247)
INK2 = (190, 196, 210)
INK3 = (128, 135, 154)
HOT = (255, 61, 127)
POS = (74, 222, 128)
NEG = (255, 107, 107)
DRAW = (251, 191, 36)

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    OK = True
except Exception:  # noqa: BLE001  Pillow 가 없으면 기본 이미지만 쓴다
    OK = False


@lru_cache(maxsize=64)
def _font(name: str, size: int):
    f = ImageFont.truetype(str(FONTS / name), size)
    if name.startswith("Unbounded"):
        try:
            f.set_variation_by_name("ExtraBold")
        except Exception:  # noqa: BLE001
            pass
    return f


def ko(size, weight="ExtraBold"):
    return _font(f"Pretendard-{weight}.otf", size)


def en(size):
    return _font("Unbounded-ExtraBold.ttf", size)


def dh(size):
    return _font("DoHyeon-Regular.ttf", size)


@lru_cache(maxsize=1)
def _base():
    """배경(아주 옅은 분홍·파랑 번짐) + 로고·이름 머리말."""
    im = Image.new("RGB", (W, H), BG)
    glow = Image.new("RGB", (W, H), BG)
    g = ImageDraw.Draw(glow)
    g.ellipse((-260, -320, 520, 300), fill=(70, 30, 58))
    g.ellipse((780, -260, 1500, 260), fill=(26, 44, 82))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    im = Image.blend(im, glow, 0.85)
    d = ImageDraw.Draw(im)
    _logo(im, 64, 52, 52)
    d.text((132, 50), "스포츠분석", font=dh(46), fill=INK)
    wx = 132 + d.textlength("스포츠분석", font=dh(46)) + 4
    d.text((wx, 66), ".kr", font=en(24), fill=HOT)
    return im


def _logo(im, x, y, s):
    """헤더 로고와 같은 무지갯빛 원(가운데에서 도는 색) + 흰 테두리."""
    k = 4
    big = Image.new("RGBA", (s * k, s * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    stops = [(0.0, (255, 61, 127)), (0.25, (255, 210, 61)), (0.5, (24, 196, 176)), (0.75, (108, 123, 255)), (1.0, (255, 61, 127))]
    n = 120
    for i in range(n):
        t = i / n
        for (a, ca), (b, cb) in zip(stops, stops[1:]):
            if a <= t <= b:
                u = (t - a) / (b - a)
                col = tuple(int(ca[j] + (cb[j] - ca[j]) * u) for j in range(3))
                break
        d.pieslice((0, 0, s * k - 1, s * k - 1), i * 360 / n - 90, (i + 1) * 360 / n - 90 + 0.8, fill=col + (255,))
    ring = s * k * 0.12
    d.ellipse((ring / 2, ring / 2, s * k - ring / 2, s * k - ring / 2), outline=(255, 255, 255, 100), width=int(ring))
    big = big.resize((s, s), Image.LANCZOS)
    im.paste(big, (x, y), big)


def _fit(d, text, font_fn, size, max_w, min_size=30):
    while size > min_size and d.textlength(text, font=font_fn(size)) > max_w:
        size -= 2
    return font_fn(size), size


def _ellipsis(d, text, font, max_w):
    if d.textlength(text, font=font) <= max_w:
        return text
    while text and d.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def tone(label: str):
    import re
    t = str(label or "")
    m = re.search(r"([+\-−])\d", t)
    if m:
        return NEG if m.group(1) in "-−" else POS
    if "오버" in t:
        return POS
    if "언더" in t:
        return NEG
    if "무" in t:
        return DRAW
    if "패" in t:
        return NEG
    if "승" in t:
        return POS
    return INK


def _pill(d, x, y, text, font, fg, bg=CARD, pad=(18, 10), border=LINE):
    w = d.textlength(text, font=font)
    h = font.size + pad[1] * 2
    d.rounded_rectangle((x, y, x + w + pad[0] * 2, y + h), radius=h // 2, fill=bg, outline=border, width=2)
    d.text((x + pad[0], y + pad[1] - 2), text, font=font, fill=fg)
    return x + w + pad[0] * 2


def _footer(d, left: str):
    d.line((64, 556, W - 64, 556), fill=LINE, width=2)
    d.text((64, 574), _ellipsis(d, left, ko(24, "SemiBold"), 820), font=ko(24, "SemiBold"), fill=INK3)
    t = "스포츠분석.kr"
    d.text((W - 64 - d.textlength(t, font=ko(24, "Bold")), 574), t, font=ko(24, "Bold"), fill=INK2)


def _save(im, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "JPEG", quality=86, optimize=True, progressive=True)


def _pick_card(d, x, y, w, label, pick, prob, odds):
    """큰 픽 카드: '예측' 라벨, 선택(색), 확률, 배당."""
    h = 150
    d.rounded_rectangle((x, y, x + w, y + h), radius=26, fill=CARD, outline=LINE, width=2)
    d.text((x + 30, y + 22), label, font=ko(24, "SemiBold"), fill=INK3)
    f, _ = _fit(d, pick, ko, 58, w - 360)
    d.text((x + 30, y + 56), pick, font=f, fill=tone(pick))
    pt = f"{prob}"
    d.text((x + w - 30 - d.textlength(pt, font=en(56)), y + 40), pt, font=en(56), fill=INK)
    if odds:
        ot = f"배당 {odds}"
        d.text((x + w - 30 - d.textlength(ot, font=ko(24, "SemiBold")), y + 108), ot, font=ko(24, "SemiBold"), fill=INK3)


# ───────── 페이지별 카드 ─────────
def match(path: Path, *, kicker: str, home: str, away: str, pick: str, prob: str, odds: str, extras: list[str], foot: str):
    if not OK:
        return False
    im = _base().copy()
    d = ImageDraw.Draw(im)
    d.text((64, 140), _ellipsis(d, kicker, ko(28, "Bold"), 1072), font=ko(28, "Bold"), fill=HOT)
    title = f"{home}  vs  {away}"
    f, size = _fit(d, title, ko, 66, 1072, 40)
    d.text((64, 184), title, font=f, fill=INK)
    if pick:
        _pick_card(d, 64, 290, 1072, "예측", pick, prob, odds)
    x = 64
    for e in extras[:3]:
        if x > 900:
            break
        x = _pill(d, x, 466, e, ko(26, "Bold"), tone(e)) + 12
    _footer(d, foot)
    _save(im, path)
    return True


def listing(path: Path, *, kicker: str, title: str, rows: list[tuple[str, str, str]], foot: str, sub: str = ""):
    """회차·리포트·리그 카드: 제목 + 최대 3줄(왼쪽 글, 가운데 선택, 오른쪽 숫자)."""
    if not OK:
        return False
    im = _base().copy()
    d = ImageDraw.Draw(im)
    d.text((64, 140), _ellipsis(d, kicker, ko(28, "Bold"), 1072), font=ko(28, "Bold"), fill=HOT)
    f, _ = _fit(d, title, ko, 64, 1072, 40)
    d.text((64, 182), title, font=f, fill=INK)
    y = 276
    if sub:
        d.text((64, 268), _ellipsis(d, sub, ko(26, "SemiBold"), 1072), font=ko(26, "SemiBold"), fill=INK2)
        y = 318
    for left, mid, right in rows[:3]:
        d.rounded_rectangle((64, y, W - 64, y + 70), radius=18, fill=CARD, outline=LINE, width=2)
        rf = en(30)
        rw = d.textlength(right, font=rf) if right else 0
        mf = ko(28, "Bold")
        mw = d.textlength(mid, font=mf) if mid else 0
        d.text((88, y + 18), _ellipsis(d, left, ko(28, "Bold"), 1072 - 80 - rw - mw - 60), font=ko(28, "Bold"), fill=INK)
        if mid:
            d.text((W - 88 - rw - 28 - mw, y + 18), mid, font=mf, fill=tone(mid))
        if right:
            d.text((W - 88 - rw, y + 16), right, font=rf, fill=INK)
        y += 82
    _footer(d, foot)
    _save(im, path)
    return True


def team(path: Path, *, kicker: str, name: str, rank: str, record: str, form: list[str], foot: str):
    if not OK:
        return False
    im = _base().copy()
    d = ImageDraw.Draw(im)
    d.text((64, 140), _ellipsis(d, kicker, ko(28, "Bold"), 1072), font=ko(28, "Bold"), fill=HOT)
    f, _ = _fit(d, name, ko, 76, 1072, 44)
    d.text((64, 182), name, font=f, fill=INK)
    x = 64
    if rank:
        x = _pill(d, x, 296, rank, ko(30, "ExtraBold"), INK, bg=(40, 33, 12), border=(120, 95, 20)) + 14
    if record:
        _pill(d, x, 296, record, ko(30, "Bold"), INK2)
    if form:
        d.text((64, 392), "최근 경기", font=ko(24, "SemiBold"), fill=INK3)
        x = 64
        for c in form[:10]:
            col = {"W": (30, 70, 52), "L": (78, 32, 42), "D": (78, 64, 20)}[c]
            fg = {"W": POS, "L": NEG, "D": DRAW}[c]
            d.rounded_rectangle((x, 430, x + 64, 494), radius=14, fill=col)
            t = {"W": "승", "L": "패", "D": "무"}[c]
            d.text((x + 32 - d.textlength(t, font=ko(30)) / 2, 444), t, font=ko(30), fill=fg)
            x += 76
    _footer(d, foot)
    _save(im, path)
    return True


def default(path: Path):
    if not OK:
        return False
    im = _base().copy()
    d = ImageDraw.Draw(im)
    d.text((64, 170), "데이터와 수학으로, 분석을 똑똑하게", font=ko(30, "Bold"), fill=HOT)
    d.text((64, 222), "베트맨 프로토 승부식", font=ko(76), fill=INK)
    d.text((64, 314), "매일 분석", font=ko(76), fill=INK)
    x = 64
    for t in ("적중 확률", "전략별 조합", "역배 · 핸디 · 언오버", "리그 순위"):
        x = _pill(d, x, 440, t, ko(26, "Bold"), INK2) + 12
    _footer(d, "해외 배당 기준 확률 · 매일 오후 7시 다음 구매일 분석")
    _save(im, path)
    return True


def icon(path: Path, size: int, *, maskable: bool = False, bg=BG):
    """홈 화면 아이콘. maskable 은 둥글게 잘려도 로고가 남도록 여백을 넉넉히 둔다."""
    if not OK:
        return False
    im = Image.new("RGB", (size, size), bg)
    s = int(size * (0.56 if maskable else 0.78))
    _logo(im, (size - s) // 2, (size - s) // 2, s)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "PNG", optimize=True)
    return True
