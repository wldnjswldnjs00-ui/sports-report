"""베트맨 공개 발매 정보 수집기.

주의
- 공개된(로그인 불필요) 발매 정보만 읽는다. 하루 몇 번, 요청 사이 지연을 둔다.
- 베트맨은 공식 API를 제공하지 않으므로 응답 형식이 바뀔 수 있다.
  필드 이름 후보를 여러 개 두고 유연하게 매핑하며, 매핑이 실패하면 예외를 던져
  파이프라인이 수동 입력 파일로 넘어가게 한다. 잘못된 데이터를 조용히 발행하지 않는다.
- 해외 IP 를 차단하는 경우가 있다. 그때는 국내 서버(예: 오라클 클라우드 서울/춘천 무료 VM)나
  개인 PC 에서 `python -m engine collect` 를 돌려 push 하면 된다.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

from .. import config
from ..util import http as _http, write_json


def http(method, url, **kw):
    """베트맨 전용: 응답이 느릴 때가 있어 연결 15초·읽기 45초, 4회 재시도(5·10·20초 간격)."""
    kw.setdefault("timeout", (15, 45))
    kw.setdefault("retries", 4)
    kw.setdefault("backoff", 5.0)
    return _http(method, url, **kw)

log = logging.getLogger("engine.betman")

BASE = "https://www.betman.co.kr"
LIST_URLS = (BASE + "/buyPsblGame/inqBuyAbleGameInfoList.do", BASE + "/buyPsblGame/inqCacheBuyAbleGameInfoList.do")
GAME_URL = BASE + "/buyPsblGame/gameInfoInq.do"
LIST_REFERER = BASE + "/main/mainPage/gamebuy/buyableNClosedIFR.do?isIFR=Y"
GM_ID = "G101"  # 프로토 승부식

SPORT_BY_ITEM = {"SC": "soccer", "BK": "basketball", "BS": "baseball", "VL": "volleyball",
                 "HK": "hockey", "FB": "football"}
SPORT_BY_WORD = {"축구": "soccer", "농구": "basketball", "야구": "baseball", "배구": "volleyball",
                 "하키": "hockey", "미식축구": "football"}


def _rows(payload: Any) -> list[dict]:
    """compSchedules 는 {'keys': [...], 'datas': [[...], ...]} 컬럼형."""
    cs = (payload or {}).get("compSchedules") or {}
    keys, datas = cs.get("keys"), cs.get("datas")
    if not keys or not isinstance(datas, list):
        return []
    return [dict(zip(keys, r)) for r in datas if isinstance(r, list)]


def _market(row: dict) -> str | None:
    """betNm/betTypNm 문자열로 마켓 판별. 전반·특수 마켓은 제외(정산 기준이 다름)."""
    name = f"{row.get('betNm') or ''} {row.get('betTypNm') or ''}"
    if "세트핸디캡" in name:
        return "HANDICAP"  # 배구 세트 핸디캡
    if "전반" in name or "후반" in name or "SUM" in name or "1점" in name or "쿼터" in name or "세트" in name:
        return None
    if "언더오버" in name:
        return "OU"
    if "핸디" in name:
        return "HANDICAP"
    if "승무패" in name:
        return "1X2"
    if "승패" in name:
        return "WL"
    return None


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _sport(row: dict) -> str:
    sp = SPORT_BY_ITEM.get(str(row.get("itemCode") or "").upper())
    if sp:
        return sp
    name = str(row.get("betNm") or "")
    for w, sp in SPORT_BY_WORD.items():
        if name.startswith(w):
            return sp
    return "etc"


def _flows(payload: dict) -> dict[int, dict]:
    """tooltipList(베트맨 공개 배당 변동 이력) → 경기번호별 {왼칸/무/오른칸: [처음, 지금], 변동횟수}."""
    out: dict[int, dict] = {}
    # 변동 이력의 배당은 100배 정수(136 = 1.36배)
    rows = sorted(payload.get("tooltipList") or [], key=lambda t: str(t.get("LST_CHG_DTM") or t.get("CHG_DTM") or ""))
    for t in rows:
        try:
            no = int(t.get("GM_SEQ"))
        except (TypeError, ValueError):
            continue
        f = out.setdefault(no, {"n": 0, "first": {}, "last": {}, "at": None})
        for side, b, a in (("W", "BCHG_W_ODDS", "ACHG_W_ODDS"), ("D", "BCHG_D_ODDS", "ACHG_D_ODDS"), ("L", "BCHG_L_ODDS", "ACHG_L_ODDS")):
            bv, av = _num(t.get(b)) / 100, _num(t.get(a)) / 100
            if bv > 1 and side not in f["first"]:
                f["first"][side] = bv
            if av > 1:
                f["last"][side] = av
        f["n"] += 1
        f["at"] = str(t.get("LST_CHG_DTM") or t.get("CHG_DTM") or "")[:12]
    return out


def parse_pending(payload: dict) -> list[dict[str, Any]]:
    """발매는 잡혔지만 배당이 아직 공개되지 않은 경기(일정만)."""
    seen, out = set(), []
    for r in _rows(payload):
        home, away, ko = r.get("homeName"), r.get("awayName"), r.get("gameDate")
        if not home or not away or not isinstance(ko, (int, float)) or _num(r.get("winAllot")) > 1 or not _market(r):
            continue
        if str(r.get("gameReject") or "0") != "0":
            continue
        key = (home, away, ko)
        if key in seen:
            continue
        seen.add(key)
        out.append({"sport": _sport(r), "league": str(r.get("leagueName") or "").strip(), "home": str(home).strip(), "away": str(away).strip(),
                    "kickoff": datetime.fromtimestamp(ko / 1000, config.KST).isoformat(timespec="minutes")})
    return out


PENDING: list[dict[str, Any]] = []


def parse_round(payload: dict, gm_ts: str) -> list[dict[str, Any]]:
    out = []
    flows = _flows(payload)
    for r in _rows(payload):
        home, away = r.get("homeName"), r.get("awayName")
        mk = _market(r)
        ko = r.get("gameDate")
        if not home or not away or not mk or not isinstance(ko, (int, float)):
            continue
        if str(r.get("gameReject") or "0") != "0" or str(r.get("buyReject") or "0") != "0":
            continue  # 발매 취소·구매 제한 경기
        w, d, l = _num(r.get("winAllot")), _num(r.get("drawAllot")), _num(r.get("loseAllot"))
        if mk == "OU":
            # 베트맨 언더오버는 승 칸=언더, 패 칸=오버 (winTxt/loseTxt 로 확인)
            if str(r.get("winTxt") or "언더").startswith("오버"):
                odds = {"O": w, "U": l}
            else:
                odds = {"U": w, "O": l}
        else:
            odds = {"H": w, "A": l}
            if d > 1:
                odds["D"] = d
            elif mk == "1X2":
                mk = "WL"
        if not all(v > 1 for v in odds.values()):
            continue  # 발매 전(배당 0.0) 또는 발매 중지
        line = r.get("winHandi")
        line = float(line) if isinstance(line, (int, float)) and line != 0 else None
        if mk in ("HANDICAP", "OU") and line is None:
            continue
        no = r.get("matchSeq")
        flow = None
        fl = flows.get(no) if isinstance(no, int) else flows.get(int(no)) if str(no).isdigit() else None
        if fl and fl["first"]:
            if mk == "OU":
                under_first = "O" not in odds or not str(r.get("winTxt") or "언더").startswith("오버")
                side_map = {"W": "U" if under_first else "O", "L": "O" if under_first else "U"}
            else:
                side_map = {"W": "H", "D": "D", "L": "A"}
            flow = {"changes": fl["n"], "at": fl["at"],
                    "from": {side_map[k]: v for k, v in fl["first"].items() if k in side_map},
                    "to": {side_map[k]: v for k, v in fl["last"].items() if k in side_map}}
        out.append({
            "id": f"betman:{GM_ID}:{gm_ts}:{no}",
            "source": "betman", "pool": "proto", "round": str(gm_ts),
            "game_no": int(no) if str(no).isdigit() else None,
            "sport": _sport(r), "league": str(r.get("leagueName") or "기타").strip(),
            "kickoff": datetime.fromtimestamp(ko / 1000, config.KST).isoformat(timespec="minutes"),
            "home": str(home).strip(), "away": str(away).strip(), "market": mk,
            "line": line, "odds": odds,
            "venue": (str(r.get("meetStadiumFullName")).strip() or None) if r.get("meetStadiumFullName") else None,
            "flow": flow,
        })
    return out


def fetch(day: str) -> list[dict[str, Any]]:
    _debug.clear()
    try:
        out = _fetch(day)
    except Exception as e:
        _debug["error"] = f"{type(e).__name__}: {e}"
        _debug["at"] = config.now_kst().isoformat(timespec="seconds")
        write_json(config.STATE / "betman_debug.json", _debug)
        raise
    dbg = config.STATE / "betman_debug.json"
    if dbg.exists():
        dbg.unlink()
    return out


_debug: dict[str, Any] = {}


def _snap(name: str, r) -> None:
    try:
        _debug[name] = {"status": r.status_code, "type": r.headers.get("content-type"), "url": r.url, "body": r.text[:6000]}
    except Exception:  # noqa: BLE001
        pass


def _json(r) -> dict:
    if "json" not in (r.headers.get("content-type") or "").lower() or r.text.lstrip().startswith("<"):
        raise RuntimeError(f"JSON 대신 다른 응답 ({r.status_code} {r.headers.get('content-type')})")
    return r.json()


_SCORE = re.compile(r"(\d+)\s*[:\-]\s*(\d+)")


def parse_results(payload: dict, gm_ts: str) -> dict[str, dict]:
    """마감 회차 결과.

    베트맨 gameResult 는 칸 번호다: 0=승(왼쪽) 칸, 1=무 칸, 2=패(오른쪽) 칸.
    mchScore 는 마켓마다 다르다(핸디캡은 핸디 적용 점수, 언더오버는 '합계:0').
    그래서 결과 판정은 gameResult 로 하고, 실제 점수는 승패·승무패 행에서만 Elo 용으로 쓴다.
    """
    out: dict[str, dict] = {}
    for r in _rows(payload):
        no = r.get("matchSeq")
        mid = f"betman:{GM_ID}:{gm_ts}:{no}"
        if str(r.get("gameReject") or "0") != "0":
            out[mid] = {"status": "CANCELLED", "src": "betman"}
            continue
        code = str(r.get("gameResult") if r.get("gameResult") is not None else "").strip()
        score = str(r.get("mchScore") or "")
        if code not in ("0", "1", "2") or not score:
            continue
        mk = _market(r)
        if mk == "OU":
            under_first = not str(r.get("winTxt") or "언더").startswith("오버")
            outcome = {"0": "U" if under_first else "O", "2": "O" if under_first else "U"}.get(code)
        else:
            outcome = {"0": "H", "1": "D", "2": "A"}[code]
        if outcome is None:
            continue
        rec = {"status": "FT", "outcome": outcome, "src": "betman", "raw": score, "code": code, "market": mk}
        m = _SCORE.search(score)
        if m and mk in ("1X2", "WL"):
            rec["home_score"], rec["away_score"] = float(m.group(1)), float(m.group(2))
        out[mid] = rec
    return out


def fetch_results(rounds: set[str]) -> dict[str, dict]:
    """회차 번호 목록을 다시 조회해 결과를 모은다. 실패한 회차는 건너뛴다."""
    ajax = {"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01", "Origin": BASE}
    res: dict[str, dict] = {}
    try:
        http("GET", BASE + "/")
    except Exception as e:  # noqa: BLE001
        log.warning("베트맨 접속 실패(결과): %s", e)
        return res
    for ts in sorted(rounds)[:6]:
        if not ts.isdigit():
            continue
        year = "20" + ts[:2]
        slip = f"{BASE}/main/mainPage/gamebuy/gameSlip.do?gmId={GM_ID}&year={year}&gmTs={ts}"
        try:
            time.sleep(1.5)
            r = http("POST", GAME_URL, json={"gmId": GM_ID, "gmTs": int(ts), "gameYear": year, "_sbmInfo": {"debugMode": "false"}},
                     headers={**ajax, "Referer": slip})
            res.update(parse_results(_json(r), ts))
        except Exception as e:  # noqa: BLE001
            log.warning("베트맨 결과 %s 실패: %s", ts, e)
    return res


def _schema_note(doc: dict) -> None:
    """응답 필드 목록과 표본 한 줄을 남긴다(결과·점수 필드 파악용, 수 KB)."""
    try:
        cs = doc.get("compSchedules") or {}
        sample = dict(zip(cs.get("keys") or [], (cs.get("datas") or [[]])[0]))
        from collections import Counter
        kinds = Counter()
        for r in _rows(doc):
            kinds[f"{r.get('itemCode')}|{r.get('betNm')}|{'배당있음' if _num(r.get('winAllot')) > 1 else '배당없음'}|{'사용' if _market(r) else '제외'}"] += 1
        tips = doc.get("tooltipList") or []
        write_json(config.STATE / "betman_schema.json", {
            "top_keys": sorted(doc.keys()), "row_keys": cs.get("keys"), "sample_row": sample, "kinds": dict(kinds),
            "tooltip_n": len(tips), "tooltip_sample": tips[:2],
            "at": config.now_kst().isoformat(timespec="seconds")})
    except Exception:  # noqa: BLE001
        pass


def _fetch(day: str) -> list[dict[str, Any]]:
    ajax = {"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01", "Origin": BASE}
    http("GET", BASE + "/")  # 세션 쿠키(JSESSIONID)
    time.sleep(1.5)
    listing, last_err = None, None
    for url in LIST_URLS:
        try:
            r = http("POST", url, json={"_sbmInfo": {"debugMode": "false"}}, headers={**ajax, "Referer": LIST_REFERER})
            _snap("list", r)
            listing = _json(r)
            if listing.get("protoGames") is not None:
                break
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(1.5)
    if not listing or listing.get("protoGames") is None:
        raise RuntimeError(f"발매 목록 조회 실패: {last_err}")
    now_ms = config.now_kst().timestamp() * 1000
    rounds = [g for g in listing["protoGames"] if g.get("gmId") == GM_ID and _num(g.get("saleEndDate")) > now_ms]
    if not rounds:
        rounds = [g for g in listing["protoGames"] if g.get("gmId") == GM_ID]
    if not rounds:
        raise RuntimeError("발매 중인 프로토 승부식 회차 없음")

    out: list[dict[str, Any]] = []
    PENDING.clear()
    for g in sorted(rounds, key=lambda g: str(g['gmTs']))[:6]:
        ts = str(g["gmTs"])
        year = str(g.get("gmOsidTsYear") or ("20" + ts[:2]))
        slip = f"{BASE}/main/mainPage/gamebuy/gameSlip.do?gmId={GM_ID}&year={year}&gmTs={ts}"
        time.sleep(1.5)
        http("GET", slip)
        time.sleep(1.5)
        r = http("POST", GAME_URL, json={"gmId": GM_ID, "gmTs": int(ts), "gameYear": year, "_sbmInfo": {"debugMode": "false"}},
                 headers={**ajax, "Referer": slip})
        _snap(f"game_{ts}", r)
        doc = _json(r)
        _schema_note(doc)
        out.extend(parse_round(doc, ts))
        PENDING.extend(parse_pending(doc))
    if not out:
        raise RuntimeError("발매 회차는 있으나 배당이 공개된 경기가 없음(발매 시작 전일 수 있음)")
    return [m for m in out if in_horizon(m["kickoff"], day)]


def in_window(ko: str, day: str) -> bool:
    """리포트의 '오늘' 범위: 그 구매일(당일 08:30 ~ 다음 날 08:30 킥오프)."""
    return config.sales_day(ko) == day


def in_horizon(ko: str, day: str, days: int = 3) -> bool:
    """미리보기 범위: 그 구매일 시작(당일 08:30)부터 3일."""
    t = datetime.fromisoformat(ko)
    start = datetime.fromisoformat(day + "T00:00:00+09:00") + config.DAY_START
    return 0 <= (t - start).total_seconds() < 86400 * days
