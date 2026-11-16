"""Threads 자동 게시(선택). THREADS_TOKEN 이 있을 때만 올린다(THREADS_USER_ID 는 없으면 토큰으로 알아낸다).

하루 두 번:
  - 밤 23:05 (night)  : 다음 구매일 분석 공개 — "내일 08시 발매"
  - 아침 07:00 (morning): 발매 1시간 전 — "오늘 08시 발매"
같은 구매일·같은 시간대에는 한 번만 올린다. 그 밖의 시각(수동 실행 포함)에는 올리지 않는다.
Threads API: 글 컨테이너 생성 → 게시 두 단계. 글자 수 제한(500자) 안에서 자른다.
배당은 사이트 화면과 같이 베트맨(구매) 배당으로 적는다.
"""
from __future__ import annotations

import logging
import os
import time

from . import config
from .util import http, read_json, write_json

log = logging.getLogger("engine.threads")
API = "https://graph.threads.net/v1.0"
STATE = config.STATE / "threads.json"
LIMIT = 490
WEEK = "월화수목금토일"


def slot_now() -> str | None:
    h = config.now_kst().hour
    if h >= 22 or h < 3:
        return "night"
    if 5 <= h < 11:
        return "morning"
    return None


def _pick(l: dict) -> str:
    """'덴버 너게츠 승' / '보스턴 핸디승 -8.5' / '언더 212.5' 처럼 짧게."""
    mk, k = l.get("market"), l.get("outcome")
    if mk == "OU":
        return f"{'오버' if k == 'O' else '언더'} {l.get('line'):g}" if l.get("line") is not None else ("오버" if k == "O" else "언더")
    if mk == "HANDICAP":
        line = l.get("line") or 0
        return f"{l['home']} 핸디승 {line:+g}" if k == "H" else f"{l['away']} 핸디승 {-line:+g}" if k == "A" else "핸디무"
    return f"{l['home']} 승" if k == "H" else f"{l['away']} 승" if k == "A" else "무승부"


def _day(rep: dict) -> str:
    from datetime import date
    d = date.fromisoformat(rep["date"])
    return f"{d.month}월 {d.day}일({WEEK[d.weekday()]})"


def compose(rep: dict, slot: str = "night") -> str:
    site = config.SITE_URL.replace("https://xn--sr3bw9dq7a9xy85g.kr", "https://스포츠분석.kr")
    n = rep["stats"]["matches"]
    head = (f"🌙 {_day(rep)} 프로토 승부식 분석 공개\n내일 08시 발매 · {n}경기 분석" if slot == "night"
            else f"☀️ {_day(rep)} 프로토 승부식\n08시 발매 시작 · {n}경기 분석")
    parts = [head]
    t = rep.get("top_pick")
    if t:
        parts.append(f"📌 기준 경기\n{t['home']} vs {t['away']}\n→ {_pick(t)} ({t['p'] * 100:.0f}%, 배당 {t['odds']:.2f})")
    tops = [x for x in (rep.get("top_picks") or []) if not t or x.get("market_id") != t.get("market_id")][:3]
    if tops:
        parts.append("🎯 적중 확률 높은 경기\n" + "\n".join(f"· {x['home']} vs {x['away']} → {_pick(x)} ({x['p'] * 100:.0f}%)" for x in tops))
    ups = (rep.get("upsets") or [])[:2]
    if ups:
        parts.append("🔄 역배 후보\n" + "\n".join(f"· {u['home']} vs {u['away']} → {_pick(u)} (배당 {u['odds']:.2f})" for u in ups))
    c = {k: len(v) for k, v in (rep.get("combos") or {}).items()}
    parts.append(f"조합: 안정형 {c.get('safe', 0)} · 밸런스형 {c.get('balanced', 0)} · 공격형 {c.get('aggressive', 0)} · 역배 {c.get('upset', 0)} · 로또 {c.get('lotto', 0)}")
    tail = f"전체 분석 👉 {site}\n만 19세 이상 · 체육진흥투표권은 베트맨 공식 채널에서만"
    # 500자 제한: 뒤쪽 목록부터 줄인다(맨 끝 링크·고지는 반드시 남긴다)
    while len("\n\n".join(parts + [tail])) > LIMIT and len(parts) > 1:
        last = parts[-1]
        lines = last.split("\n")
        if len(lines) > 2:
            parts[-1] = "\n".join(lines[:-1])
        else:
            parts.pop()
    return "\n\n".join(parts + [tail])


def post_daily(dry: bool = False, slot: str | None = None) -> bool:
    slot = slot or slot_now()
    day = config.today_kst()
    rep = read_json(config.REPORTS / f"{day}.json")
    if dry:
        print(compose(rep, slot or "night") if rep else "리포트가 없습니다.")
        return False
    uid, token = os.getenv("THREADS_USER_ID", "").strip(), os.getenv("THREADS_TOKEN", "").strip()
    token = "".join(token.split()).strip('"\'')  # 복사할 때 붙은 공백·줄바꿈·따옴표 제거
    if not token or not slot:
        return False
    st = read_json(STATE, {}) or {}
    key = f"{day}:{slot}"
    if key in (st.get("posted") or []):
        return False
    if not rep or not rep.get("stats", {}).get("matches"):
        return False
    if not uid.isdigit():
        # 사용자 ID 를 따로 넣지 않아도 토큰으로 알아낸다
        try:
            uid = str(http("GET", f"{API}/me", params={"fields": "id", "access_token": token}, retries=2).json()["id"])
        except Exception as e:  # noqa: BLE001
            log.warning("Threads 사용자 ID 확인 실패(토큰을 다시 확인): %s", type(e).__name__)
            return False
    try:
        r = http("POST", f"{API}/{uid}/threads", params={"media_type": "TEXT", "text": compose(rep, slot), "access_token": token}, retries=2)
        cid = r.json()["id"]
        time.sleep(5)
        http("POST", f"{API}/{uid}/threads_publish", params={"creation_id": cid, "access_token": token}, retries=2)
        posted = (st.get("posted") or [])[-30:] + [key]
        write_json(STATE, {"posted": posted, "last": day})
        log.info("Threads 게시 완료(%s)", key)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Threads 게시 실패: %s", type(e).__name__)
        return False
