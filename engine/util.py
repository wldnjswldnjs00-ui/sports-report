"""공용 유틸: 안전한 JSON 입출력, 재시도 HTTP, 이름 정규화."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

from . import config

log = logging.getLogger("engine")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        # 깨진 파일 때문에 전체 파이프라인이 죽지 않게 한다.
        log.error("JSON 파싱 실패 %s: %s", path, e)
        return default


def write_json(path: Path, data: Any) -> None:
    """원자적 쓰기: 중간에 죽어도 기존 파일이 반쯤 덮이지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})


def http(method: str, url: str, *, retries: int = 3, backoff: float = 2.0, **kw) -> requests.Response:
    """지수 백오프 재시도. 4xx(429 제외)는 재시도하지 않는다."""
    kw.setdefault("timeout", config.HTTP_TIMEOUT)
    last: Exception | None = None
    for i in range(retries):
        try:
            r = _session.request(method, url, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} {url}", response=r)
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            last = e
            code = e.response.status_code if e.response is not None else 0
            if 400 <= code < 500 and code != 429:
                break
        except requests.RequestException as e:
            last = e
        if i < retries - 1:
            time.sleep(backoff * (2 ** i))
    assert last is not None
    raise last


_strip = re.compile(r"[\s\.\-_'’`]+")
_suffix = re.compile(r"\b(fc|cf|afc|sc|ac|bc|club|the)\b")


def norm_team(name: str) -> str:
    """팀 이름 매칭용 정규화 키."""
    s = unicodedata.normalize("NFKC", name or "").lower()
    s = _suffix.sub(" ", s)
    return _strip.sub("", s)


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").strip().lower()
    s = re.sub(r"[^\w가-힣]+", "-", s)
    return s.strip("-") or "etc"
