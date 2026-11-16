"""베트맨 한글 표기 → 영문 팀명 매핑, 리그 → The Odds API 종목 키.

여기 없는 팀은 data/aliases.json 에 {"한글표기": "English Name"} 로 추가하면 된다.
매칭이 안 된 경기는 해외 배당 없이 베트맨 배당 + Elo 로만 분석된다(에러 아님).
"""
from __future__ import annotations

from .. import config
from ..util import norm_team, read_json

LEAGUE_TO_ODDS_API = {
    "EPL": "soccer_epl", "프리미어리그": "soccer_epl", "잉글랜드프리미어리그": "soccer_epl",
    "EFL챔": "soccer_efl_champ", "챔피언십": "soccer_efl_champ",
    "라리가": "soccer_spain_la_liga", "프리메라": "soccer_spain_la_liga",
    "세리에A": "soccer_italy_serie_a", "세리에": "soccer_italy_serie_a",
    "분데스리가": "soccer_germany_bundesliga", "분데스": "soccer_germany_bundesliga",
    "리그1": "soccer_france_ligue_one", "리그앙": "soccer_france_ligue_one",
    "에레디비": "soccer_netherlands_eredivisie",
    "UCL": "soccer_uefa_champs_league", "챔스": "soccer_uefa_champs_league",
    "UEL": "soccer_uefa_europa_league", "유로파": "soccer_uefa_europa_league",
    "K리그1": "soccer_korea_kleague1", "J리그": "soccer_japan_j_league", "J1리그": "soccer_japan_j_league",
    "NBA": "basketball_nba", "NHL": "icehockey_nhl", "MLB": "baseball_mlb", "NFL": "americanfootball_nfl",
    "UNL": "soccer_uefa_nations_league", "네이션스리그": "soccer_uefa_nations_league",
}

SEED = {
    # EPL
    "맨체스C": "Manchester City", "맨시티": "Manchester City", "맨체스U": "Manchester United", "맨유": "Manchester United",
    "리버풀": "Liverpool", "아스널": "Arsenal", "첼시": "Chelsea", "토트넘": "Tottenham Hotspur",
    "뉴캐슬": "Newcastle United", "애스턴빌": "Aston Villa", "A빌라": "Aston Villa", "브라이턴": "Brighton and Hove Albion",
    "웨스트햄": "West Ham United", "울버햄튼": "Wolverhampton Wanderers", "울버햄턴": "Wolverhampton Wanderers",
    "크리스털": "Crystal Palace", "C팰리스": "Crystal Palace", "에버턴": "Everton", "풀럼": "Fulham", "본머스": "Bournemouth",
    "브렌트퍼": "Brentford", "브렌트포": "Brentford", "노팅엄": "Nottingham Forest", "리즈": "Leeds United",
    "번리": "Burnley", "선덜랜드": "Sunderland",
    # 라리가 / 세리에 / 분데스 일부
    "레알마드": "Real Madrid", "바르셀로": "Barcelona", "AT마드리": "Atlético Madrid", "세비야": "Sevilla",
    "인테르": "Inter Milan", "AC밀란": "AC Milan", "유벤투스": "Juventus", "나폴리": "Napoli", "AS로마": "AS Roma",
    "바이에른": "Bayern Munich", "도르트문": "Borussia Dortmund", "레버쿠젠": "Bayer Leverkusen", "라이프치": "RB Leipzig",
    "파리SG": "Paris Saint Germain", "PSG": "Paris Saint Germain",
    # NBA
    "보스턴": "Boston Celtics", "LA레이커": "Los Angeles Lakers", "LA클리퍼": "Los Angeles Clippers",
    "골든스테": "Golden State Warriors", "덴버": "Denver Nuggets", "피닉스": "Phoenix Suns", "밀워키": "Milwaukee Bucks",
    "필라델피": "Philadelphia 76ers", "뉴욕닉스": "New York Knicks", "브루클린": "Brooklyn Nets", "마이애미": "Miami Heat",
    "시카고": "Chicago Bulls", "클리블랜": "Cleveland Cavaliers", "댈러스": "Dallas Mavericks", "휴스턴": "Houston Rockets",
    "멤피스": "Memphis Grizzlies", "뉴올리언": "New Orleans Pelicans", "샌안토니": "San Antonio Spurs",
    "오클라호": "Oklahoma City Thunder", "미네소타": "Minnesota Timberwolves", "유타": "Utah Jazz", "포틀랜드": "Portland Trail Blazers",
    "새크라멘": "Sacramento Kings", "애틀랜타": "Atlanta Hawks", "샬럿": "Charlotte Hornets", "올랜도": "Orlando Magic",
    "워싱턴": "Washington Wizards", "디트로이": "Detroit Pistons", "인디애나": "Indiana Pacers", "토론토": "Toronto Raptors",
}


def alias_map() -> dict[str, str]:
    m = {norm_team(k): v for k, v in SEED.items()}
    extra = read_json(config.DATA / "aliases.json", {}) or {}
    m.update({norm_team(k): v for k, v in extra.items()})
    return m


def english(name: str, amap: dict[str, str]) -> str:
    return amap.get(norm_team(name), name)


def odds_api_key_for(league: str) -> str | None:
    return LEAGUE_TO_ODDS_API.get(league.replace(" ", ""))
