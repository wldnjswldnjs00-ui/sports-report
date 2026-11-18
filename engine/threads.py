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


def post() -> bool:
    st = read_json(STATE, {}) or {}
    pend = st.get("pending")
    token = _token()
    if not pend or not token:
        return False
    key = f"{pend['day']}:{pend['slot']}"
    if key in (st.get("posted") or []):
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
    if not pend or st.get("kh_day") == pend["day"]:
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
    hi = [m for m in done if m["analysis"]["pick_prob"] >= 0.65]
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
    for m in sorted(done, key=lambda m: -m["analysis"]["pick_prob"])[:7]:
        k = m["analysis"]["pick"]
        pk = lab.get(k, k)
        if m["market"] == "HANDICAP":
            pk = "핸디" + pk + (f" {m['line']:+g}" if k == "H" and m.get("line") is not None else "")
        if m["market"] == "OU" and m.get("line") is not None:
            pk = f"{pk} {m['line']:g}"
        ko = str(m.get("kickoff") or "")
        rows.append({"home": m["home"], "away": m["away"], "pick": pk, "odds": m["odds"].get(k, 0), "hit": outs[m["id"]] == k,
                     "meta": f"{m['league']} · {int(ko[5:7])}/{int(ko[8:10])} {ko[11:16]}" if len(ko) >= 16 else m["league"]})
    crow = []
    for key, cs in (rep.get("combos") or {}).items():
        fin = [c for c in cs or [] if c.get("result") in ("win", "lose")]
        if fin:
            crow.append((STRATEGIES.get(key, {}).get("label", key), sum(1 for c in fin if c["result"] == "win"), len(fin)))
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
    cards = [TC.card_result(day, res), TC.card_result_picks(day, res["picks"])]
    if res["combos"]:
        cards.append(TC.card_result_combos(day, res["combos"], res.get("highlight")))
    cards.append(TC.card_link("어제 픽 전체와", "30일 기록은 여기서"))
    paths = TC.render(cards, IMG_DIR, f"{day}-result")
    st["pending_result"] = {"day": day, "files": [p.name for p in paths],
                            "text": "어제 결과 · 매일 같은 기준으로 모든 픽을 기록합니다\n#프로토 #승부식 #프로토분석 #스포츠토토 #베트맨 #스포츠분석 #만19세이상"}
    write_json(STATE, st)
    log.info("Threads 결과 카드 준비(%s): %d/%d, 30일 %.0f%%", day, res["hit"], res["n"], res["r30"] * 100)
    return True


def post_result() -> bool:
    st = read_json(STATE, {}) or {}
    pend = st.get("pending_result")
    if not pend:
        return False
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


def _publish(uid: str, token: str, urls: list[str], text: str, what: str) -> bool:
    """이미지 한 장이면 단독, 여러 장이면 묶음(캐러셀)으로 게시."""
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


def prepare_knowhow(force: bool = False) -> bool:
    """노하우 글 한 편을 카드 묶음(표지 → 핵심 표 → 정리 → 사이트)으로 만든다. 하루 한 편, 주간 리포트가 있으면 그것부터."""
    if not (os.getenv("THREADS_TOKEN", "").strip() or force):
        return False
    st = read_json(STATE, {}) or {}
    today = config.today_kst()
    if st.get("kh_day") == today:
        return False
    lst = _kh_all()
    if not lst:
        return False
    done = st.get("kh") or []
    weekly = [x for x in lst if x.get("cat") == "주간 리포트" and x["slug"] not in done]
    rest = [x for x in lst if x.get("cat") != "주간 리포트" and x["slug"] not in done]
    pick = (weekly or rest or [])[:1]
    if not pick:
        order = {s_: i for i, s_ in enumerate(done)}
        pick = sorted([x for x in lst if x.get("cat") != "주간 리포트"], key=lambda x: order.get(x["slug"], -1))[:1]
    if not pick:
        return False
    a = pick[0]
    tables, paras = _kh_parts(a.get("body") or "")
    from . import threads_cards as TC
    big = None
    m = re.search(r"\d+(?:\.\d+)?%", a.get("lead") or "")
    if m:
        big = m.group(0)
    cards = [TC.card_kh_cover(today, a.get("cat") or "", a["title"], a.get("lead") or "", big)]
    for head, rows in tables[:2]:
        cards.append(TC.card_kh_table(today, "기록으로 보면", head[:5], [r[:5] for r in rows[:7]]))
    if paras:
        cards.append(TC.card_kh_text(today, "정리하면", paras[-2:] if len(paras) > 2 else paras[:2]))
    cards.append(TC.card_link("전체 글과 다른 노하우는", "여기서 무료로"))
    _prune()
    paths = TC.render(cards, IMG_DIR, f"{today}-kh")
    tags = ["#프로토", "#프로토분석", "#스포츠분석"] + ([f"#{a['league'].replace(' ', '')}"] if a.get("league") else [])
    st["pending_kh"] = {"day": today, "slug": a["slug"], "title": a["title"], "files": [p_.name for p_ in paths],
                        "text": f"{a['title']}\n{' '.join(tags)} #만19세이상"}
    write_json(STATE, st)
    log.info("Threads 노하우 카드 %d장 준비: %s", len(paths), a["title"])
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
