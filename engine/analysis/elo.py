"""종목별 Elo 레이팅.

결과가 채점될 때마다 갱신되어 data/state/elo.json 에 쌓인다.
표본이 적은 팀은 확률 결합에서 가중치를 0 으로 둔다(신뢰할 수 없는 정보는 쓰지 않는다).
"""
from __future__ import annotations

import math
from typing import Any

from .. import config
from ..util import norm_team, read_json, write_json

PATH = config.STATE / "elo.json"

# 종목별 파라미터: K 계수, 홈 어드밴티지(Elo 점수), 무승부 기본 비율
PARAMS = {
    "soccer": {"k": 22, "home": 60, "draw": 0.27},
    "basketball": {"k": 18, "home": 70, "draw": 0.0},
    "baseball": {"k": 6, "home": 20, "draw": 0.0},
    "volleyball": {"k": 20, "home": 40, "draw": 0.0},
    "hockey": {"k": 10, "home": 35, "draw": 0.0},
    "football": {"k": 20, "home": 55, "draw": 0.0},
    "etc": {"k": 15, "home": 40, "draw": 0.0},
}
MIN_GAMES = 8


class Elo:
    def __init__(self, data: dict[str, Any] | None = None):
        self.data = data or {}

    @classmethod
    def load(cls) -> "Elo":
        return cls(read_json(PATH, {}))

    def save(self) -> None:
        write_json(PATH, self.data)

    def _rec(self, sport: str, team: str) -> dict[str, Any]:
        bucket = self.data.setdefault(sport, {})
        return bucket.setdefault(norm_team(team), {"r": 1500.0, "n": 0, "name": team})

    def games(self, sport: str, team: str) -> int:
        return self.data.get(sport, {}).get(norm_team(team), {}).get("n", 0)

    def rating(self, sport: str, team: str) -> float:
        return self.data.get(sport, {}).get(norm_team(team), {}).get("r", 1500.0)

    def expected(self, sport: str, home: str, away: str, neutral: bool = False) -> float:
        p = PARAMS.get(sport, PARAMS["etc"])
        diff = self.rating(sport, home) - self.rating(sport, away) + (0 if neutral else p["home"])
        return 1 / (1 + 10 ** (-diff / 400))

    def probs(self, sport: str, home: str, away: str, market: str) -> dict[str, float] | None:
        """승무패/승패 확률. 표본 부족이면 None."""
        if min(self.games(sport, home), self.games(sport, away)) < MIN_GAMES:
            return None
        e = self.expected(sport, home, away)
        if market == "1X2":
            base = PARAMS.get(sport, PARAMS["etc"])["draw"] or 0.25
            # 전력 차가 클수록 무승부 확률이 줄어든다.
            d = base * math.exp(-((e - 0.5) ** 2) / 0.08)
            return {"H": e * (1 - d), "D": d, "A": (1 - e) * (1 - d)}
        if market == "WL":
            return {"H": e, "A": 1 - e}
        return None

    def update(self, sport: str, home: str, away: str, score: float, margin: float = 0.0) -> None:
        """score: 홈 기준 1(승) 0.5(무) 0(패). margin: 점수 차(가중용)."""
        p = PARAMS.get(sport, PARAMS["etc"])
        e = self.expected(sport, home, away)
        mult = 1.0 + (math.log1p(abs(margin)) * 0.35 if margin else 0.0)
        delta = p["k"] * mult * (score - e)
        h, a = self._rec(sport, home), self._rec(sport, away)
        h["r"] += delta
        a["r"] -= delta
        h["n"] += 1
        a["n"] += 1
