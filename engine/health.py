"""자동 점검. 문제가 이어지면 GitHub 이슈 하나를 열어 알린다(저장소 주인에게 이메일이 간다). 해결되면 닫는다.

점검 항목
  - 베트맨 수집이 2번 연속 실패 (사이트·주소가 바뀌었을 가능성 → 진단 스냅샷 위치 안내)
  - 리포트가 30시간 넘게 갱신되지 않음
  - 쓰레드 토큰 만료 임박(첫 게시 후 53일, 토큰 수명 60일)
  - 해외 배당 API 잔여량이 월말까지 기본 수집에 모자람
GITHUB_TOKEN 이 없으면(로컬 실행) 화면에만 출력한다.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta

from . import config
from .util import http, read_json, write_json

log = logging.getLogger("engine.health")
STATE = config.STATE / "health.json"
TITLE = "⚠️ 사이트 자동 점검 경고"


def problems() -> list[str]:
    st = read_json(STATE, {}) or {}
    out: list[str] = []
    rep = read_json(config.REPORTS / f"{config.today_kst()}.json") or {}
    srcs = rep.get("sources") or {}
    betman_failed = str(srcs.get("betman", "")).startswith("실패") or (config.STATE / "betman_debug.json").exists()
    fails = st.get("betman_fails", 0) + 1 if betman_failed else 0
    st["betman_fails"] = fails
    if fails >= 2:
        out.append(f"베트맨 경기 수집이 {fails}번 연속 실패했습니다. 베트맨 사이트나 데이터 주소가 바뀌었을 수 있습니다. "
                   "진단 기록: `data/state/betman_debug.json`, `data/state/betman_schema.json`. 그동안 사이트는 마지막 리포트를 그대로 보여줍니다.")
    # 베트맨 구조가 바뀌면 접속은 돼도 경기를 0개로 읽거나 배당을 못 읽을 수 있다(실패로 안 잡힘).
    # 경기 수·분석된 비율이 평소보다 크게 줄어든 상태가 3번 이어지면 알린다.
    ms = rep.get("markets") or []
    analyzed = sum(1 for m in ms if m.get("analysis"))
    recent = []
    for pth in sorted(config.REPORTS.glob("*.json"))[-15:-1]:
        try:
            recent.append(len((read_json(pth) or {}).get("markets") or []))
        except Exception:  # noqa: BLE001
            pass
    typical = sorted(recent)[len(recent) // 2] if recent else 0
    weird = (not betman_failed) and typical >= 10 and (len(ms) == 0 or len(ms) < typical * 0.15 or (ms and analyzed / len(ms) < 0.3))
    st["weird"] = st.get("weird", 0) + 1 if weird else 0
    if st["weird"] >= 3:
        out.append(f"베트맨에서 읽은 경기가 평소와 크게 다릅니다(지금 {len(ms)}개, 분석 {analyzed}개 / 평소 {typical}개 안팎, {st['weird']}번 연속). "
                   "베트맨 사이트 구조가 바뀌었을 수 있습니다. 진단 기록: `data/state/betman_schema.json`.")
    upd = rep.get("updated_at") or rep.get("generated_at")
    if upd:
        age = config.now_kst() - datetime.fromisoformat(upd)
        if age > timedelta(hours=30):
            out.append(f"오늘 리포트가 {age.total_seconds() / 3600:.0f}시간째 갱신되지 않았습니다.")
    elif not rep:
        st["no_report"] = st.get("no_report", 0) + 1
        if st["no_report"] >= 3:
            out.append("오늘 구매일 리포트가 아직 만들어지지 않았습니다(3번 연속).")
    else:
        st["no_report"] = 0
    # 실제 사이트: 지난 실행에서 만든 구매일이 지금 사이트에 보이는지(배포 실패 감지). 다음 실행을 위해 이번 구매일을 기록
    from . import selfcheck
    if st.get("site_expect"):
        out += selfcheck.site_problems(st["site_expect"])
    st["site_expect"] = config.today_kst()
    th = read_json(config.STATE / "threads.json", {}) or {}
    posted = th.get("posted") or []
    if posted:
        first = st.setdefault("threads_first", posted[0][:10])
        if (date.fromisoformat(config.today_kst()) - date.fromisoformat(first)).days >= 53:
            out.append("쓰레드 토큰이 곧(60일) 만료됩니다. Meta 개발자 화면에서 '액세스 토큰 생성'으로 새 토큰을 만들어 "
                       "GitHub Secrets 의 `THREADS_TOKEN` 값을 바꾼 뒤, 이 이슈에 '토큰 갱신' 이라고 댓글을 남기고 닫아 주세요.")
    from .sources import odds_api
    rem = odds_api._remaining()
    if rem is not None and rem < odds_api._days_left() * odds_api.DAILY_NEED * 0.5:
        out.append(f"해외 배당 API 잔여량이 {rem:.0f}회로 월말까지 모자랄 수 있습니다. 새로고침은 자동으로 멈추고, 부족하면 레이팅 기반 분석으로 대신합니다.")
    write_json(STATE, st)
    return out


def _gh(method: str, path: str, **kw):
    repo, token = os.getenv("GITHUB_REPOSITORY"), os.getenv("GITHUB_TOKEN")
    if not repo or not token:
        return None
    return http(method, f"https://api.github.com/repos/{repo}{path}", retries=2,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, **kw)


def check() -> list[str]:
    ps = problems()
    for p in ps:
        log.warning("점검: %s", p)
    try:
        r = _gh("GET", "/issues", params={"state": "open", "labels": "auto-health", "per_page": 5})
        open_issue = (r.json() or [None])[0] if r is not None else None
        if ps:
            body = "자동 점검에서 아래 문제가 확인됐습니다.\n\n" + "\n".join(f"- {p}" for p in ps) + \
                   f"\n\n_{config.now_kst():%Y-%m-%d %H:%M} KST 점검. 해결되면 이 이슈는 자동으로 닫힙니다._"
            if open_issue:
                _gh("PATCH", f"/issues/{open_issue['number']}", json={"body": body})
            else:
                _gh("POST", "/issues", json={"title": TITLE, "body": body, "labels": ["auto-health"]})
        elif open_issue:
            _gh("POST", f"/issues/{open_issue['number']}/comments", json={"body": "다시 정상입니다. 자동으로 닫습니다."})
            _gh("PATCH", f"/issues/{open_issue['number']}", json={"state": "closed"})
    except Exception as e:  # noqa: BLE001
        log.warning("점검 알림 실패: %s", type(e).__name__)
    return ps
