"""구글 웹스토리(AMP Story): '오늘의 핵심 경기'를 매 빌드 자동으로 만든다.

구글 검색·디스커버의 스토리 칸에 뜰 수 있는 형식. 사람 손 없이 오늘 경기에서 골라 만든다.
- 표지 1장 + 핵심 경기 최대 5장(빅매치 우선, 확률 높은 순) + 마지막 장(사이트로 이동)
- AMP 규칙: 외부 스크립트는 AMP 것만, CSS 는 <style amp-custom> 안에, 이미지는 amp-img.
- 표지 이미지(세로 3:4, 960×1280)는 Pillow 로 그린다.
"""
from __future__ import annotations

import html
import logging
from pathlib import Path

log = logging.getLogger("engine.stories")

BOILER = ("<style amp-boilerplate>body{-webkit-animation:-amp-start 8s steps(1,end) 0s 1 normal both;-moz-animation:-amp-start 8s steps(1,end) 0s 1 normal both;"
          "-ms-animation:-amp-start 8s steps(1,end) 0s 1 normal both;animation:-amp-start 8s steps(1,end) 0s 1 normal both}@-webkit-keyframes -amp-start{from{visibility:hidden}"
          "to{visibility:visible}}@-moz-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}@-ms-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}"
          "@-o-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}@keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}</style>"
          "<noscript><style amp-boilerplate>body{-webkit-animation:none;-moz-animation:none;-ms-animation:none;animation:none}</style></noscript>")

CSS = """
amp-story{font-family:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:#eef0f7}
.bg{background:linear-gradient(160deg,#2a1530 0%,#0f1117 55%,#13203a 100%)}
.pad{padding:56px 28px 40px}
.brand{font-size:18px;font-weight:800;letter-spacing:-.01em}
.brand b{color:#ff3d7f;font-size:13px;margin-left:2px}
.kick{font-size:14px;font-weight:700;color:#ff8ab0;margin-top:22px}
.h1{font-size:38px;line-height:1.2;font-weight:800;margin-top:10px;letter-spacing:-.02em}
.sub{font-size:16px;color:#c2c7d6;margin-top:14px;line-height:1.5}
.lg{font-size:14px;color:#8a90a6;font-weight:700}
.teams{font-size:30px;line-height:1.25;font-weight:800;margin-top:10px;letter-spacing:-.02em}
.vs{font-size:16px;color:#8a90a6;font-weight:600;display:block;margin:6px 0}
.score{margin-top:26px;padding:18px;border-radius:18px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12)}
.score small{display:block;font-size:13px;color:#8a90a6;font-weight:700}
.score strong{display:block;font-size:44px;font-weight:800;margin-top:4px}
.pick{margin-top:14px;font-size:20px;font-weight:800}
.pos{color:#4ade80}.neg{color:#ff6b6b}.draw{color:#fbbf24}
.note{margin-top:16px;font-size:15px;color:#c2c7d6;line-height:1.55}
.foot{position:absolute;left:28px;right:28px;bottom:28px;font-size:12px;color:#8a90a6}
"""


def _e(s) -> str:
    return html.escape(str(s or ""), quote=True)


def _tone(label: str) -> str:
    import re
    m = re.search(r"([+\-−])\d", label)
    if m:
        return "pos" if m.group(1) == "+" else "neg"
    if "오버" in label:
        return "pos"
    if "언더" in label:
        return "neg"
    if "무" in label:
        return "draw"
    if "패" in label:
        return "neg"
    return "pos" if "승" in label else ""


def pick_games(matches: list[dict], is_hot, predict, is_pick, label, now_iso: str, k: int = 5) -> list[dict]:
    """시작 전 경기 중 추천이 있는 것: 빅매치 먼저, 그다음 확률 높은 순."""
    out = []
    for g in matches:
        if str(g.get("kickoff", ""))[:16] <= now_iso[:16]:
            continue
        m = g.get("main") or {}
        a = m.get("analysis") or {}
        if not is_pick(a):
            continue
        pd = predict(g)
        out.append({"g": g, "hot": is_hot(g), "p": a.get("pick_prob") or 0, "label": label(m, a.get("pick")), "pd": pd,
                    "odds": a.get("pick_odds")})
    out.sort(key=lambda x: (not x["hot"], -x["p"]))
    return out[:k]


