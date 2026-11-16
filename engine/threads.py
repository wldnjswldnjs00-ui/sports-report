"""Threads 자동 게시(선택). THREADS_USER_ID / THREADS_TOKEN 이 있을 때만 하루 한 번 올린다.

Threads API: 글 컨테이너 생성 → 게시 두 단계. 토큰(장기 60일)은 게시할 때마다 갱신을 시도한다.
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


def compose(rep: dict) -> str:
    lines = [f"{rep['date'][5:7]}월 {int(rep['date'][8:])}일 프로토 승부식 {rep['stats']['matches']}경기 분석"]
    t = rep.get("top_pick")
    if t:
        side = t["home"] if t["outcome"] == "H" else t["away"] if t["outcome"] == "A" else "무승부"
        lines.append(f"기준 경기: {t['home']} vs {t['away']} → {side} (추정 {t['p'] * 100:.0f}%, 배당 {t['odds']:.2f})")
    ups = rep.get("upsets") or []
    if ups:
        u = ups[0]
        lines.append(f"역배 후보: {u['home']} vs {u['away']} 배당 {u['odds']:.2f}")
    n = {k: len(v) for k, v in (rep.get("combos") or {}).items()}
    lines.append(f"안정형 {n.get('safe', 0)} · 밸런스형 {n.get('balanced', 0)} · 공격형 {n.get('aggressive', 0)} · 로또폴더 {n.get('lotto', 0)}")
    lines.append(f"전체 분석 {config.SITE_URL.replace('https://xn--sr3bw9dq7a9xy85g.kr', 'https://스포츠분석.kr')}")
    lines.append("만 19세 이상 · 체육진흥투표권은 베트맨 공식 채널에서만")
    return "\n".join(lines)[:480]


def post_daily() -> bool:
    uid, token = os.getenv("THREADS_USER_ID", "").strip(), os.getenv("THREADS_TOKEN", "").strip()
    if not uid or not token:
        return False
    day = config.today_kst()
    st = read_json(STATE, {}) or {}
    if st.get("last") == day:
        return False
    rep = read_json(config.REPORTS / f"{day}.json")
    if not rep or not rep.get("stats", {}).get("matches"):
        return False
    try:
        r = http("POST", f"{API}/{uid}/threads", params={"media_type": "TEXT", "text": compose(rep), "access_token": token}, retries=2)
        cid = r.json()["id"]
        time.sleep(5)
        http("POST", f"{API}/{uid}/threads_publish", params={"creation_id": cid, "access_token": token}, retries=2)
        write_json(STATE, {"last": day})
        log.info("Threads 게시 완료")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Threads 게시 실패: %s", type(e).__name__)
        return False
