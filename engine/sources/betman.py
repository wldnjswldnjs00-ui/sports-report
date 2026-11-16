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
import time
from datetime import datetime
from typing import Any

from .. import config
from ..util import http, write_json

log = logging.getLogger("engine.betman")

BASE = "https://www.betman.co.kr"
LIST_URL = BASE + "/buyPsblGame/inqCacheBuyAbleGameInfoList.do"
GAME_URL = BASE + "/buyPsblGame/gameInfoInq.do"

# 게임 종류: 프로토 승부식, 축구토토 승무패
GAME_IDS = {"G101": "proto", "G011": "toto"}

SPORT_MAP = {
    "SC": "soccer", "축구": "soccer", "BK": "basketball", "농구": "basketball",
    "BS": "baseball", "야구": "baseball", "VL": "volleyball", "배구": "volleyball",
    "HK": "hockey", "하키": "hockey", "FB": "football", "미식축구": "football",
}

F = {  # 필드 이름 후보
    "home": ("homeName", "hTeamNm", "homeTeamName", "HOME_NM"),
    "away": ("awayName", "aTeamNm", "awayTeamName", "AWAY_NM"),
    "league": ("leagueName", "lgNm", "leagueNm", "LEAGUE_NM"),
    "sport": ("itemCode", "sportsCd", "itemNm", "SPORTS_CD"),
    "win": ("winAllot", "wAllot", "winRt", "WIN_ALLOT"),
    "draw": ("drawAllot", "dAllot", "drawRt", "DRAW_ALLOT"),
    "lose": ("loseAllot", "lAllot", "loseRt", "LOSE_ALLOT"),
    "kickoff": ("gameDate", "mchDtm", "matchDate", "GAME_DT"),
    "no": ("matchSeq", "gmSeq", "mchSeq", "MATCH_SEQ"),
    "type": ("mchType", "gameType", "betType", "MCH_TYPE"),
    "line": ("handi", "handicap", "hdcp", "uoLine", "HANDI"),
}


def _get(row: dict, key: str):
    for k in F[key]:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def _rows(payload: Any) -> list[dict]:
    """{'keys':[...], 'datas':[[...]]} 형태와 dict 리스트 형태를 모두 처리."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    if "keys" in payload and "datas" in payload:
        keys = payload["keys"]
        return [dict(zip(keys, r)) for r in payload["datas"] if isinstance(r, list)]
    for v in payload.values():
        rows = _rows(v)
        if rows and any(_get(r, "home") for r in rows):
            return rows
    return []


def _kickoff(v) -> str:
    if isinstance(v, (int, float)):  # epoch ms
        return datetime.fromtimestamp(v / 1000, config.KST).isoformat(timespec="minutes")
    s = str(v).strip()
    for fmt in ("%Y%m%d%H%M", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s[:len(datetime.now().strftime(fmt))], fmt).replace(tzinfo=config.KST).isoformat(timespec="minutes")
        except ValueError:
            continue
    raise ValueError(f"킥오프 파싱 실패: {v}")


def _market_type(t, line) -> str:
    t = str(t or "").upper()
    if "U" in t and "O" in t or "언더" in t:
        return "OU"
    if "H" in t or "핸디" in t or (line not in (None, "", 0, "0")):
        return "HANDICAP"
    return "1X2"


_debug: dict[str, Any] = {}


def _snap(name: str, r) -> None:
    """응답 형식 진단용 스냅샷(앞부분만). 수집 실패 시 data/state/betman_debug.json 에 남는다."""
    try:
        _debug[name] = {"status": r.status_code, "type": r.headers.get("content-type"), "url": r.url,
                        "body": r.text[:6000]}
    except Exception:  # noqa: BLE001
        pass


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


def _fetch(day: str) -> list[dict[str, Any]]:
    headers = {"Content-Type": "application/json; charset=UTF-8", "Referer": BASE + "/", "X-Requested-With": "XMLHttpRequest"}
    r = http("POST", LIST_URL, json={"_sbmInfo": {"debugMode": "false"}}, headers=headers)
    _snap("list", r)
    lst = r.json()
    games = []
    for g in _rows(lst) or (lst.get("data") if isinstance(lst, dict) else []) or []:
        gid = g.get("gmId") or g.get("GM_ID")
        ts = g.get("gmTs") or g.get("GM_TS")
        if gid in GAME_IDS and ts:
            games.append((gid, ts))
    if not games:
        raise RuntimeError("발매 중인 게임 목록을 찾지 못함(응답 형식 변경 가능성)")

    out: list[dict[str, Any]] = []
    for gid, ts in games:
        time.sleep(1.5)  # 서버 부담 최소화
        body = {"gmId": gid, "gmTs": ts, "gameYear": "", "_sbmInfo": {"debugMode": "false"}}
        rr = http("POST", GAME_URL, json=body, headers=headers)
        _snap(f"game_{gid}", rr)
        payload = rr.json()
        rows = _rows(payload.get("compSchedules", payload) if isinstance(payload, dict) else payload)
        pool = GAME_IDS[gid]
        for r in rows:
            home, away = _get(r, "home"), _get(r, "away")
            if not home or not away:
                continue
            try:
                ko = _kickoff(_get(r, "kickoff"))
            except ValueError:
                continue
            line = _get(r, "line")
            mt = "1X2" if pool == "toto" else _market_type(_get(r, "type"), line)
            sport_raw = str(_get(r, "sport") or "")
            sport = SPORT_MAP.get(sport_raw, SPORT_MAP.get(sport_raw[:2], "etc"))
            odds = {}
            if pool == "proto":
                w, d, l = _get(r, "win"), _get(r, "draw"), _get(r, "lose")
                if mt == "OU":
                    odds = {"U": w, "O": l}
                else:
                    odds = {"H": w, "A": l}
                    if d not in (None, "", 0, "0", 0.0):
                        odds["D"] = d
                    elif mt == "1X2":
                        mt = "WL"
            no = _get(r, "no")
            out.append({
                "id": f"betman:{gid}:{ts}:{no}:{mt}",
                "source": "betman", "pool": pool, "round": str(ts), "game_no": int(no) if str(no).isdigit() else None,
                "sport": sport, "league": _get(r, "league") or "기타", "kickoff": ko,
                "home": str(home), "away": str(away), "market": mt,
                "line": float(line) if line not in (None, "") else None, "odds": odds,
            })
    if not out:
        raise RuntimeError("경기 데이터를 매핑하지 못함(응답 형식 변경 가능성)")
    # 리포트 날짜 기준: 오늘 06:00 ~ 내일 06:00 KST 킥오프 경기(심야 해외 경기 포함)
    return [m for m in out if _in_window(m["kickoff"], day)]


def _in_window(ko: str, day: str) -> bool:
    t = datetime.fromisoformat(ko)
    start = datetime.fromisoformat(day + "T06:00:00+09:00")
    return 0 <= (t - start).total_seconds() < 86400 + 6 * 3600  # 다음날 정오까지 여유
