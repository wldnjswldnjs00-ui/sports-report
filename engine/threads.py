"""Threads 자동 게시(선택). THREADS_TOKEN 이 있을 때만 올린다(THREADS_USER_ID 는 없으면 토큰으로 알아낸다).

하루 두 번, 카드 이미지 묶음(캐러셀)으로:
  - 저녁 19:00 (night)  : 다음 구매일 — 적중 확률 높은 경기 · 역배 후보 · 공격형 · 로또폴더 · 사이트 주소
  - 아침 07:00 (morning): 같은 구매일, 밤 글에 없던 다른 경기·조합으로
카드마다 일부 경기를 가린다(적중·역배·공격형 2개, 로또폴더 4개). 가린 경기는 사이트에서만 보인다. 배당은 베트맨(구매) 배당.

순서(워크플로):
  1) prepare : 카드 이미지를 data/threads/ 에 만들고 게시 대기 정보를 저장 → 커밋되면 사이트(/threads/)로 배포
  2) post    : 이미지 주소가 열릴 때까지 기다렸다가 캐러셀로 게시 → 게시 기록 저장(다시 커밋)
같은 구매일·같은 시간대에는 한 번만. 그 밖의 시각(수동 실행 포함)에는 아무것도 하지 않는다.
"""
from __future__ import annotations

import html
import logging
import re
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
    """저녁 글(19:00, 늦으면 새벽 3시까지)·아침 글(07:00, 늦으면 정오까지). 예비 실행이 늦게 돌아도 그 시간대 글로 올라간다."""
    h = config.now_kst().hour
    if h >= 17 or h < 3:
        return "night"
    if 6 <= h < 12:
        return "morning"
    return None


def day_for(slot: str) -> str:
    """저녁 게시는 다음 구매일(17시~새벽 3시 어느 때 돌아도 같은 날), 아침 게시는 오늘 구매일."""
    if slot == "night":
        return (config.now_kst() + timedelta(hours=7)).strftime("%Y-%m-%d")
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
    if (not rep or not rep.get("stats", {}).get("matches")) and os.getenv("THREADS_COLLECT"):
        # 다시 올리기 실행: 정해진 시각에 베트맨이 막혀 경기가 없었으면 지금 다시 받아 온다
        try:
            from . import pipeline
            pipeline.collect(day)
        except Exception as e:  # noqa: BLE001
            log.warning("Threads: 경기 다시 받기 실패 %s", str(e)[:200])
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
    """Worker(KV)에 보관·자동 연장되는 최신 토큰. 못 받으면 GitHub Secrets 토큰(공백·따옴표 제거)."""
    from . import threads_token
    return threads_token.current()


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


class _Skip(Exception):
    """이미 올라가 있어 게시 과정을 건너뛴다."""


def post() -> bool:
    st = read_json(STATE, {}) or {}
    pend = st.get("pending")
    token = _token()
    if not pend or not token:
        return False
    key = f"{pend['day']}:{pend['slot']}"
    if key in (st.get("posted") or []):
        return False
    if pend["slot"] != (os.getenv("THREADS_SLOT", "").strip() or slot_now()) or pend["day"] != day_for(pend["slot"]):
        log.info("Threads: 지난 시간대 카드(%s)라 올리지 않음", key)
        return False
    # 토큰 확인: Worker 토큰이 안 되면 GitHub Secrets 토큰으로 한 번 더(둘 중 되는 것을 쓴다)
    from . import threads_token
    cands = list(dict.fromkeys([token, threads_token._seed()]))
    me, errs = None, []
    for tk in [c for c in cands if c]:
        try:
            me = str(http("GET", f"{API}/me", params={"fields": "id", "access_token": tk}, retries=2).json()["id"])
            token = tk
            break
        except Exception as e:  # noqa: BLE001
            r = getattr(e, "response", None)
            errs.append(f"{getattr(r, 'status_code', '?')} {(r.text if r is not None else str(e))[:200]}".replace(tk, "***"))
    uid = os.getenv("THREADS_USER_ID", "").strip()
    if not me:
        log.warning("Threads 토큰 확인 실패(토큰 만료·권한 문제일 수 있음): %s", " | ".join(errs))
        if not uid.isdigit():
            return False
        token = cands[0]  # 확인만 막혔을 수 있으니 사용자 ID 로 게시는 시도한다
    if not uid.isdigit():
        uid = me
    urls = [f"{config.SITE_URL}/threads/{f}" for f in pend["files"]]
    if not _wait_live(urls):
        log.warning("Threads: 카드 이미지가 사이트에 아직 없음(배포 지연) — 게시하지 않음")
        return False
    if _already_up(uid, token, pend["text"]):
        log.info("Threads: 이미 올라가 있어 기록만 남김(%s)", key)
        kids = []
    else:
        kids = None

    def _err(e) -> str:
        """쓰레드가 돌려준 오류 내용(토큰은 빼고)."""
        r = getattr(e, "response", None)
        body = (r.text if r is not None else str(e))[:400]
        return body.replace(token, "***")

    def _ready(cid: str, wait: int = 120) -> bool:
        """컨테이너가 FINISHED 될 때까지 기다린다(이미지 처리)."""
        end = time.time() + wait
        while time.time() < end:
            try:
                st_ = http("GET", f"{API}/{cid}", params={"fields": "status,error_message", "access_token": token}, retries=1).json()
                if st_.get("status") == "FINISHED":
                    return True
                if st_.get("status") in ("ERROR", "EXPIRED"):
                    log.warning("Threads 컨테이너 오류: %s", st_.get("error_message"))
                    return False
            except Exception:  # noqa: BLE001
                pass
            time.sleep(5)
        return False

    step = "이미지 등록"
    try:
        if kids is not None:
            raise _Skip
        kids = []
        for u in urls[:20]:
            r = http("POST", f"{API}/{uid}/threads", params={"media_type": "IMAGE", "image_url": u, "is_carousel_item": "true", "access_token": token}, retries=2)
            kids.append(r.json()["id"])
        step = "이미지 처리 대기"
        for k in kids:
            if not _ready(k):
                log.warning("Threads: 이미지 처리가 끝나지 않음(%s)", k)
                return False
        step = "묶음 만들기"
        r = http("POST", f"{API}/{uid}/threads", params={"media_type": "CAROUSEL", "children": ",".join(kids), "text": pend["text"], "access_token": token}, retries=2)
        cid = r.json()["id"]
        step = "묶음 처리 대기"
        _ready(cid, 180)
        step = "게시"
        http("POST", f"{API}/{uid}/threads_publish", params={"creation_id": cid, "access_token": token}, retries=3)
    except _Skip:
        pass
    except Exception as e:  # noqa: BLE001
        log.warning("Threads 게시 실패(%s): %s", step, _err(e))
        return False
    used = {d: v for d, v in (st.get("used") or {}).items() if d >= pend["day"]}
    if pend["slot"] == "night":
        used[pend["day"]] = pend["used"]
    st.update(posted=(st.get("posted") or [])[-30:] + [key], used=used, last=pend["day"])
    st.pop("pending", None)
    write_json(STATE, st)
    log.info("Threads 게시 완료(%s, 카드 %d장)", key, len(kids))
    return True


