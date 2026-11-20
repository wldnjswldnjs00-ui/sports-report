"""GitHub Actions 무료 실행 시간 지키기.

비공개 저장소는 한 달 무료 시간이 정해져 있고(기본 2,000분), 다 쓰면 그달 끝까지 모든 자동 실행이 멈춘다.
이번 달 실행들의 실제 사용 시간(분)을 GitHub 에서 읽어 더하고(한 번 읽은 실행은 기록해 두고 새 실행만 읽는다),
속도대로면 한도를 넘을 것 같을 때 '절약 모드'로 바꾼다.

  normal  : 평소대로
  save    : 예비·재수집 시각(09:30·13:00·18:00·22:00)은 쓰레드가 빠진 게 없으면 건너뛴다
  minimal : 필수 시각만(06:00 채점, 07·11·15·19시 쓰레드, 23:05 다음 구매일), 다시 올리기는 2번까지

ACTIONS_MINUTES_LIMIT 환경 변수로 한도를, ACTIONS_CYCLE_DAY 로 무료 시간이 다시 채워지는 날(UTC 기준 그 달의 며칠)을 바꿀 수 있다.
이 계정은 11/19 에 실행이 멈췄다가 11/20 에 다시 돌아 20일에 채워지는 것으로 본다.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from . import config
from .util import http, read_json, write_json

log = logging.getLogger("engine.budget")
STATE = config.STATE / "minutes.json"
OPTIONAL = {"30 0 * * *", "0 4 * * *", "0 9 * * *", "0 13 * * *"}


def _limit() -> int:
    try:
        return int(os.getenv("ACTIONS_MINUTES_LIMIT") or 2000)
    except ValueError:
        return 2000


def _gh(path: str, **params):
    repo, token = os.getenv("GITHUB_REPOSITORY"), os.getenv("GITHUB_TOKEN")
    if not repo or not token:
        return None
    return http("GET", f"https://api.github.com/repos/{repo}{path}", params=params or None, retries=2,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}).json()


def _cycle() -> tuple[datetime, datetime]:
    """지금 속한 무료 시간 주기의 시작·끝(UTC)."""
    try:
        cd = min(max(int(os.getenv("ACTIONS_CYCLE_DAY") or 20), 1), 28)
    except ValueError:
        cd = 20
    now = datetime.now(timezone.utc)
    start = now.replace(day=cd, hour=0, minute=0, second=0, microsecond=0)
    if start > now:
        start = (start.replace(day=1) - timedelta(days=1)).replace(day=cd)
    end = (start.replace(day=28) + timedelta(days=7)).replace(day=cd)
    return start, end


def usage() -> tuple[float, dict]:
    """이번 주기에 사용한 분(실행별 기록을 이어서 더함). GitHub 에 못 묻는 환경이면 기록된 값만."""
    now = config.now_kst()
    cs, _ = _cycle()
    month = cs.strftime("%Y-%m-%d")
    st = read_json(STATE, {}) or {}
    if st.get("month") != month:
        st = {"month": month, "runs": {}}
    runs: dict = st.setdefault("runs", {})
    try:
        page = 1
        while page <= 10:
            d = _gh("/actions/runs", per_page=100, page=page, created=f">={cs.strftime('%Y-%m-%dT%H:%M:%SZ')}")
            if not d:
                break
            items = d.get("workflow_runs") or []
            for r in items:
                rid = str(r["id"])
                if rid in runs or r.get("status") != "completed":
                    continue
                t = _gh(f"/actions/runs/{rid}/timing") or {}
                ms = sum((v or {}).get("total_ms", 0) for v in (t.get("billable") or {}).values())
                if not ms and t.get("run_duration_ms"):
                    ms = t["run_duration_ms"]
                runs[rid] = round(ms / 60000, 2)
            if len(items) < 100:
                break
            page += 1
    except Exception as e:  # noqa: BLE001 - 못 읽으면 지난 기록으로 판단
        log.warning("사용 시간 확인 실패: %s", type(e).__name__)
    used = round(sum(runs.values()), 1)
    st["used"] = used
    st["at"] = now.isoformat(timespec="minutes")
    write_json(STATE, st)
    return used, st


def mode() -> str:
    used, st = usage()
    lim = _limit()
    cs, ce = _cycle()
    nowu = datetime.now(timezone.utc)
    elapsed = max((nowu - cs).total_seconds() / 86400, 0.5)
    pace = used / elapsed * ((ce - cs).total_seconds() / 86400)  # 이 속도로 가면 주기 끝 사용량
    if used >= lim * 0.9:
        m = "minimal"
    elif used >= lim * 0.7 or (elapsed >= 3 and pace >= lim * 0.95):  # 주기 초반 며칠은 속도 추정이 흔들려 쓰지 않는다
        m = "save"
    else:
        m = "normal"
    st = read_json(STATE, {}) or {}
    st.update(mode=m, pace=round(pace), limit=lim)
    write_json(STATE, st)
    log.info("무료 실행 시간: 이번 주기 %.0f분 / %d분, 이 속도면 월말 %.0f분 → %s", used, lim, pace, m)
    return m


def should_skip(slot: str) -> bool:
    """이번 실행을 건너뛸지(쓰레드가 빠진 게 있으면 건너뛰지 않는다)."""
    m = mode()
    if m == "normal" or slot not in OPTIONAL:
        return False
    from . import threads as TH
    if any(TH.due(k) for k in ("analysis", "result", "kh")):
        return False
    return True
