"""쓰레드 토큰: Cloudflare Worker(KV)에 보관된 최신 토큰을 받아 쓴다(60일 만료를 Worker 가 7일마다 연장).

GitHub Actions 가 발급하는 OIDC 신원 증명으로 Worker(/api/tt)에 요청한다. 처음 한 번은 GitHub Secrets 의 토큰을
함께 보내 Worker 에 넣는다. Worker 를 쓸 수 없으면(로컬 실행, KV 미연결, 네트워크 문제) GitHub Secrets 토큰을 그대로 쓴다.
토큰 값은 로그에 남기지 않는다.
"""
from __future__ import annotations

import logging
import os

from . import config
from .util import http, write_json

log = logging.getLogger("engine.threads_token")
AUD = "sports-report-worker"
_cached: str | None = None


def _seed() -> str:
    return "".join(os.getenv("THREADS_TOKEN", "").split()).strip('"\'')


def _oidc() -> str | None:
    url, tok = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL"), os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not tok:
        return None
    r = http("GET", url, params={"audience": AUD}, headers={"Authorization": f"Bearer {tok}"}, retries=2)
    return (r.json() or {}).get("value")


def _note(src: str, err: str = "") -> None:
    """어디서 토큰을 받았는지만 기록(값은 저장하지 않음). 자동 점검이 연장 실패를 알아챌 때 쓴다."""
    try:
        write_json(config.STATE / "threads_token.json", {"src": src, "err": err[:200], "at": config.now_kst().isoformat(timespec="minutes")})
    except Exception:  # noqa: BLE001
        pass


def current() -> str:
    global _cached
    if _cached:
        return _cached
    seed = _seed()
    if not seed:
        return ""
    try:
        jwt = _oidc()
        if jwt:
            r = http("POST", config.SITE_URL + "/api/tt", json={"seed": seed}, retries=2,
                     headers={"Authorization": f"Bearer {jwt}", "User-Agent": "sports-report-actions"})
            d = r.json() if r.status_code == 200 else {}
            if d.get("token"):
                if d.get("error"):
                    log.warning("Worker 토큰 연장 오류 기록 있음: %s", str(d["error"])[:160])
                _note("worker", str(d.get("error") or ""))
                _cached = d["token"]
                return _cached
            log.info("Worker 토큰 응답 %s: Secrets 토큰 사용", r.status_code)
    except Exception as e:  # noqa: BLE001
        r = getattr(e, "response", None)
        log.info("Worker 토큰 확인 실패(%s %s): Secrets 토큰 사용", type(e).__name__,
                 f"{r.status_code} {r.text[:160]}" if r is not None else "")
    _note("seed")
    _cached = seed
    return seed