def poster(path: Path, title: str, sub: str) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFilter
        from . import og
        W, H = 960, 1280
        im = Image.new("RGB", (W, H), og.BG)
        glow = Image.new("RGB", (W, H), og.BG)
        gd = ImageDraw.Draw(glow)
        gd.ellipse((-300, -300, 700, 600), fill=(80, 30, 62))
        gd.ellipse((400, 700, 1300, 1500), fill=(26, 44, 92))
        im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(160)), 0.9)
        d = ImageDraw.Draw(im)
        og._logo(im, 64, 70, 70)
        d.text((150, 74), "스포츠분석", font=og.dh(56), fill=og.INK)
        d.text((64, 520), title, font=og.ko(84), fill=og.INK)
        d.text((64, 640), sub, font=og.ko(40, "Bold"), fill=og.INK2)
        d.text((64, H - 110), "만 19세 이상 · 참고용 분석", font=og.ko(30, "Bold"), fill=og.INK3)
        path.parent.mkdir(parents=True, exist_ok=True)
        im.save(path, "JPEG", quality=86)
        return True
    except Exception:  # noqa: BLE001
        log.exception("웹스토리 표지 실패")
        return False


def render(site_url: str, site_name: str, items: list[dict], kdt, day_label: str, poster_url: str, logo_url: str, canonical: str) -> str:
    title = f"오늘의 프로토 핵심 경기 {len(items)}"
    pages = [f'''<amp-story-page id="cover" auto-advance-after="6s"><amp-story-grid-layer template="fill" class="bg"></amp-story-grid-layer>
<amp-story-grid-layer template="vertical" class="pad"><div class="brand">{_e(site_name)}<b>.kr</b></div>
<div class="kick">{_e(day_label)}</div><h1 class="h1">오늘의 프로토<br>핵심 경기 {len(items)}</h1>
<p class="sub">해외 배당과 과거 기록으로 계산한 예상 스코어와 확률입니다.</p><p class="foot">만 19세 이상 · 베트맨 공식 채널에서만 · 참고용 분석</p></amp-story-grid-layer></amp-story-page>''']
    for i, it in enumerate(items, 1):
        g = it["g"]
        pd = it["pd"]
        sc = f"{pd['h']} : {pd['a']}" if pd else "–"
        # 첫 문장('~ 예측')은 위 추천 줄과 겹치니 그다음 근거 문장을 쓴다
        sents = [x.strip().rstrip(".") for x in ((g.get("main") or {}).get("narrative") or "").split(". ") if x.strip()]
        rest = [x for x in sents[1:] if x and not x[0].isdigit()]  # 주어 없이 숫자로 시작하는 문장은 뺀다
        narr = ". ".join(rest[:2])[:120]
        narr = narr + "." if narr else ""
        pages.append(f'''<amp-story-page id="g{i}" auto-advance-after="8s"><amp-story-grid-layer template="fill" class="bg"></amp-story-grid-layer>
<amp-story-grid-layer template="vertical" class="pad"><div class="lg">{_e(g.get("league"))} · {_e(kdt(g["kickoff"]))}</div>
<div class="teams">{_e(g["home"])}<span class="vs">vs</span>{_e(g["away"])}</div>
<div class="score"><small>예상 스코어</small><strong>{_e(sc)}</strong></div>
<div class="pick"><span class="{_tone(it["label"])}">{_e(it["label"])}</span> · {it["p"] * 100:.0f}%</div>
<p class="note">{_e(narr)}</p></amp-story-grid-layer>
<amp-story-page-outlink layout="nodisplay"><a href="{_e(site_url + g["url"])}">경기 분석 보기</a></amp-story-page-outlink></amp-story-page>''')
    pages.append(f'''<amp-story-page id="end"><amp-story-grid-layer template="fill" class="bg"></amp-story-grid-layer>
<amp-story-grid-layer template="vertical" class="pad"><div class="brand">{_e(site_name)}<b>.kr</b></div>
<h2 class="h1">전체 경기 분석과<br>전략별 조합</h2><p class="sub">매일 자동으로 갱신됩니다. 결과도 매일 채점해 공개합니다.</p>
<p class="foot">만 19세 이상 · 베트맨 공식 채널에서만 · 참고용 분석</p></amp-story-grid-layer>
<amp-story-page-outlink layout="nodisplay"><a href="{_e(site_url)}/">오늘의 분석 보기</a></amp-story-page-outlink></amp-story-page>''')
    return f'''<!doctype html>
<html ⚡ lang="ko">
<head>
<meta charset="utf-8">
<title>{_e(title)} | {_e(site_name)}</title>
<link rel="canonical" href="{_e(canonical)}">
<meta name="viewport" content="width=device-width">
<meta name="description" content="{_e(day_label)} 베트맨 프로토 승부식 핵심 경기의 예상 스코어와 확률. 해외 배당과 과거 기록으로 계산합니다.">
<script async src="https://cdn.ampproject.org/v0.js"></script>
<script async custom-element="amp-story" src="https://cdn.ampproject.org/v0/amp-story-1.0.js"></script>
{BOILER}
<style amp-custom>{CSS}</style>
</head>
<body>
<amp-story standalone title="{_e(title)}" publisher="{_e(site_name)}" publisher-logo-src="{_e(logo_url)}" poster-portrait-src="{_e(poster_url)}">
{"".join(pages)}
</amp-story>
</body>
</html>
'''