def _auth() -> tuple[str, str] | None:
    """(사용자 ID, 토큰). Worker 토큰이 안 되면 Secrets 토큰으로."""
    from . import threads_token
    token = _token()
    cands = [c for c in dict.fromkeys([token, threads_token._seed()]) if c]
    uid = os.getenv("THREADS_USER_ID", "").strip()
    for tk in cands:
        try:
            me = str(http("GET", f"{API}/me", params={"fields": "id", "access_token": tk}, retries=2).json()["id"])
            return (uid if uid.isdigit() else me), tk
        except Exception:  # noqa: BLE001
            continue
    return (uid, cands[0]) if uid.isdigit() and cands else None


def post_knowhow() -> bool:
    """준비해 둔 노하우 카드 묶음을 게시(밤 22:00, 빠지면 23:05)."""
    st = read_json(STATE, {}) or {}
    pend = st.get("pending_kh")
    if not pend or st.get("kh_day") == pend["day"] or pend["day"] != config.today_kst():
        return False
    au = _auth()
    if not au:
        log.warning("Threads 노하우: 토큰 확인 실패")
        return False
    uid, token = au
    urls = [f"{config.SITE_URL}/threads/{f}" for f in pend["files"]]
    if not _wait_live(urls):
        log.warning("Threads 노하우: 카드 이미지가 사이트에 아직 없음 — 다음 실행에 맡김")
        return False
    if not _publish(uid, token, urls, pend["text"], "노하우"):
        return False
    st = read_json(STATE, {}) or {}
    st["kh"] = [x for x in (st.get("kh") or []) if x != pend["slug"]][-1000:] + [pend["slug"]]
    st["kh_day"] = pend["day"]
    st.pop("pending_kh", None)
    write_json(STATE, st)
    log.info("Threads 노하우 게시 완료: %s", pend["title"])
    return True


