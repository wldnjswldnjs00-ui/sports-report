"""국가대표 A매치 기록과 레이팅(해외 배당이 없는 국가대표 경기용).

기록: martj42/international_results (1872년~현재 A매치 전 경기, 공개 데이터)
레이팅: World Football Elo(eloratings.net)와 같은 방식으로 직접 계산한다.
  - 대회 중요도 K: 월드컵 본선 60, 대륙 선수권 본선 50, 예선·네이션스리그 40, 기타 대회 30, 친선 20
  - 득점 차 가중: 2골 차 ×1.5, 3골 이상 ×(11+N)/8
  - 홈 이점 +100 (중립 경기는 0)
결과표: 2000년 이후 경기를 '홈 이점 포함 레이팅 차' 25점 구간으로 묶어 실제 승무패·득점 차·총 득점 분포를 센다.
베트맨 기록은 쓰지 않는다. 일주일에 한 번 새로 받는다.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date

from .. import config
from ..util import http, read_json, write_json

log = logging.getLogger("engine.intl")
URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
PATH = config.STATE / "intl_elo.json"
BW = 25          # 레이팅 차 구간 폭
DIFF_MAX, GOAL_MAX = 6, 10
SINCE = "2000-01-01"

# 베트맨 한글 국가명 → 기록의 영어 이름
KO = {
    "한국": "South Korea", "대한민국": "South Korea", "북한": "North Korea", "일본": "Japan", "중국": "China", "카타르": "Qatar",
    "사우디아라비아": "Saudi Arabia", "이란": "Iran", "이라크": "Iraq", "요르단": "Jordan", "아랍에미리트": "United Arab Emirates",
    "UAE": "United Arab Emirates", "오만": "Oman", "바레인": "Bahrain", "쿠웨이트": "Kuwait", "시리아": "Syria", "레바논": "Lebanon",
    "팔레스타인": "Palestine", "예멘": "Yemen", "우즈베키스탄": "Uzbekistan", "카자흐스탄": "Kazakhstan", "키르기스스탄": "Kyrgyzstan",
    "타지키스탄": "Tajikistan", "투르크메니스탄": "Turkmenistan", "호주": "Australia", "뉴질랜드": "New Zealand", "태국": "Thailand",
    "베트남": "Vietnam", "인도네시아": "Indonesia", "말레이시아": "Malaysia", "싱가포르": "Singapore", "필리핀": "Philippines",
    "미얀마": "Myanmar", "캄보디아": "Cambodia", "라오스": "Laos", "인도": "India", "홍콩": "Hong Kong", "대만": "Taiwan",
    "중화타이베이": "Taiwan", "몽골": "Mongolia", "방글라데시": "Bangladesh", "네팔": "Nepal", "스리랑카": "Sri Lanka", "몰디브": "Maldives",
    "아프가니스탄": "Afghanistan", "파키스탄": "Pakistan", "브루나이": "Brunei", "동티모르": "Timor-Leste", "마카오": "Macau", "괌": "Guam",
    "미국": "United States", "캐나다": "Canada", "멕시코": "Mexico", "코스타리카": "Costa Rica", "파나마": "Panama", "온두라스": "Honduras",
    "과테말라": "Guatemala", "엘살바도르": "El Salvador", "니카라과": "Nicaragua", "자메이카": "Jamaica", "아이티": "Haiti",
    "트리니다드토바고": "Trinidad and Tobago", "트리니다드 토바고": "Trinidad and Tobago", "쿠바": "Cuba", "퀴라소": "Curaçao",
    "도미니카공화국": "Dominican Republic", "도미니카 공화국": "Dominican Republic", "수리남": "Suriname", "가이아나": "Guyana",
    "푸에르토리코": "Puerto Rico", "벨리즈": "Belize", "바하마": "Bahamas", "버뮤다": "Bermuda", "그레나다": "Grenada", "바베이도스": "Barbados",
    "브라질": "Brazil", "아르헨티나": "Argentina", "우루과이": "Uruguay", "파라과이": "Paraguay", "칠레": "Chile", "콜롬비아": "Colombia",
    "에콰도르": "Ecuador", "페루": "Peru", "볼리비아": "Bolivia", "베네수엘라": "Venezuela",
    "잉글랜드": "England", "스코틀랜드": "Scotland", "웨일스": "Wales", "북아일랜드": "Northern Ireland", "아일랜드": "Republic of Ireland",
    "아일랜드공화국": "Republic of Ireland", "프랑스": "France", "독일": "Germany", "스페인": "Spain", "이탈리아": "Italy", "포르투갈": "Portugal",
    "네덜란드": "Netherlands", "벨기에": "Belgium", "스위스": "Switzerland", "오스트리아": "Austria", "덴마크": "Denmark", "스웨덴": "Sweden",
    "노르웨이": "Norway", "핀란드": "Finland", "아이슬란드": "Iceland", "폴란드": "Poland", "체코": "Czech Republic", "슬로바키아": "Slovakia",
    "헝가리": "Hungary", "루마니아": "Romania", "불가리아": "Bulgaria", "그리스": "Greece", "튀르키예": "Turkey", "터키": "Turkey",
    "크로아티아": "Croatia", "세르비아": "Serbia", "슬로베니아": "Slovenia", "보스니아헤르체고비나": "Bosnia and Herzegovina",
    "보스니아 헤르체고비나": "Bosnia and Herzegovina", "몬테네그로": "Montenegro", "북마케도니아": "North Macedonia", "알바니아": "Albania",
    "코소보": "Kosovo", "우크라이나": "Ukraine", "러시아": "Russia", "벨라루스": "Belarus", "몰도바": "Moldova", "조지아": "Georgia",
    "아르메니아": "Armenia", "아제르바이잔": "Azerbaijan", "이스라엘": "Israel", "키프로스": "Cyprus", "몰타": "Malta",
    "룩셈부르크": "Luxembourg", "리투아니아": "Lithuania", "라트비아": "Latvia", "에스토니아": "Estonia", "페로제도": "Faroe Islands",
    "안도라": "Andorra", "산마리노": "San Marino", "리히텐슈타인": "Liechtenstein", "지브롤터": "Gibraltar",
    "모로코": "Morocco", "알제리": "Algeria", "튀니지": "Tunisia", "이집트": "Egypt", "리비아": "Libya", "나이지리아": "Nigeria",
    "가나": "Ghana", "세네갈": "Senegal", "카메룬": "Cameroon", "코트디부아르": "Ivory Coast", "말리": "Mali", "부르키나파소": "Burkina Faso",
    "남아프리카공화국": "South Africa", "남아공": "South Africa", "케냐": "Kenya", "우간다": "Uganda", "탄자니아": "Tanzania",
    "에티오피아": "Ethiopia", "잠비아": "Zambia", "짐바브웨": "Zimbabwe", "앙골라": "Angola", "콩고민주공화국": "DR Congo",
    "콩고": "Congo", "가봉": "Gabon", "기니": "Guinea", "베냉": "Benin", "토고": "Togo", "카보베르데": "Cape Verde", "수단": "Sudan",
    "모잠비크": "Mozambique", "마다가스카르": "Madagascar", "모리타니": "Mauritania", "감비아": "Gambia", "적도기니": "Equatorial Guinea",
}


def _norm(s: str) -> str:
    return "".join(str(s).split()).replace("·", "")


_KO_N = {_norm(k): v for k, v in KO.items()}


def english(name: str) -> str | None:
    return _KO_N.get(_norm(name))


def _k(tournament: str) -> float:
    t = tournament.lower()
    if t == "friendly":
        return 20
    if "qualification" in t or "nations league" in t:
        return 40
    if t == "fifa world cup":
        return 60
    if any(x in t for x in ("uefa euro", "copa américa", "african cup of nations", "afc asian cup", "gold cup", "confederations cup")):
        return 50
    return 30


def _gmult(d: int) -> float:
    d = abs(d)
    return 1.0 if d <= 1 else 1.5 if d == 2 else (11 + d) / 8


def build(text: str) -> dict:
    ratings: dict[str, float] = {}
    games: dict[str, int] = {}
    last: dict[str, str] = {}
    table: dict[str, list[int]] = {}
    for r in csv.DictReader(io.StringIO(text)):
        try:
            hs, as_ = int(r["home_score"]), int(r["away_score"])
        except (TypeError, ValueError):
            continue  # 아직 안 끝난 경기
        h, a = r["home_team"], r["away_team"]
        rh, ra = ratings.get(h, 1500.0), ratings.get(a, 1500.0)
        neutral = str(r.get("neutral", "")).upper() == "TRUE"
        dr = rh - ra + (0 if neutral else 100)
        if r["date"] >= SINCE and games.get(h, 0) >= 10 and games.get(a, 0) >= 10:
            row = table.setdefault(str(int(dr // BW)), [0] * (4 + 2 * DIFF_MAX + 1 + GOAL_MAX + 1))
            row[0] += 1
            row[1 if hs > as_ else 2 if hs == as_ else 3] += 1
            row[4 + DIFF_MAX + max(-DIFF_MAX, min(DIFF_MAX, hs - as_))] += 1
            row[4 + 2 * DIFF_MAX + 1 + min(hs + as_, GOAL_MAX)] += 1
        we = 1 / (10 ** (-dr / 400) + 1)
        w = 1.0 if hs > as_ else 0.5 if hs == as_ else 0.0
        delta = _k(r.get("tournament", "")) * _gmult(hs - as_) * (w - we)
        ratings[h], ratings[a] = rh + delta, ra - delta
        games[h], games[a] = games.get(h, 0) + 1, games.get(a, 0) + 1
        last[h] = last[a] = r["date"]
    return {"updated": config.today_kst(), "bw": BW, "dm": DIFF_MAX, "gm": GOAL_MAX,
            "teams": {t: [round(ratings[t], 1), games[t], last[t]] for t in ratings}, "table": table}


def backfill(force: bool = False) -> bool:
    if config.DEMO:
        return False
    cur = read_json(PATH, {}) or {}
    if not force and cur.get("updated") and (date.fromisoformat(config.today_kst()) - date.fromisoformat(cur["updated"])).days < 7:
        return False
    try:
        r = http("GET", URL, retries=2, timeout=90)
        book = build(r.content.decode("utf-8-sig", "replace"))
        if len(book["teams"]) < 150:
            raise ValueError("팀 수가 너무 적음")
        write_json(PATH, book)
        log.info("국가대표 레이팅 %d팀 갱신", len(book["teams"]))
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("국가대표 기록 실패: %s", type(e).__name__)
        return False


_CACHE: dict | None = None


def load() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = read_json(PATH, {}) or {}
    return _CACHE


def stat(home: str, away: str, book: dict | None = None) -> dict | None:
    """두 국가대표의 레이팅과, 레이팅 차가 비슷했던 2000년 이후 A매치의 실제 결과 분포."""
    b = book if book is not None else load()
    teams = b.get("teams") or {}
    eh, ea = english(home), english(away)
    if not eh or not ea or eh not in teams or ea not in teams:
        return None
    (rh, gh, _), (ra, ga, _) = teams[eh], teams[ea]
    if min(gh, ga) < 30:
        return None  # A매치 기록이 적은 팀은 레이팅을 믿지 않는다
    dr = rh - ra + 100  # 베트맨은 중립 여부를 주지 않으므로 홈 경기로 본다
    i = int(dr // b.get("bw", BW))
    t = b.get("table") or {}
    acc = None
    for rad in range(0, 4):
        acc = None
        for k in range(i - rad, i + rad + 1):
            row = t.get(str(k))
            if row:
                acc = list(row) if acc is None else [x + y for x, y in zip(acc, row)]
        if acc and acc[0] >= 300:
            break
    if not acc or acc[0] < 100:
        return None
    dm, gm = b.get("dm", DIFF_MAX), b.get("gm", GOAL_MAX)
    n = acc[0]
    # 극단 구간(표본 적음)에서 0%·100% 로 단정하지 않게 라플라스 보정
    return {"n": n, "H": (acc[1] + 1) / (n + 3), "D": (acc[2] + 1) / (n + 3), "A": (acc[3] + 1) / (n + 3),
            "diff": acc[4:4 + 2 * dm + 1], "goals": acc[4 + 2 * dm + 1:4 + 2 * dm + 1 + gm + 1], "dm": dm,
            "rh": round(rh), "ra": round(ra), "en": (eh, ea)}


def market_probs(st: dict, market: str, line: float | None, keys: set[str]) -> dict[str, float] | None:
    if market == "1X2" and keys == {"H", "D", "A"}:
        return {k: st[k] for k in ("H", "D", "A")}
    if market == "WL" and keys == {"H", "A"}:
        t = st["H"] + st["A"]
        return {"H": st["H"] / t, "A": st["A"] / t}
    if market == "HANDICAP" and line is not None:
        o = {"H": 0, "D": 0, "A": 0}
        for idx, c in enumerate(st["diff"]):
            v = idx - st["dm"] + line
            o["H" if v > 0 else "D" if v == 0 else "A"] += c
        if "D" not in keys:
            o.pop("D")
        t = sum(o.values())
        res = {k: v / t for k, v in o.items()} if t else None
        return res if res and set(res) == keys else None
    if market == "OU" and line is not None and keys == {"O", "U"}:
        n = sum(st["goals"])
        over = sum(c for g, c in enumerate(st["goals"]) if g > line)
        push = sum(c for g, c in enumerate(st["goals"]) if g == line)
        return {"O": over / (n - push), "U": 1 - over / (n - push)} if n - push else None
    return None
