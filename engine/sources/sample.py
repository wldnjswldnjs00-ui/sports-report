"""데모 데이터. DEMO=1 일 때만 쓰인다. 화면에 '샘플' 표시가 반드시 붙는다.

실제 경기처럼 보이지 않도록 팀 이름은 가상의 이름을 쓴다.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .. import config

TEAMS = {
    ("soccer", "가상리그A"): ["북항FC", "서강유나이티드", "남천시티", "동원로버스", "청람FC", "백운SC", "해솔유나이티드", "송림FC"],
    ("soccer", "가상리그B"): ["리버턴", "애쉬필드", "노스게이트", "웨스트모어", "브룩데일", "핀우드"],
    ("basketball", "가상농구"): ["한빛 레이더스", "금강 호크스", "태백 베어스", "누리 썬더", "가람 나이츠", "솔빛 스타즈"],
    ("baseball", "가상야구"): ["북부 이글스", "남부 웨일스", "동부 타이탄즈", "서부 팬서스"],
}


def _odds(p: dict[str, float], payout: float, rng: random.Random) -> dict[str, float]:
    return {k: round(max(1.03, payout / v * rng.uniform(0.97, 1.03)), 2) for k, v in p.items()}


def generate(day: str, seed: int | None = None) -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    """(markets, reference_probs, results) 반환. 결과는 과거 날짜 채점 데모용."""
    rng = random.Random(seed if seed is not None else int(day.replace("-", "")))
    base = datetime.fromisoformat(day + "T13:00:00+09:00")
    markets, ref, results = [], {}, {}
    no = 1
    for (sport, league), teams in TEAMS.items():
        t = teams[:]
        rng.shuffle(t)
        for i in range(0, len(t) - 1, 2):
            home, away = t[i], t[i + 1]
            strength = rng.gauss(0.12, 0.55)
            ko = (base + timedelta(minutes=30 * rng.randint(0, 18))).isoformat(timespec="minutes")
            if sport == "soccer":
                ph = 1 / (1 + pow(10, -strength))
                d = 0.27 * (1 - abs(ph - 0.5))
                p = {"H": ph * (1 - d), "D": d, "A": (1 - ph) * (1 - d)}
                mk = "1X2"
            else:
                ph = 1 / (1 + pow(10, -strength * 0.8))
                p = {"H": ph, "A": 1 - ph}
                mk = "WL"
            true_p = {k: v for k, v in p.items()}
            noisy = {k: max(0.02, v + rng.gauss(0, 0.035)) for k, v in p.items()}
            s = sum(noisy.values())
            noisy = {k: v / s for k, v in noisy.items()}
            mid = f"sample:{day}:{no}"
            markets.append({
                "id": mid, "source": "sample", "pool": "proto", "round": "샘플", "game_no": no,
                "sport": sport, "league": league, "kickoff": ko, "home": home, "away": away,
                "market": mk, "line": None, "odds": _odds(noisy, rng.uniform(0.82, 0.9), rng),
            })
            ref[mid] = {k: v for k, v in true_p.items()}
            r = rng.random()
            acc = 0.0
            outcome = "H"
            for k, v in true_p.items():
                acc += v
                if r <= acc:
                    outcome = k
                    break
            if sport == "soccer":
                hs, as_ = {"H": (2, 1), "D": (1, 1), "A": (0, 1)}[outcome]
            elif sport == "basketball":
                hs, as_ = (88, 80) if outcome == "H" else (79, 85)
            else:
                hs, as_ = (5, 3) if outcome == "H" else (2, 4)
            results[mid] = {"home_score": hs, "away_score": as_, "status": "FT", "src": "sample"}
            no += 1
    return markets, ref, results


def is_demo() -> bool:
    return config.DEMO
