"""Threads 자동 게시(선택). THREADS_TOKEN 이 있을 때만 올린다(THREADS_USER_ID 는 없으면 토큰으로 알아낸다).

하루 두 번, 카드 이미지 묶음(캐러셀)으로:
  - 밤 22:00 (night)   : 다음 구매일 — 적중 확률 높은 경기 · 역배 후보 · 공격형 · 로또폴더 · 사이트 주소
  - 아침 07:00 (morning): 같은 구매일, 밤 글에 없던 다른 경기·조합으로
카드마다 일부 경기를 가린다(적중·역배·공격형 2개, 로또폴더 4개). 가린 경기는 사이트에서만 보인다. 배당은 베트맨(구매) 배당.

순서(워크플로):
  1) prepare : 카드 이미지를 data/threads/ 에 만들고 게시 대기 정보를 저장 → 커밋되면 사이트(/threads/)로 배포
  2) post    : 이미지 주소가 열릴 때까지 기다렸다가 캐러셀로 게시 → 게시 기록 저장(다시 커밋)
같은 구매일·같은 시간대에는 한 번만. 그 밖의 시각(수동 실행 포함)에는 아무것도 하지 않는다.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta

from . import config
from .util import http, read_json, write_json

log = logging.getLogger("engine.threads")
API = "https://graph.threads.net/v1.0"
STATE = config.STATE / "threads.json"
IMG_DIR = config.DATA / "threads"
WEEK = "월화수목금토일"
KEEP_DAYS = 3


def slot_now() -> str | None:
    h = config.now_kst().hour
    if h >= 21 or h < 3:
        return "night"
    if 5 <= h < 11:
        return "morning"
    return None


def day_for(slot: str) -> str:
    """밤 게시는 다음 구매일(22시 기준 내일, 실행이 늦어 23시를 넘겨도 같은 날), 아침 게시는 오늘 구매일."""
    if slot == "night":
        return (config.now_kst() + timedelta(hours=3)).strftime("%Y-%m-%d")
    return config.today_kst()


def caption(rep: dict, slot: str) -> str:
    """글 본문은 태그만. 그날 나온 리그를 태그로 붙인다."""
    tags = ["#프로토", "#승부식", "#프로토분석", "#스포츠토토", "#베트맨", "#스포츠분석"]
    leagues = []
    for m in rep.get("markets") or []:
        lg = str(m.get("league") or "").replace(" ", "")
        if lg and lg not in leagues:
            leagues.append(lg)
    tags += ["#" + lg for lg in leagues[:5]]
    tags += ["#만19세이상"]
    return " ".join(dict.fromkeys(tags))


def _prune() -> None:
    if not IMG_DIR.exists():
        return
    cut = (date.fromisoformat(config.today_kst()) - timedelta(days=KEEP_DAYS)).isoformat()
    for p in IMG_DIR.glob("*.jpg"):
        if p.name[:10] < cut:
            p.unlink(missing_ok=True)


def prepare(slot: str | None = None, force: bool = False) -> bool:
    """카드 이미지를 만들고 게시 대기 정보를 저장한다(토큰이 없으면 만들지 않는다)."""
    slot = slot or os.getenv("THREADS_SLOT", "").strip() or slot_now()
    if not slot or not (os.getenv("THREADS_TOKEN", "").strip() or force):
        return False
    day = day_for(slot)
    st = read_json(STATE, {}) or {}
    if f"{day}:{slot}" in (st.get("posted") or []):
        return False
    rep = read_json(config.REPORTS / f"{day}.json")
    if not rep or not rep.get("stats", {}).get("matches"):
        log.info("Threads: %s 리포트가 없어 건너뜀", day)
        return False
    from . import threads_cards as TC
    exclude = set((st.get("used") or {}).get(day) or []) if slot == "morning" else set()
    if slot == "morning" and not exclude:
        exclude = set(TC.build(rep, "night")[1])  # 밤 기록이 없으면 밤에 골랐을 경기를 다시 계산해 뺀다
    cards, shown = TC.build(rep, slot, exclude)
    _prune()
    paths = TC.render(cards, IMG_DIR, f"{day}-{slot}")
    st["pending"] = {"day": day, "slot": slot, "files": [p.name for p in paths], "used": shown, "text": caption(rep, slot)}
    write_json(STATE, st)
    log.info("Threads 카드 %d장 준비(%s %s)", len(paths), day, slot)
    return True


def _token() -> str:
    return "".join(os.getenv("THREADS_TOKEN", "").split()).strip('"\'')  # 복사할 때 붙은 공백·줄바꿈·따옴표 제거


def _wait_live(urls: list[str], minutes: int = 10) -> bool:
    """사이트 배포가 끝나 이미지가 열릴 때까지 기다린다."""
    end = time.time() + minutes * 60
    while time.time() < end:
        try:
            if all(http("GET", u, retries=1, timeout=20).headers.get("content-type", "").startswith("image") for u in urls):
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(20)
    return False


def post() -> bool:
    st = read_json(STATE, {}) or {}
    pend = st.get("pending")
    token = _token()
    if not pend or not token:
        return False
    key = f"{pend['day']}:{pend['slot']}"
    if key in (st.get("posted") or []):
        return False
    uid = os.getenv("THREADS_USER_ID", "").strip()
    if not uid.isdigit():
        try:
            uid = str(http("GET", f"{API}/me", params={"fields": "id", "access_token": token}, retries=2).json()["id"])
        except Exception as e:  # noqa: BLE001
            log.warning("Threads 사용자 ID 확인 실패(토큰을 다시 확인): %s", type(e).__name__)
            return False
    urls = [f"{config.SITE_URL}/threads/{f}" for f in pend["files"]]
    if not _wait_live(urls):
        log.warning("Threads: 카드 이미지가 사이트에 아직 없음(배포 지연) — 게시하지 않음")
        return False
    try:
        kids = []
        for u in urls[:20]:
            r = http("POST", f"{API}/{uid}/threads", params={"media_type": "IMAGE", "image_url": u, "is_carousel_item": "true", "access_token": token}, retries=2)
            kids.append(r.json()["id"])
        r = http("POST", f"{API}/{uid}/threads", params={"media_type": "CAROUSEL", "children": ",".join(kids), "text": pend["text"], "access_token": token}, retries=2)
        cid = r.json()["id"]
        time.sleep(30)  # 이미지 처리 시간
        http("POST", f"{API}/{uid}/threads_publish", params={"creation_id": cid, "access_token": token}, retries=3)
    except Exception as e:  # noqa: BLE001
        log.warning("Threads 게시 실패: %s", type(e).__name__)
        return False
    used = {d: v for d, v in (st.get("used") or {}).items() if d >= pend["day"]}
    if pend["slot"] == "night":
        used[pend["day"]] = pend["used"]
    st.update(posted=(st.get("posted") or [])[-30:] + [key], used=used, last=pend["day"])
    st.pop("pending", None)
    write_json(STATE, st)
    log.info("Threads 게시 완료(%s, 카드 %d장)", key, len(kids))
    return True


def post_daily() -> bool:
    """준비 + 게시를 한 번에(이미지가 이미 배포돼 있을 때만 게시됨)."""
    return prepare() and post()


def draft(out: str | None = None) -> bool:
    """올리지 않고 오늘 기준 밤·아침 카드 초안과 글을 만든다."""
    from pathlib import Path

    from . import threads_cards as TC
    rep = read_json(config.REPORTS / f"{config.today_kst()}.json")
    if not rep:
        print("리포트가 없습니다.")
        return False
    d = Path(out or (config.ROOT / ".draft"))
    cards, shown = TC.build(rep, "night")
    TC.render(cards, d, "night")
    cards2, _ = TC.build(rep, "morning", set(shown))
    TC.render(cards2, d, "morning")
    print(caption(rep, "night"), "\n\n", caption(rep, "morning"), "\n\n카드:", d)
    return True
