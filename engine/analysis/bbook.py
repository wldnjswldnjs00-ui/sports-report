"""베트맨 배당 기록 구도표(리그별).

해외 배당 기록이 없는 리그(KBL·WKBL·KOVO·K리그·KBO 등)는 베트맨 지난 회차 기록으로
'베트맨 배당이 이렇게 붙었던 경기는 실제로 어떻게 끝났나'를 센다.

- 키: 리그 묶음(kbl, wkbl, kovo_m …)과 종목 전체(all_basketball …)
- 마켓별(WL·HANDICAP·OU) · 왼칸 공정확률 구간(0.05) → [경기 수, 왼칸, 무, 오른칸]
  언더오버는 오버 공정확률 구간 → [경기 수, 오버, 0, 언더] (기준점과 상관없이 확률로 묶는다)
공정확률 = 배당 역수를 합이 1이 되게 나눈 값(발행처 몫 제거).
"""
from __future__ import annotations

from typing import Any

W = 0.05
NEED = 40          # 한 칸 표본이 이보다 적으면 이웃 칸까지 넓힌다
MIN_GROUP = 25     # 리그 묶음 표본이 이보다 적으면 종목 전체 기록으로 계산

# 페이지·분석에 보여줄 리그 묶음 (해외 기록이 이미 있는 NBA·MLB·유럽 축구는 베트맨 묶음에서 뺀다)
GROUPS: dict[str, dict[str, str]] = {
    "kbl": {"sport": "basketball", "label": "KBL"},
    "wkbl": {"sport": "basketball", "label": "WKBL"},
    "bk_intl": {"sport": "basketball", "label": "국제 농구"},
    "kovo_m": {"sport": "volleyball", "label": "KOVO 남자"},
    "kovo_w": {"sport": "volleyball", "label": "KOVO 여자"},
    "vb_intl": {"sport": "volleyball", "label": "국제 배구"},
    "kleague": {"sport": "soccer", "label": "K리그"},
    "jleague": {"sport": "soccer", "label": "J리그"},
    "soc_intl": {"sport": "soccer", "label": "A매치·국제 대회"},
    "soc_etc": {"sport": "soccer", "label": "그 밖의 리그"},
    "kbo": {"sport": "baseball", "label": "KBO"},
    "npb": {"sport": "baseball", "label": "NPB"},
}
SPORT_ALL = {"basketball": "농구 전체", "volleyball": "배구 전체", "soccer": "축구 전체", "baseball": "야구 전체"}
EUROPE = ("잉글랜드", "스페인", "이탈리아", "독일", "프랑스", "네덜란드", "포르투갈", "스코틀랜드", "벨기에", "튀르키예", "터키", "그리스", "UEFA")
INTL = ("국제친선", "네이션스", "월드컵", "아시안게임", "아시안컵", "유로", "코파 아메리카", "골드컵", "올림픽", "선수권", "예선")


def group_of(sport: str, league: str) -> str | None:
    lg = str(league or "").replace(" ", "")
    if sport == "basketball":
        if lg.startswith("WKBL") or "박신자컵" in lg:
            return "wkbl"
        if lg.startswith("KBL"):
            return "kbl"
        if "NBA" in lg or "WNBA" in lg:
            return None
        return "bk_intl"
    if sport == "volleyball":
        if "KOVO" in lg:
            return "kovo_w" if "여자" in lg else "kovo_m"
        return "vb_intl"
    if sport == "soccer":
        if lg.startswith("K리그"):
            return "kleague"
        if lg.startswith("J1") or lg.startswith("J2") or lg.startswith("J3") or "J리그" in lg or "일본J" in lg:
            return "jleague"
        if any(k.replace(" ", "") in lg for k in INTL):
            return "soc_intl"
        if any(k in lg for k in EUROPE):
            return None
        return "soc_etc"
    if sport == "baseball":
        if lg.startswith("KBO"):
            return "kbo"
        if lg.startswith("NPB"):
            return "npb"
        return None
    return None


def _bin(p: float) -> int:
    return max(0, min(round(1 / W) - 1, int(p / W)))