# ───────────── 전날 결과(하루 한 번, 13:00 · 빠지면 18:00) ─────────────
def result_stats(day: str) -> dict | None:
    """전날(구매일) 픽 결과. 박빙(확률 55% 미만)은 픽이 아니라 세지 않는다. 결과가 덜 나왔으면 None."""
    from .analysis.grading import is_pick
    from .analysis.combos import STRATEGIES
    rep = read_json(config.REPORTS / f"{day}.json")
    if not rep:
        return None
    outs = rep.get("outcomes") or {}
    picks = [m for m in rep.get("markets") or [] if is_pick(m.get("analysis")) and not m.get("preview")]
    done = [m for m in picks if outs.get(m["id"]) not in (None, "VOID")]
    if not picks or len(done) < max(3, int(len(picks) * 0.9)):
        return None  # 아직 끝나지 않은 경기가 많다
    hits = [m for m in done if outs[m["id"]] == m["analysis"]["pick"]]
    hi = [m for m in done if m["odds"].get(m["analysis"]["pick"], 0) >= 1.5]
    # 최근 30일(이 날 포함)
    n30 = h30 = 0
    cut = (date.fromisoformat(day) - timedelta(days=29)).isoformat()
    for f in sorted(config.REPORTS.glob("*.json")):
        if not (cut <= f.stem <= day):
            continue
        r = read_json(f) or {}
        o = r.get("outcomes") or {}
        for m in r.get("markets") or []:
            if is_pick(m.get("analysis")) and not m.get("preview") and o.get(m["id"]) not in (None, "VOID"):
                n30 += 1
                h30 += int(o[m["id"]] == m["analysis"]["pick"])
    # 어제의 한 장면: 적중한 조합 중 배당이 가장 큰 것, 없으면 적중한 픽 중 배당이 가장 큰 것
    hl = None
    best = None
    for key, cs in (rep.get("combos") or {}).items():
        for c in cs or []:
            if c.get("result") == "win" and (best is None or c["total_odds"] > best[1]["total_odds"]):
                best = (key, c)
    if best and best[1]["total_odds"] >= 2:
        k, c = best
        hl = f"{STRATEGIES.get(k, {}).get('label', '조합')} {c['size']}폴더 ×{c['total_odds']:.2f} 적중"
    elif hits:
        m = max(hits, key=lambda m: m["odds"].get(m["analysis"]["pick"], 0))
        k = m["analysis"]["pick"]
        lab = {"H": "승", "D": "무", "A": "패", "O": "오버", "U": "언더"}.get(k, k)
        team = m["away"] if k == "A" else m["home"]
        if m["market"] == "HANDICAP":
            lab = "핸디" + lab
        hl = f"{team} {lab} {m['odds'][k]:.2f} 적중" if m["market"] != "OU" else f"{m['home']} vs {m['away']} {lab} {m['odds'][k]:.2f} 적중"
    lab = {"H": "승", "D": "무", "A": "패", "O": "오버", "U": "언더"}
    rows = []
    # 배당 1.50 이상 픽을 경기 시작 순으로(낮은 배당만 보여 주지 않게). 모자라면 1.30 이상까지
    show = [m for m in done if m["odds"].get(m["analysis"]["pick"], 0) >= 1.5]
    if len(show) < 3:
        show = [m for m in done if m["odds"].get(m["analysis"]["pick"], 0) >= 1.3]
    # 적중한 역배(픽·조합 다리 모두에서): 베트맨 배당이 상대보다 높은 쪽을 맞힌 것은 꼭 넣는다
    from .analysis.combos import _is_dog
    by_id = {m["id"]: m for m in rep.get("markets") or []}
    dogs = {}
    for m in done:
        k = m["analysis"]["pick"]
        if outs[m["id"]] == k and _is_dog(m, m["analysis"], k):
            dogs[(m["id"], k)] = m
    for cs in (rep.get("combos") or {}).values():
        for c in cs or []:
            for lg in c.get("legs") or []:
                m = by_id.get(lg.get("market_id"))
                k = lg.get("outcome")
                if m and outs.get(m["id"]) == k and _is_dog(m, {}, k):
                    dogs.setdefault((m["id"], k), m)
    sel = [(m, k, True) for (_, k), m in dogs.items()]
    seen = set(dogs)
    sel += [(m, m["analysis"]["pick"], False) for m in sorted(show, key=lambda m: str(m.get("kickoff")))
            if (m["id"], m["analysis"]["pick"]) not in seen]
    sel = sorted(sel[:7], key=lambda x: str(x[0].get("kickoff")))
    for m, k, dog in sel:
        pk = lab.get(k, k)
        if m["market"] == "HANDICAP":
            pk = "핸디" + pk + (f" {m['line']:+g}" if k == "H" and m.get("line") is not None else "")
        if m["market"] == "OU" and m.get("line") is not None:
            pk = f"{pk} {m['line']:g}"
        ko = str(m.get("kickoff") or "")
        rows.append({"home": m["home"], "away": m["away"], "pick": pk, "odds": m["odds"].get(k, 0), "hit": outs[m["id"]] == k, "dog": dog,
                     "meta": f"{m['league']} · {int(ko[5:7])}/{int(ko[8:10])} {ko[11:16]}" if len(ko) >= 16 else m["league"]})
    crow = []
    for key, cs in (rep.get("combos") or {}).items():
        fin = [c for c in cs or [] if c.get("result") in ("win", "lose")]
        if fin:
            wins = [c for c in fin if c["result"] == "win"]
            crow.append((STRATEGIES.get(key, {}).get("label", key), len(wins), len(fin),
                         max((c.get("total_odds") or 0 for c in wins), default=0)))
    return {"picks": rows, "combos": crow,
            "day": day, "n": len(done), "hit": len(hits), "rate": len(hits) / len(done),
            "hi_n": len(hi), "hi_hit": sum(1 for m in hi if outs[m["id"]] == m["analysis"]["pick"]),
            "n30": n30, "r30": (h30 / n30) if n30 else 0, "highlight": hl}


def prepare_result(force: bool = False) -> bool:
    if not (os.getenv("THREADS_TOKEN", "").strip() or force):
        return False
    day = (date.fromisoformat(config.today_kst()) - timedelta(days=1)).isoformat()
    st = read_json(STATE, {}) or {}
    if f"{day}:result" in (st.get("posted") or []):
        return False
    res = result_stats(day)
    if not res:
        log.info("Threads 결과: %s 결과가 아직 덜 나와 다음 실행에 맡김", day)
        return False
    from . import threads_cards as TC
    _prune()
    cards = [TC.card_result(day, res)] + ([TC.card_result_picks(day, res["picks"])] if res["picks"] else [])
    hit_combos = [c for c in res["combos"] if c[1] > 0]  # 적중이 나온 전략만
    if hit_combos:
        cards.append(TC.card_result_combos(day, hit_combos, res.get("highlight")))
    cards.append(TC.card_link("오늘 분석도", "이미 올라와 있습니다"))
    paths = TC.render(cards, IMG_DIR, f"{day}-result")
    st["pending_result"] = {"day": day, "files": [p.name for p in paths],
                            "text": "어제 결과 · 매일 같은 기준으로 모든 픽을 기록합니다\n#프로토 #승부식 #프로토분석 #스포츠토토 #베트맨 #스포츠분석 #만19세이상"}
    write_json(STATE, st)
    log.info("Threads 결과 카드 준비(%s): %d/%d, 30일 %.0f%%", day, res["hit"], res["n"], res["r30"] * 100)
    return True


