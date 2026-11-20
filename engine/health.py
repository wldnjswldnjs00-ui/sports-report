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
    # 베트맨은 자정~06시에 사이트를 닫는다. 그 시간대 접속 실패는 세지 않는다(연속 횟수는 유지).
    closed = config.now_kst().hour < 6
    fails = (st.get("betman_fails", 0) + (0 if closed else 1)) if betman_failed else 0
    st["betman_fails"] = fails
    # 발매 대기(회차 사이)는 고장이 아니다. 다만 36시간 넘게 이어지면 이상으로 본다.
    idle = str(srcs.get("betman", "")) == "발매 대기"
    if idle:
        st.setdefault("idle_since", config.now_kst().isoformat(timespec="minutes"))
        if config.now_kst() - datetime.fromisoformat(st["idle_since"]) > timedelta(hours=36):
            out.append("베트맨에 발매 중인 프로토 승부식 회차가 36시간 넘게 없습니다. 휴장이 아니라면 베트맨 사이트 구조가 바뀌었을 수 있습니다.")
    else:
        st.pop("idle_since", None)
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
    weird = (not betman_failed) and (not idle) and typical >= 10 and (len(ms) == 0 or len(ms) < typical * 0.15 or (ms and analyzed / len(ms) < 0.3))
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
    tk = read_json(config.STATE / "threads_token.json", {}) or {}
    posted = th.get("posted") or []
    if posted:
        first = st.setdefault("threads_first", posted[0][:10])
        days = (date.fromisoformat(config.today_kst()) - date.fromisoformat(first)).days
        exp = tk.get("expires")
        left = (exp / 1000 - config.now_kst().timestamp()) / 86400 if exp else None
        if left is not None and left <= 12:
            out.append(f"쓰레드 토큰이 {max(left, 0):.0f}일 뒤 만료됩니다(자동 연장이 되지 않고 있음). Meta 개발자 화면에서 새 장기 토큰을 만들어 "
                       "GitHub Secrets 의 `THREADS_TOKEN` 값을 바꿔 주세요. 바꾸면 다음 실행부터 자동으로 이어서 연장됩니다.")
        if tk.get("src") == "worker" and tk.get("err"):
            out.append(f"쓰레드 토큰 자동 연장에 오류가 있습니다: {tk['err'][:120]}. 토큰이 만료되기 전에 Meta 개발자 화면에서 새 토큰을 만들어 "
                       "GitHub Secrets 의 `THREADS_TOKEN` 값을 바꿔 주세요.")
        elif tk.get("src") != "worker" and days >= 53:
            out.append("쓰레드 토큰 자동 연장(Cloudflare Worker)을 쓰지 못하고 있어, 첫 토큰이 곧(60일) 만료됩니다. "
                       "Meta 개발자 화면에서 새 토큰을 만들어 GitHub Secrets 의 `THREADS_TOKEN` 값을 바꿔 주세요.")
    # Cloudflare Worker(정해진 시각에 실행을 시작하는 시계) 상태
    try:
        ws = http("GET", config.SITE_URL + "/api/status", retries=2, headers={"User-Agent": "sports-report-actions"}).json()
        hb = ws.get("cron_last")
        if hb:
            age_h = (datetime.now(datetime.fromisoformat(hb.replace("Z", "+00:00")).tzinfo) - datetime.fromisoformat(hb.replace("Z", "+00:00"))).total_seconds() / 3600
            if age_h > 3:
                out.append(f"Cloudflare 예약 실행이 {age_h:.0f}시간째 멈춰 있습니다. GitHub 예비 확인(지킴이)이 대신 돌리고 있지만 늦을 수 있습니다.")
        exp = ws.get("gh_token_expires")
        if exp:
            ed = datetime.strptime(exp[:10], "%Y-%m-%d").date()
            left = (ed - date.fromisoformat(config.today_kst())).days
            if left <= 14:
                out.append(f"Cloudflare 가 실행을 시작할 때 쓰는 GitHub 토큰이 {ed.isoformat()}에 만료됩니다({left}일 남음). "
                           "GitHub → Settings → Developer settings → Personal access tokens 에서 같은 권한으로 새로 만들어 "
                           "Cloudflare Worker 의 비밀 값 `GH_TOKEN` 을 바꿔 주세요. 그 전까지는 GitHub 예비 확인이 대신 돌립니다.")
    except Exception as e:  # noqa: BLE001
        log.info("Worker 상태 확인 건너뜀: %s", type(e).__name__)
    mn = read_json(config.STATE / "minutes.json", {}) or {}
    if mn.get("used") and mn.get("limit") and mn["used"] >= mn["limit"] * 0.8:
        out.append(f"GitHub Actions 무료 실행 시간을 이번 주기(매달 20일부터) {mn['used']:.0f}분 / {mn['limit']}분 썼습니다. 절약 모드({mn.get('mode')})로 "
                   "필수 시각(쓰레드·채점)만 돌리고 있습니다. 다음 20일에 자동으로 평소대로 돌아갑니다.")
    # 어제 쓰레드 글 4개(07 아침·11 결과·15 노하우·19 저녁)가 다 올라갔는지(다시 올리기까지 다 실패한 경우만 남는다)
    if th.get("posted") and os.getenv("THREADS_TOKEN"):
        y = date.fromisoformat(config.today_kst()) - timedelta(days=1)
        want = {f"{y.isoformat()}:morning": "07시 아침 분석", f"{(y + timedelta(days=1)).isoformat()}:night": "19시 저녁 분석",
                f"{(y - timedelta(days=1)).isoformat()}:result": "11시 전날 결과"}
        miss = [v for k, v in want.items() if k not in th["posted"]]
        if th.get("kh_days") is not None and y.isoformat() not in th["kh_days"]:
            miss.append("15시 노하우")
        # 결과는 경기가 덜 끝난 날 건너뛸 수 있고, 베트맨 휴장일엔 분석 글이 없을 수 있어 2개 이상 빠질 때만 알린다
        if len(miss) >= 2:
            out.append(f"어제({y.isoformat()}) 쓰레드 글 중 {', '.join(miss)}이 올라가지 않았습니다(다시 올리기까지 실패). "
                       "Actions 의 '매일 분석'·'쓰레드 다시 올리기' 기록에 원인이 남아 있습니다.")
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


