"""Threads 자동 게시(선택). THREADS_TOKEN 이 있을 때만 올린다(THREADS_USER_ID 는 없으면 토큰으로 알아낸다).

하루 두 번:
  - 밤 22:00 (night)   : 다음 구매일 분석 공개 — "내일 08시 발매" (22:00 실행이 다음 구매일 리포트를 미리 만든다)
  - 아침 07:00 (morning): 같은 구매일, 발매 1시간 전 — 밤 글에 없던 다른 경기로
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
    if h >= 21 or h < 3:
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


def _key(l: dict) -> str:
    return f"{l['kickoff'][:16]}|{l['home']}|{l['away']}"


def _take(pool: list[dict], n: int, used: set[str]) -> list[dict]:
    out = []
    for l in pool:
        k = _key(l)
        if k in used:
            continue
        used.add(k)
        out.append(l)
        if len(out) >= n:
            break
    return out


def compose(rep: dict, slot: str = "night", exclude: set[str] | None = None) -> tuple[str, list[str]]:
    """(글, 이 글에 쓴 경기 키). 아침 글은 exclude(밤 글에 쓴 경기)를 빼고 다른 경기로 채운다."""
    site = config.SITE_URL.replace("https://xn--sr3bw9dq7a9xy85g.kr", "https://스포츠분석.kr")
    n = rep["stats"]["matches"]
    used: set[str] = set(exclude or ())
    tops = list(rep.get("top_picks") or [])
    if slot == "night":
        head = f"🌙 {_day(rep)} 프로토 승부식 분석 공개\n내일 08시 발매 · {n}경기 분석"
        base = _take(([rep["top_pick"]] if rep.get("top_pick") else []) + tops, 1, used)
        more = _take(tops, 3, used)
        more_t = "🎯 적중 확률 높은 경기"
    else:
        head = f"☀️ {_day(rep)} 프로토 승부식\n08시 발매 시작 · 어젯밤과 다른 경기"
        # 밤 글에 없던 경기 중에서: 적중 확률 높은 경기 → 핸디캡·언더오버 추천 순으로
        pool = sorted(tops + list(rep.get("handi_picks") or []) + list(rep.get("ou_picks") or []), key=lambda l: -l["p"])
        base = _take(pool, 1, used)
        more = _take(pool, 3, used)
        more_t = "🎯 다른 추천 경기"
    parts = [head]
    if base:
        t = base[0]
        parts.append(f"📌 {'기준 경기' if slot == 'night' else '오늘의 추천'}\n{t['home']} vs {t['away']}\n→ {_pick(t)} ({t['p'] * 100:.0f}%, 배당 {t['odds']:.2f})")
    if more:
        parts.append(more_t + "\n" + "\n".join(f"· {x['home']} vs {x['away']} → {_pick(x)} ({x['p'] * 100:.0f}%)" for x in more))
    ups = _take(list(rep.get("upsets") or []), 2, used)
    if ups:
        parts.append("🔄 역배 후보\n" + "\n".join(f"· {u['home']} vs {u['away']} → {_pick(u)} (배당 {u['odds']:.2f})" for u in ups))
    c = {k: len(v) for k, v in (rep.get("combos") or {}).items()}
    parts.append(f"조합: 안정형 {c.get('safe', 0)} · 밸런스형 {c.get('balanced', 0)} · 공격형 {c.get('aggressive', 0)} · 역배 {c.get('upset', 0)} · 로또 {c.get('lotto', 0)}")
    tail = f"전체 분석 👉 {site}\n만 19세 이상 · 체육진흥투표권은 베트맨 공식 채널에서만"
    # 500자 제한: 뒤쪽 목록부터 줄인다(맨 끝 링크·고지는 반드시 남긴다)
    while len("\n\n".join(parts + [tail])) > LIMIT and len(parts) > 1:
        lines = parts[-1].split("\n")
        if len(lines) > 2:
            parts[-1] = "\n".join(lines[:-1])
        else:
            parts.pop()
    text = "\n\n".join(parts + [tail])
    shown = [_key(l) for l in base + more + ups if l["home"] in text]
    return text, shown


def post_daily(dry: bool = False, slot: str | None = None) -> bool:
    slot = slot or slot_now()
    # 밤 게시는 다음 구매일(22시 기준 내일, 실행이 늦어 23시를 넘겨도 같은 날), 아침 게시는 오늘 구매일
    from datetime import timedelta
    day = (config.now_kst() + timedelta(hours=3)).strftime("%Y-%m-%d") if slot == "night" else config.today_kst()
    rep = read_json(config.REPORTS / f"{day}.json")
    st = read_json(STATE, {}) or {}
    if dry:
        if not rep:
            print("리포트가 없습니다.")
            return False
        night, keys = compose(rep, "night")
        print("===== 밤 22:00 =====\n" + night)
        print("\n===== 아침 07:00 =====\n" + compose(rep, "morning", set(keys))[0])
        return False
    uid, token = os.getenv("THREADS_USER_ID", "").strip(), os.getenv("THREADS_TOKEN", "").strip()
    token = "".join(token.split()).strip('"\'')  # 복사할 때 붙은 공백·줄바꿈·따옴표 제거
    if not token or not slot:
        return False
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
        used = (st.get("used") or {}).get(day)
        if slot == "morning" and used is None:
            used = compose(rep, "night")[1]  # 밤 글 기록이 없으면 밤 글이 골랐을 경기를 다시 계산해 뺀다
        text, shown = compose(rep, slot, set(used or []) if slot == "morning" else None)
        r = http("POST", f"{API}/{uid}/threads", params={"media_type": "TEXT", "text": text, "access_token": token}, retries=2)
        cid = r.json()["id"]
        time.sleep(5)
        http("POST", f"{API}/{uid}/threads_publish", params={"creation_id": cid, "access_token": token}, retries=2)
        posted = (st.get("posted") or [])[-30:] + [key]
        used_all = {d: v for d, v in (st.get("used") or {}).items() if d >= day}  # 지난 날짜 기록은 버린다
        if slot == "night":
            used_all[day] = shown
        write_json(STATE, {"posted": posted, "last": day, "used": used_all})
        log.info("Threads 게시 완료(%s)", key)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Threads 게시 실패: %s", type(e).__name__)
        return False