def post_result() -> bool:
    st = read_json(STATE, {}) or {}
    pend = st.get("pending_result")
    if not pend or pend["day"] != (date.fromisoformat(config.today_kst()) - timedelta(days=1)).isoformat():
        return False  # 어제 것이 아니면(지난 카드) 올리지 않는다
    key = f"{pend['day']}:result"
    if key in (st.get("posted") or []):
        return False
    au = _auth()
    if not au:
        log.warning("Threads 결과: 토큰 확인 실패")
        return False
    uid, token = au
    urls = [f"{config.SITE_URL}/threads/{f}" for f in pend["files"]]
    if not _wait_live(urls):
        log.warning("Threads 결과: 카드 이미지가 사이트에 아직 없음 — 다음 실행에 맡김")
        return False
    if not _publish(uid, token, urls, pend["text"], "결과"):
        return False
    st = read_json(STATE, {}) or {}
    st["posted"] = (st.get("posted") or [])[-30:] + [key]
    st.pop("pending_result", None)
    write_json(STATE, st)
    log.info("Threads 결과 게시 완료(%s)", pend["day"])
    return True


def _same_post(a, b) -> bool:
    """같은 글인가: 첫 줄(제목)로 비교한다. 쓰레드는 해시태그를 바꿔 돌려줄 수 있어 전체 글은 다를 수 있다.
    제목 없이 태그만 있는 글(분석 글)은 전체 글로 비교."""
    a, b = (a or "").strip(), (b or "").strip()
    fa, fb = a.split("\n")[0].strip(), b.split("\n")[0].strip()
    if fb and not fb.startswith("#"):
        return fa == fb
    return a == b