OWNER = "wldnjswldnjs00-ui"
REMIND_DAYS = 50


def remind() -> None:
    """50일마다 쓰레드 토큰 확인 알림 이슈를 연다(저장소 주인에게 이메일). 이전 알림은 닫는다."""
    st = read_json(STATE, {}) or {}
    today = date.fromisoformat(config.today_kst())
    last = st.get("remind_at")
    if last and (today - date.fromisoformat(last)).days < REMIND_DAYS:
        return
    tk = read_json(config.STATE / "threads_token.json", {}) or {}
    exp = tk.get("expires")
    exp_s = datetime.fromtimestamp(exp / 1000, config.KST).strftime("%Y-%m-%d") if exp else "알 수 없음"
    auto = "정상(7일마다 자동 연장)" if tk.get("src") == "worker" and not tk.get("err") else f"확인 필요({tk.get('err') or tk.get('src') or '기록 없음'})"
    body = (f"@{OWNER} {REMIND_DAYS}일마다 보내는 쓰레드 토큰 확인 알림입니다.\n\n"
            f"- 자동 연장: {auto}\n- 지금 토큰 만료일: {exp_s}\n\n"
            "자동 연장이 '정상'이면 아무것도 하지 않아도 됩니다. '확인 필요'이거나 만료일이 2주 안이면 "
            "Meta 개발자 화면에서 새 장기 토큰을 만들어 GitHub 저장소 Settings → Secrets → `THREADS_TOKEN` 값만 바꿔 주세요. "
            "나머지는 자동으로 이어집니다.\n\n"
            f"_다음 알림: {(today + timedelta(days=REMIND_DAYS)).isoformat()}. 이 이슈는 다음 알림 때 자동으로 닫힙니다._")
    try:
        r = _gh("GET", "/issues", params={"state": "open", "labels": "token-reminder", "per_page": 10})
        if r is None:
            return
        for old in r.json() or []:
            _gh("PATCH", f"/issues/{old['number']}", json={"state": "closed"})
        rr = _gh("POST", "/issues", json={"title": f"🔔 {REMIND_DAYS}일 점검 알림: 쓰레드 토큰 ({today.isoformat()})", "body": body,
                                          "labels": ["token-reminder"]})
        if rr is not None and rr.status_code < 300:
            st = read_json(STATE, {}) or {}
            st["remind_at"] = today.isoformat()
            write_json(STATE, st)
    except Exception as e:  # noqa: BLE001
        log.warning("토큰 알림 실패: %s", type(e).__name__)


def check() -> list[str]:
    remind()
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