def _fair(odds: list[float]) -> list[float] | None:
    if any(not o or o <= 1 for o in odds):
        return None
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [v / s for v in inv]


def _cell(row: list) -> tuple[str, int, list[int]] | None:
    """행 하나 → (마켓, 구간, [1, 왼칸, 무, 오른칸]). OU 는 [1, 오버, 0, 언더] 로 바꾼다."""
    try:
        sport, league, mk, line, w, d, l, code, under_first = row[0], row[1], row[2], row[3], row[4], row[5], row[6], int(row[7]), row[9]
    except (IndexError, TypeError, ValueError):
        return None
    if mk == "1X2":
        mk = "WL"
    if mk not in ("WL", "HANDICAP", "OU"):
        return None
    odds = [w, d, l] if d and d > 1 else [w, l]
    f = _fair(odds)
    if not f:
        return None
    hit = [0, 0, 0]
    hit[code] = 1
    if mk == "OU":
        p_over = f[-1] if under_first else f[0]
        over = hit[2] if under_first else hit[0]
        under = hit[0] if under_first else hit[2]
        return mk, _bin(p_over), [1, over, 0, under]
    return mk, _bin(f[0]), [1, hit[0], hit[1], hit[2]]


def build(rows: list[list]) -> dict[str, Any]:
    data: dict[str, dict[str, dict[str, list[int]]]] = {}
    count: dict[str, dict[str, int]] = {}
    for r in rows:
        c = _cell(r)
        if not c:
            continue
        mk, b, v = c
        sport = r[0]
        keys = ["all_" + sport]
        g = group_of(sport, r[1])
        if g:
            keys.append(g)
        for k in keys:
            t = data.setdefault(k, {}).setdefault(mk, {})
            cur = t.setdefault(str(b), [0, 0, 0, 0])
            for i in range(4):
                cur[i] += v[i]
            count.setdefault(k, {}).setdefault(mk, 0)
            count[k][mk] += 1
    groups = {k: {**g, "n": count.get(k, {})} for k, g in GROUPS.items()}
    for sp, lab in SPORT_ALL.items():
        groups["all_" + sp] = {"sport": sp, "label": lab, "n": count.get("all_" + sp, {})}
    return {"w": W, "need": NEED, "min_group": MIN_GROUP, "groups": groups, "data": data}


def lookup(book: dict, sport: str, league: str, market: str, odds: dict[str, float], key: str) -> dict | None:
    """오늘 경기 한 마켓의 선택 key 에 대해, 베트맨 배당이 비슷했던 과거 경기의 실제 적중률."""
    if not book or not odds:
        return None
    mk = "WL" if market == "1X2" else market
    if mk not in ("WL", "HANDICAP", "OU"):
        return None
    if mk == "OU":
        o, u = odds.get("O"), odds.get("U")
        f = _fair([o, u]) if o and u else None
        if not f:
            return None
        b, idx = _bin(f[0]), (1 if key == "O" else 3)
        imp = f[0] if key == "O" else f[1]
    else:
        arr = [odds.get("H"), odds.get("D"), odds.get("A")] if odds.get("D") else [odds.get("H"), odds.get("A")]
        f = _fair(arr)
        if not f:
            return None
        b = _bin(f[0])
        idx = {"H": 1, "D": 2, "A": 3}.get(key)
        if idx is None:
            return None
        imp = f[0] if key == "H" else (f[-1] if key == "A" else f[1])
    g = group_of(sport, league)
    for k in ([g] if g else []) + ["all_" + sport]:
        t = ((book.get("data") or {}).get(k) or {}).get(mk) or {}
        tot = sum(v[0] for v in t.values())
        if k == g and tot < MIN_GROUP:
            continue
        for r in range(0, 4):
            acc = [0, 0, 0, 0]
            for j in range(b - r, b + r + 1):
                v = t.get(str(j))
                if v:
                    acc = [acc[i] + v[i] for i in range(4)]
            if acc[0] >= NEED:
                label = (book.get("groups") or {}).get(k, {}).get("label") or k
                return {"hit": round(acc[idx] / acc[0], 4), "n": acc[0], "imp": round(imp, 4), "group": label}
    return None