def _already_up(uid: str, token: str, text: str, hours: int = 2) -> bool:
    """같은 글이 최근 몇 시간 안에 이미 올라가 있는가(게시는 됐는데 기록 저장이 실패한 경우 두 번 올리지 않게)."""
    try:
        data = http("GET", f"{API}/{uid}/threads", params={"fields": "text,timestamp", "limit": 10, "access_token": token},
                    retries=1).json().get("data") or []
    except Exception:  # noqa: BLE001 - 확인이 안 되면 그냥 올린다
        return False
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for d in data:
        try:
            ts = datetime.strptime(d["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        except Exception:  # noqa: BLE001
            continue
        if _same_post(d.get("text"), text) and (now - ts).total_seconds() < hours * 3600:
            return True
    return False


def _publish(uid: str, token: str, urls: list[str], text: str, what: str, check_dup: bool = True) -> bool:
    """이미지 한 장이면 단독, 여러 장이면 묶음(캐러셀)으로 게시."""
    if check_dup and _already_up(uid, token, text):
        log.info("Threads %s: 이미 올라가 있어 기록만 남김", what)
        return True
    def ready(cid, wait=150):
        end = time.time() + wait
        while time.time() < end:
            try:
                st_ = http("GET", f"{API}/{cid}", params={"fields": "status,error_message", "access_token": token}, retries=1).json()
                if st_.get("status") == "FINISHED":
                    return True
                if st_.get("status") in ("ERROR", "EXPIRED"):
                    log.warning("Threads %s 컨테이너 오류: %s", what, st_.get("error_message"))
                    return False
            except Exception:  # noqa: BLE001
                pass
            time.sleep(5)
        return False
    step = "이미지 등록"
    try:
        if len(urls) == 1:
            cid = http("POST", f"{API}/{uid}/threads", params={"media_type": "IMAGE", "image_url": urls[0], "text": text, "access_token": token}, retries=2).json()["id"]
        else:
            kids = [http("POST", f"{API}/{uid}/threads", params={"media_type": "IMAGE", "image_url": u, "is_carousel_item": "true", "access_token": token}, retries=2).json()["id"] for u in urls[:20]]
            step = "이미지 처리 대기"
            if not all(ready(k) for k in kids):
                return False
            step = "묶음 만들기"
            cid = http("POST", f"{API}/{uid}/threads", params={"media_type": "CAROUSEL", "children": ",".join(kids), "text": text, "access_token": token}, retries=2).json()["id"]
        step = "처리 대기"
        ready(cid, 180)
        step = "게시"
        http("POST", f"{API}/{uid}/threads_publish", params={"creation_id": cid, "access_token": token}, retries=3)
        return True
    except Exception as e:  # noqa: BLE001
        rr = getattr(e, "response", None)
        log.warning("Threads %s 게시 실패(%s): %s", what, step, ((rr.text if rr is not None else str(e))[:300]).replace(token, "***"))
        return False


def _kh_all() -> list[dict]:
    from .site import knowhow as KH
    out = []
    try:
        from .site import knowhow_weekly as KW
        out += KW.load()
    except Exception:  # noqa: BLE001
        pass
    return out + KH.build_all()


def _kh_parts(body: str) -> tuple[list[tuple[list[str], list[list[str]]]], list[str]]:
    """글 본문 HTML 에서 (표 목록, 문단 목록)을 뽑는다."""
    clean = lambda x: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).strip()
    tables = []
    for t in re.findall(r"<table.*?</table>", body, flags=re.S):
        head = [clean(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", t, flags=re.S)]
        rows = [[clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)] for tr in re.findall(r"<tr>(.*?)</tr>", t, flags=re.S)]
        rows = [r for r in rows if r]
        if head and rows:
            tables.append((head, rows))
    paras = [clean(p) for p in re.findall(r"<p>(.*?)</p>", body, flags=re.S)]
    return tables, [p for p in paras if len(p) > 20]



# ── 쓰레드 노하우: 관심이 큰 주제부터, 넓은 주제 → 종목 → 인기 리그 순. 제목은 쓰레드용으로 짧고 궁금하게 ──
_KH_COMMON = ["underdogs", "favorites-by-odds", "folders", "odds-movement", "streaks", "bankroll", "handicap",
              "over-under", "soccer-draws", "home-advantage", "compare-favorites", "compare-goals", "compare-draws",
              "time-of-day", "payout-rate", "nba-mlb-margins"]
_KH_HOOK = {
    "underdogs": "역배, 진짜 몇 번에 한 번 터질까",
    "favorites-by-odds": "1점대 정배, 정말 믿어도 될까",
    "folders": "폴더 하나 더 붙이면 적중률은 얼마나 달라질까",
    "odds-movement": "배당이 내려간 쪽, 정말 이겼을까",
    "streaks": "연승 중인 팀, 다음 경기도 이길까",
    "bankroll": "잘 고르는 사람도 연속으로 빗나간다: 금액 나누는 기준",
    "handicap": "핸디 받은 팀, 생각보다 잘 버틸까",
    "over-under": "오버냐 언더냐, 기록이 가리키는 쪽",
    "soccer-draws": "축구 무승부, 언제 노려볼 만할까",
    "home-advantage": "홈팀은 정말 유리할까: 종목별로 보면",
    "compare-favorites": "정배가 가장 잘 버티는 축구 리그는",
    "compare-goals": "골 제일 많이 나는 축구 리그는",
    "compare-draws": "무승부 제일 잘 나오는 축구 리그는",
    "time-of-day": "새벽 경기와 저녁 경기, 정배 기록이 다를까",
    "payout-rate": "배당 안에 숨은 몫, 폴더를 늘리면 커진다",
    "nba-mlb-margins": "NBA·MLB 기준점, 10시즌 기록으로 보면",
}
_KH_TOPIC = ["upset", "fav", "hc", "ou", "home", "league", "o25", "draws", "favfd", "goals", "fd"]  # 리그·종목 글 안에서의 주제 순서
_KH_TOPIC_HOOK = {
    "upset": "{n} 역배, 몇 경기에 한 번 터질까", "fav": "{n} 정배, 진짜 믿어도 될까",
    "hc": "{n} 핸디 받은 팀, 얼마나 버틸까", "ou": "{n} 오버냐 언더냐, 기록으로 보면",
    "home": "{n} 홈팀은 얼마나 유리할까", "league": "{n}, 기록으로 보면 이런 리그",
    "o25": "{n} 오버 2.5, 배당이 맞았을까", "draws": "{n} 무승부는 언제 나올까",
    "goals": "{n} 한 경기 골은 몇 개", "favfd": "{n} 정배, 여러 시즌 기록으로 보면", "fd": "{n}, 숫자로 보면 이런 리그",
}
_KH_SPORT = {"soccer": "축구", "baseball": "야구", "basketball": "농구", "volleyball": "배구"}
_KH_POPULAR = ["KBO", "잉글랜드 프리미어리그", "NBA", "MLB", "K리그1", "UEFA 챔피언스리그", "스페인 라리가",
               "이탈리아 세리에A", "독일 분데스리가", "KBL", "NPB", "축구 월드컵", "일본 J1리그", "프랑스 리그1"]
_KH_SHORT = {"잉글랜드 프리미어리그": "프리미어리그", "UEFA 챔피언스리그": "챔피언스리그", "스페인 라리가": "라리가",
             "이탈리아 세리에A": "세리에A", "독일 분데스리가": "분데스리가", "미국 메이저리그사커": "MLS",
             "남자축구 국제친선경기": "A매치 친선전", "UEFA 네이션스리그": "네이션스리그", "일본 J1리그": "J리그",
             "UEFA 유로파리그": "유로파리그", "프랑스 리그1": "리그1", "잉글랜드 챔피언십": "EFL 챔피언십",
             "FIVB 남자배구 네이션스리그": "남자배구 VNL", "FIVB 여자배구 네이션스리그": "여자배구 VNL"}


def _kh_topic(a: dict) -> str:
    sl = a["slug"]
    return "favfd" if sl.startswith("fav-fd-") else sl.split("-")[0]


# 리그별 시즌 달(베트맨 기록이 짧아도 시즌 중인지 알 수 있게). 키는 리그 이름에 들어 있는 말.
_KH_MONTHS = [
    (("잉글랜드", "스페인", "이탈리아", "독일", "프랑스", "네덜란드", "포르투갈", "벨기에", "튀르키예", "그리스",
      "스코틀랜드", "챔피언스리그", "유로파"), (8, 9, 10, 11, 12, 1, 2, 3, 4, 5)),
    (("K리그", "J1", "J2"), (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)),
    (("메이저리그사커",), (2, 3, 4, 5, 6, 7, 8, 9, 10, 11)),
    (("KBO", "MLB", "NPB"), (3, 4, 5, 6, 7, 8, 9, 10)),
    (("NBA", "KBL", "WKBL"), (10, 11, 12, 1, 2, 3, 4, 5, 6)),
    (("KOVO",), (10, 11, 12, 1, 2, 3, 4)),
    (("네이션스리그", "FIVB"), (5, 6, 7)),
]
_KH_SPORT_MONTHS = {"baseball": (3, 4, 5, 6, 7, 8, 9, 10), "basketball": (10, 11, 12, 1, 2, 3, 4, 5, 6),
                    "volleyball": (10, 11, 12, 1, 2, 3, 4, 5, 6, 7), "soccer": tuple(range(1, 13))}


def _kh_season(days: int = 21):
    """지금 시즌 중인 리그·종목: 최근 3주 베트맨에 올라온 것 + 시즌 달 표. 실패해도 달 표만으로 판단."""
    lg, sp = set(), set()
    today = date.fromisoformat(config.today_kst())
    cut = (today - timedelta(days=days)).isoformat()
    try:
        for f in config.REPORTS.glob("*.json"):
            if f.stem >= cut:
                for m in (read_json(f) or {}).get("markets") or []:
                    lg.add(m.get("league"))
                    sp.add(m.get("sport"))
    except Exception:  # noqa: BLE001 - 순서만 바뀔 뿐, 실패해도 게시는 계속
        pass
    mo = today.month
    sp |= {k for k, ms in _KH_SPORT_MONTHS.items() if mo in ms}
    return lg, sp, mo


def _kh_live(league: str, season) -> bool:
    lgs, _, mo = season
    if league in lgs:
        return True
    for keys, ms in _KH_MONTHS:
        if any(k in league for k in keys):
            # 네이션스리그는 축구(가을 A매치)와 배구(여름)가 이름이 겹친다 → 베트맨 기록이 있으면 위에서 이미 참
            return mo in ms
    return False


def _kh_order(lst: list[dict], season) -> list[dict]:
    """게시 순서. 공통 글 → (시즌 중 종목 + 시즌 중 인기 리그) → 시즌 중 다른 리그 → 쉬는 종목·리그.
    묶음 안에서는 종목/리그를 돌아가며 한 편씩, 주제도 묶음마다 시작점을 달리해 같은 리그·같은 주제가 이어지지 않게."""
    common = sorted([a for a in lst if a["slug"] in _KH_COMMON], key=lambda a: _KH_COMMON.index(a["slug"]))
    common += [a for a in lst if a["slug"] not in _KH_COMMON and a.get("cat") in ("공통", "리그 비교")]
    groups: dict[tuple, list[dict]] = {}
    for a in lst:
        if a in common:
            continue
        if a.get("cat") == "종목별":
            spt = a["slug"].rsplit("-", 1)[-1]
            band = 0 if spt in season[1] else 2
            key = (band, 0, list(_KH_SPORT).index(spt) if spt in _KH_SPORT else 9, "s:" + spt)
        else:
            lg = a.get("league") or ""
            live = _kh_live(lg, season)
            pop = lg in _KH_POPULAR
            band = (0 if pop else 1) if live else 2
            key = (band, 1 if pop else 2, _KH_POPULAR.index(lg) if pop else -(a.get("games") or 0), "l:" + lg)
        groups.setdefault(key, []).append(a)
    out = list(common)
    for band in (0, 1, 2):
        ks = sorted(k for k in groups if k[0] == band)
        # 종목 글과 리그 글을 번갈아(종목 하나, 리그 하나 …)
        sk = [k for k in ks if k[3].startswith("s:")]
        lk = [k for k in ks if k[3].startswith("l:")]
        mixed = []
        while sk or lk:
            if sk:
                mixed.append(sk.pop(0))
            mixed += lk[:2]
            lk = lk[2:]
        qs = []
        for gi, k in enumerate(mixed):
            items = sorted(groups[k], key=lambda a: _KH_TOPIC.index(_kh_topic(a)) if _kh_topic(a) in _KH_TOPIC else 99)
            r = gi % max(1, len(items))
            qs.append(items[r:] + items[:r])  # 묶음마다 다른 주제부터
        while any(qs):
            for q in qs:
                if q:
                    out.append(q.pop(0))
    return out


def _kh_hook(a: dict) -> str:
    sl = a["slug"]
    if sl in _KH_HOOK:
        return _KH_HOOK[sl]
    tp = _kh_topic(a)
    if a.get("cat") == "종목별":
        n = _KH_SPORT.get(sl.rsplit("-", 1)[-1], "")
    else:
        n = _KH_SHORT.get(a.get("league") or "", a.get("league") or "")
    if n and tp in _KH_TOPIC_HOOK:
        return _KH_TOPIC_HOOK[tp].format(n=n)
    return a["title"]


def _kh_lead(lead: str) -> str:
    """표지 설명은 첫 문장만, 사이트 안내 문장은 뺀다."""
    ss = [x for x in re.split(r"(?<=[.!?])\s+", lead or "") if x and not re.search(r"메뉴|화면|페이지|자동으로|다시 계산", x)]
    return ss[0] if ss else ""


def _kh_sections(body: str):
    """(소제목, 표 머리, 표 행) 목록과 문단 목록. 표는 바로 앞 소제목과 짝을 짓는다."""
    clean = lambda x: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).strip()
    secs, cur = [], ""
    for m in re.finditer(r"<h2>(.*?)</h2>|(<table.*?</table>)", body, flags=re.S):
        if m.group(1) is not None:
            cur = clean(m.group(1))
            continue
        t = m.group(2)
        head = [clean(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", t, flags=re.S)]
        rows = [[clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)] for tr in re.findall(r"<tr>(.*?)</tr>", t, flags=re.S)]
        rows = [r for r in rows if r]
        if head and rows:
            secs.append((cur, head, rows))
    paras = [clean(p) for p in re.findall(r"<p>(.*?)</p>", body, flags=re.S)]
    return secs, [p for p in paras if len(p) > 20]


def _kh_stat_rows(head: list[str], rows: list[list[str]]):
    """표에서 '이름 → 핵심 숫자' 4줄만. 핵심 열은 실제 적중·오버·무승부·비율 같은 결과 열."""
    if len(head) < 2:
        return None
    pref = ("실제", "적중", "오버", "무승부", "홈 승", "비율", "버틴", "값")
    col = next((i for i, h in enumerate(head) if i and any(p in h for p in pref)), len(head) - 1)
    good = [r for r in rows if len(r) > col and r[col] and r[0]]
    if len(good) < 2:
        return None
    extra = ""
    if len({r[0] for r in good}) < len(good):
        # '종목 × 배당 구간' 처럼 같은 이름이 여러 줄인 표: 모든 이름에 공통으로 있는 구간 하나로 맞춰 비교한다
        best = None
        for j in range(1, len(head)):
            if j == col:
                continue
            cnt = {}
            for r in good:
                if len(r) > j:
                    cnt.setdefault(r[j], set()).add(r[0])
            for v, names in cnt.items():
                # 우연히 두어 개만 겹치는 값(점수 등)은 쓰지 않는다: 이름의 절반 이상·3개 이상에 있는 구간만
                if len(names) >= max(3, (len({r[0] for r in good}) + 1) // 2) and (best is None or len(names) > best[2]):
                    best = (j, v, len(names))
        if best:
            j, v, _ = best
            seen, pick = set(), []
            for r in good:
                if len(r) > j and r[j] == v and r[0] not in seen:
                    seen.add(r[0])
                    pick.append(r)
            good, extra = pick, f"{head[j]} {v} · "
        else:  # 공통 구간이 없으면 둘째 칸(리그 등)을 이름으로
            good = [[r[1]] + r[1:] for r in good]
            head = [head[1]] + head[1:]
    if len({r[0] for r in good}) < len(good):  # 그래도 겹치면 처음 것만
        seen = set()
        good = [r for r in good if not (r[0] in seen or seen.add(r[0]))]
    if len(good) < 2:
        return None
    if len(good) > 4:  # 많으면 고르게 4줄(처음·끝 포함)
        idx = sorted({0, len(good) // 3, 2 * len(good) // 3, len(good) - 1})
        good = [good[i] for i in idx]
    cap = "" if head[0] in ("항목", "구분") or head[col] == "값" else f"{extra}{head[0]}별 {head[col]}"
    return cap, [(r[0], re.sub(r"\s*\(.*?\)", "", r[col])) for r in good]  # 괄호 속 표본 수는 빼고 숫자만


def _kh_sentences(paras: list[str]) -> list[str]:
    """마무리 문단에서 짧은 문장 1~2개씩 묶어 카드 한 장 분량으로."""
    sents = []
    for p in paras[-2:]:
        sents += [x.strip() for x in re.split(r"(?<=[.!?])\s+", p) if len(x.strip()) > 8
                  and not re.search(r"메뉴|화면|페이지|발매되면|자동으로|다시 계산", x)]  # 사이트 안내 문장은 빼고 내용만
    out, cur = [], ""
    for x in sents:
        if len(cur) + len(x) > 70 and cur:
            out.append(cur)
            cur = x
        else:
            cur = (cur + " " + x).strip()
    if cur:
        out.append(cur)
    return [o for o in out if len(o) <= 120]


def prepare_knowhow(force: bool = False) -> bool:
    """노하우 글 한 편을 카드 묶음(표지 → 핵심 표 → 정리 → 사이트)으로 만든다. 하루 한 편, 주간 리포트가 있으면 그것부터."""
    if not (os.getenv("THREADS_TOKEN", "").strip() or force):
        return False
    st = read_json(STATE, {}) or {}
    today = config.today_kst()
    if st.get("kh_day") == today:
        return False
    lst = [x for x in _kh_all() if x.get("cat") != "주간 리포트"]  # 노하우 탭 글만
    if not lst:
        return False
    done = st.get("kh") or []
    lst = _kh_order(lst, _kh_season())
    pick = [x for x in lst if x["slug"] not in done][:1]
    if not pick:  # 한 바퀴 다 돌면 가장 오래전에 올린 글부터 다시
        order = {s_: i for i, s_ in enumerate(done)}
        pick = sorted(lst, key=lambda x: order.get(x["slug"], -1))[:1]
    if not pick:
        return False
    a = pick[0]
    cards, text = _kh_cards(a, today)
    from . import threads_cards as TC
    _prune()
    paths = TC.render(cards, IMG_DIR, f"{today}-kh")
    st["pending_kh"] = {"day": today, "slug": a["slug"], "title": a["title"], "files": [p_.name for p_ in paths], "text": text}
    write_json(STATE, st)
    log.info("Threads 노하우 카드 %d장 준비: %s", len(paths), a["title"])
    return True


def _kh_cards(a: dict, today: str):
    """노하우 글 한 편 → (카드 HTML 목록, 게시 글)."""
    secs, paras = _kh_sections(a.get("body") or "")
    from . import threads_cards as TC
    big = None
    m = re.search(r"\d+(?:\.\d+)?%", a.get("lead") or "")
    if m:
        big = m.group(0)
    hook = _kh_hook(a)
    cards = [TC.card_kh_cover(today, a.get("cat") or "", hook, _kh_lead(a.get("lead") or ""), big)]
    for heading, head, rows in secs[:2]:
        st_ = _kh_stat_rows(head, rows)
        if st_:
            cards.append(TC.card_kh_stats(today, heading or a["title"], st_[0], st_[1]))
    for k, t in enumerate(_kh_sentences(paras)[:2], 1):
        cards.append(TC.card_kh_quote(today, t, "정리" if k == 1 else ""))
    cards.append(TC.card_link("전체 글과 다른 노하우는", "여기서 무료로"))
    tags = ["#프로토", "#프로토분석", "#스포츠분석"] + ([f"#{a['league'].replace(' ', '')}"] if a.get("league") else [])
    return cards, f"{hook}\n{' '.join(tags)} #만19세이상"


def redo_knowhow_prepare() -> bool:
    """오늘 올린 노하우 글을 고친 카드로 다시 만든다(이미지 주소를 새로 해 캐시된 옛 이미지가 쓰이지 않게)."""
    st = read_json(STATE, {}) or {}
    today = config.today_kst()
    if (st.get("kh_redo") or {}).get("day") == today:  # 이미 준비(또는 완료)됨: 지우기 기록을 지키려고 다시 만들지 않는다
        return False
    if st.get("kh_day") != today or not st.get("kh"):
        log.info("노하우 다시 올리기: 오늘 올린 글이 없거나 이미 다시 올림")
        return False
    slug = st["kh"][-1]
    a = next((x for x in _kh_all() if x["slug"] == slug), None)
    if not a:
        return False
    cards, text = _kh_cards(a, today)
    from . import threads_cards as TC
    paths = TC.render(cards, IMG_DIR, f"{today}-khr")
    st["kh_redo"] = {"day": today, "slug": slug, "files": [p_.name for p_ in paths], "text": text}
    write_json(STATE, st)
    log.info("노하우 다시 올리기 카드 %d장 준비: %s", len(paths), slug)
    return True


def redo_knowhow_post() -> bool:
    """옛 글을 지우고(지우기가 안 되면 아무것도 안 함) 고친 카드로 다시 올린다."""
    st = read_json(STATE, {}) or {}
    rd = st.get("kh_redo")
    if not rd or rd.get("done") or rd["day"] != config.today_kst():
        return False
    au = _auth()
    if not au:
        log.warning("노하우 다시 올리기: 토큰 확인 실패")
        return False
    uid, token = au
    urls = [f"{config.SITE_URL}/threads/{f}" for f in rd["files"]]
    if not _wait_live(urls):
        log.warning("노하우 다시 올리기: 새 카드가 사이트에 아직 없음")
        return False
    if not rd.get("deleted"):
        try:
            data = http("GET", f"{API}/{uid}/threads", params={"fields": "id,text,timestamp", "limit": 25, "access_token": token},
                        retries=2).json().get("data") or []
        except Exception as e:  # noqa: BLE001
            log.warning("노하우 다시 올리기: 글 목록 확인 실패 %s", str(e)[:200].replace(token, "***"))
            return False
        from datetime import datetime, timezone
        def recent(ts):  # 최근 30시간 안에 올린 글만
            try:
                return (datetime.now(timezone.utc) - datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")).total_seconds() < 30 * 3600
            except Exception:  # noqa: BLE001
                return False
        olds = [d for d in data if _same_post(d.get("text"), rd["text"]) and recent(str(d.get("timestamp", "")))]
        if not olds:
            log.warning("노하우 다시 올리기: 지울 옛 글을 찾지 못함 — 두 번 올라가지 않게 멈춤. 최근 글: %s",
                        [(str(d.get("timestamp"))[:16], (d.get("text") or "")[:30]) for d in data[:6]])
            return False
        for d in olds:
            try:
                http("DELETE", f"{API}/{d['id']}", params={"access_token": token}, retries=2)
            except Exception as e:  # noqa: BLE001
                r = getattr(e, "response", None)
                log.warning("노하우 다시 올리기: 옛 글 지우기 실패(권한 threads_delete 필요할 수 있음) %s",
                            ((r.text if r is not None else str(e))[:300]).replace(token, "***"))
                return False
        rd["deleted"] = True
        st["kh_redo"] = rd
        write_json(STATE, st)
        log.info("노하우 다시 올리기: 옛 글 %d개 지움", len(olds))
    if not _publish(uid, token, urls, rd["text"], "노하우(다시)", check_dup=False):
        return False
    st = read_json(STATE, {}) or {}
    st["kh_redo"] = {**rd, "done": True}
    write_json(STATE, st)
    log.info("노하우 다시 올리기 완료: %s", rd["slug"])
    return True


def due(kind: str) -> bool:
    """이 글이 지금 올라가 있어야 하는데 아직 안 올라갔는가(바로 다시 올릴지 판단).
    kind: analysis(아침·저녁 분석) · result(전날 결과) · kh(노하우). 토큰이 없으면 언제나 False."""
    if not os.getenv("THREADS_TOKEN", "").strip():
        return False
    st = read_json(STATE, {}) or {}
    posted = st.get("posted") or []
    today = config.today_kst()
    if kind == "analysis":
        slot = slot_now()
        if not slot:
            return False
        day = day_for(slot)
        return f"{day}:{slot}" not in posted  # 경기가 없으면(베트맨 막힘) 다시 올리기에서 경기를 다시 받아 온다
    if kind == "result":
        day = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
        if f"{day}:result" in posted:
            return False
        return bool(st.get("pending_result")) or result_stats(day) is not None  # 결과가 덜 나온 날은 13·18시가 이어받음
    if kind == "kh-redo":
        rd = st.get("kh_redo") or {}
        return rd.get("day") == today and not rd.get("done")
    if kind == "kh":
        return st.get("kh_day") != today and config.now_kst().hour >= 15
    return False


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
