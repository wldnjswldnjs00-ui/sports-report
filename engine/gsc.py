"""구글 서치 콘솔 자동화: 사이트맵 제출, 새 페이지 색인 요청, 색인 상태·검색 노출 기록.

구글은 IndexNow를 받지 않으므로 서비스 계정(GitHub Secret GSC_SA_JSON)으로 직접 알린다.
- 사이트맵: 매 실행마다 제출(구글이 바로 다시 읽어 간다).
- 색인 요청(Indexing API): 빅매치·고정 페이지·어제~내일 페이지 순, 하루 180개 이내, 같은 주소는 3일에 한 번.
- 색인 확인(URL Inspection): 하루 한 번 대표 주소 20개, 결과와 최근 7일 노출·클릭을 data/state/gsc.json 에 남긴다.
비밀 값이 없거나 구글이 거절해도 파이프라인은 그대로 계속된다.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import timedelta
from urllib.parse import quote, urlparse

from . import config
from .util import http, read_json

log = logging.getLogger("engine.gsc")
STATE = config.STATE / "gsc.json"
SCOPES = "https://www.googleapis.com/auth/webmasters https://www.googleapis.com/auth/indexing"
DAY_CAP = 180          # Indexing API 기본 한도 200/일
RESEND_DAYS = 3
INSPECT_N = 20


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _sa() -> dict | None:
    raw = (os.getenv("GSC_SA_JSON") or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw if raw.startswith("{") else base64.b64decode(raw).decode())
    except Exception as e:  # noqa: BLE001
        log.warning("GSC_SA_JSON 형식 확인 필요: %s", type(e).__name__)
        return None


def _sign(data: bytes, pem: str) -> bytes:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        return key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    except ImportError:
        pass
    fd, path = tempfile.mkstemp(suffix=".pem")
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(pem)
        return subprocess.run(["openssl", "dgst", "-sha256", "-sign", path], input=data,
                              capture_output=True, check=True).stdout
    finally:
        os.unlink(path)


def _token(sa: dict) -> str:
    now = int(time.time())
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claim = _b64(json.dumps({"iss": sa["client_email"], "scope": SCOPES, "aud": sa.get("token_uri") or "https://oauth2.googleapis.com/token",
                             "iat": now, "exp": now + 3600}).encode())
    msg = f"{head}.{claim}".encode()
    jwt = f"{head}.{claim}.{_b64(_sign(msg, sa['private_key']))}"
    r = http("POST", "https://oauth2.googleapis.com/token", data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt}, retries=3)
    return r.json()["access_token"]


def _properties(h: dict) -> list[str]:
    """서비스 계정이 접근할 수 있는 이 사이트의 속성. 도메인 속성 → 대표 주소 → www 순."""
    host = urlparse(config.SITE_URL).hostname or ""
    bare = host[4:] if host.startswith("www.") else host
    want = [f"sc-domain:{bare}", f"https://{bare}/", f"http://{bare}/", f"https://www.{bare}/", f"http://www.{bare}/"]
    try:
        have = {e["siteUrl"]: e.get("permissionLevel", "") for e in http("GET", "https://www.googleapis.com/webmasters/v3/sites", headers=h).json().get("siteEntry", [])}
    except Exception as e:  # noqa: BLE001
        log.warning("서치 콘솔 속성 조회 안 됨: %s", e)
        return []
    out = [w for w in want if w in have and have[w] != "siteUnverifiedUser"]
    if not out and have:
        log.info("서비스 계정이 볼 수 있는 속성: %s", list(have))
    return out


def _submit_sitemaps(h: dict, props: list[str], st: dict) -> None:
    sm = config.SITE_URL + "/sitemap.xml"
    done = {}
    for p in props:
        try:
            http("PUT", f"https://www.googleapis.com/webmasters/v3/sites/{quote(p, safe='')}/sitemaps/{quote(sm, safe='')}", headers=h, retries=2)
            done[p] = "ok"
        except Exception as e:  # noqa: BLE001
            done[p] = str(getattr(getattr(e, "response", None), "status_code", "") or type(e).__name__)
    st["sitemap"] = {"at": config.now_kst().isoformat(timespec="minutes"), "result": done}
    log.info("사이트맵 제출 %s", done)


def _publish(h: dict, st: dict) -> None:
    from .indexnow import recent_urls
    today = config.now_kst().strftime("%Y-%m-%d")
    sent: dict = st.setdefault("sent", {})
    cutoff = (config.now_kst() - timedelta(days=RESEND_DAYS)).strftime("%Y-%m-%d")
    for u in [u for u, d in sent.items() if d < (config.now_kst() - timedelta(days=30)).strftime("%Y-%m-%d")]:
        sent.pop(u)
    day = st.setdefault("day", {})
    if day.get("date") != today:
        day.clear()
        day.update({"date": today, "n": 0})
    urls = recent_urls()
    # 오늘 처음 보이는 주소 → 오래전에 보낸 주소 순
    todo = [u for u in urls if sent.get(u, "") < cutoff or (today in u and sent.get(u) != today)]
    n = 0
    for u in todo:
        if day["n"] >= DAY_CAP:
            break
        try:
            http("POST", "https://indexing.googleapis.com/v3/urlNotifications:publish", headers=h,
                 json={"url": u, "type": "URL_UPDATED"}, retries=2)
            sent[u] = today
            day["n"] += 1
            n += 1
        except Exception as e:  # noqa: BLE001
            code = getattr(getattr(e, "response", None), "status_code", 0)
            log.warning("색인 요청 멈춤 %s: %s", code, u)
            if code in (403, 429):
                st["publish_block"] = {"at": config.now_kst().isoformat(timespec="minutes"), "code": code}
                break
    log.info("구글 색인 요청 %d개 (오늘 누적 %d)", n, day["n"])


def _inspect(h: dict, prop: str, st: dict) -> None:
    today = config.now_kst().strftime("%Y-%m-%d")
    if (st.get("inspect") or {}).get("date") == today:
        return
    from .indexnow import FIXED, recent_urls
    urls = list(dict.fromkeys([config.SITE_URL + quote(u) for u in FIXED] + recent_urls()))[:INSPECT_N]
    res = {}
    for u in urls:
        try:
            r = http("POST", "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect", headers=h,
                     json={"inspectionUrl": u, "siteUrl": prop, "languageCode": "ko"}, retries=2).json()
            ir = r.get("inspectionResult", {}).get("indexStatusResult", {})
            res[u] = {"state": ir.get("coverageState", ""), "verdict": ir.get("verdict", ""), "crawled": ir.get("lastCrawlTime", ""),
                      "canonical": ir.get("googleCanonical", "")}
        except Exception as e:  # noqa: BLE001
            res[u] = {"state": "확인 안 됨", "err": str(getattr(getattr(e, "response", None), "status_code", "") or type(e).__name__)}
    st["inspect"] = {"date": today, "indexed": sum(1 for v in res.values() if v.get("verdict") == "PASS"), "total": len(res), "urls": res}
    try:
        end = config.now_kst().date()
        q = http("POST", f"https://www.googleapis.com/webmasters/v3/sites/{quote(prop, safe='')}/searchAnalytics/query", headers=h,
                 json={"startDate": str(end - timedelta(days=7)), "endDate": str(end), "dimensions": ["query"], "rowLimit": 25}, retries=2).json()
        rows = q.get("rows", [])
        st["search"] = {"date": today, "clicks": sum(r["clicks"] for r in rows), "impressions": sum(r["impressions"] for r in rows),
                        "top": [{"q": r["keys"][0], "c": r["clicks"], "i": r["impressions"], "pos": round(r["position"], 1)} for r in rows[:15]]}
    except Exception as e:  # noqa: BLE001
        log.info("검색 노출 조회 건너뜀: %s", e)
    log.info("색인 확인 %d/%d", st["inspect"]["indexed"], st["inspect"]["total"])


def run() -> int:
    sa = _sa()
    if not sa:
        log.info("GSC_SA_JSON 없음: 구글 직접 알림은 건너뜀(사이트맵은 robots.txt로 수집)")
        return 0
    st = read_json(STATE, {}) or {}
    try:
        h = {"Authorization": f"Bearer {_token(sa)}"}
    except Exception as e:  # noqa: BLE001
        st["auth"] = {"at": config.now_kst().isoformat(timespec="minutes"), "ok": False, "why": type(e).__name__}
        _save(st)
        log.warning("구글 인증 안 됨: %s", type(e).__name__)
        return 0
    st["auth"] = {"at": config.now_kst().isoformat(timespec="minutes"), "ok": True, "account": sa.get("client_email", "")}
    props = _properties(h)
    st["properties"] = props
    if props:
        _submit_sitemaps(h, props, st)
    _publish(h, st)
    if props:
        _inspect(h, props[0], st)
    _save(st)
    return 1


def _save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
