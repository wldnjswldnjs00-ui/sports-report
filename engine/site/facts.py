"""AI 검색·검색엔진이 인용하기 좋은 '짧은 질문과 답' 페이지(/facts/)와 llms.txt.

모두 저장된 기록으로 매 빌드마다 다시 계산한다(사람 손 없음). 표본이 적은 리그는 넣지 않는다.
- 리그별: 홈 승률, 정배 적중률, 배당 3.0 이상 역배 적중률, 평균 합계, 언더오버 기준점 대비 오버 비율
- 사이트: 분석 방법, 지금까지의 적중 기록
"""
from __future__ import annotations

from collections import defaultdict

MIN_GAMES = 120


def _league_stats(rows: list[list]) -> list[dict]:
    """베트맨 지난 회차 행 → 리그별 통계. 행: [종목, 리그, 마켓, 기준점, 왼, 무, 오른, 결과칸, 킥오프ms, 왼칸언더, 홈, 원정, 홈점수, 원정점수]"""
    g = defaultdict(lambda: {"n": 0, "home": 0, "fav_n": 0, "fav_hit": 0, "dog_n": 0, "dog_hit": 0, "tot": 0, "ou_n": 0, "ou_over": 0, "sport": ""})
    for r in rows:
        try:
            sport, lg, mk, line, l, d, rr, res, _ko, under_left, _h, _a, hs, as_ = r[:14]
        except ValueError:
            continue
        x = g[lg]
        x["sport"] = sport
        if mk in ("1X2", "WL") and hs is not None and as_ is not None:
            x["n"] += 1
            x["home"] += hs > as_
            x["tot"] += hs + as_
            if l and rr and l > 1 and rr > 1:
                fav_home = l < rr
                won_home, won_away = hs > as_, as_ > hs
                x["fav_n"] += 1
                x["fav_hit"] += won_home if fav_home else won_away
                dog_odds = rr if fav_home else l
                if dog_odds >= 3.0:
                    x["dog_n"] += 1
                    x["dog_hit"] += won_away if fav_home else won_home
        elif mk == "OU" and res in (0, 2):
            x["ou_n"] += 1
            over_left = not under_left
            x["ou_over"] += (res == 0) == over_left
    out = []
    for lg, x in g.items():
        if x["n"] < MIN_GAMES:
            continue
        out.append({"league": lg, "sport": x["sport"], "n": x["n"], "home": x["home"] / x["n"],
                    "fav": x["fav_hit"] / x["fav_n"] if x["fav_n"] else None, "fav_n": x["fav_n"],
                    "dog": x["dog_hit"] / x["dog_n"] if x["dog_n"] >= 30 else None, "dog_n": x["dog_n"],
                    "avg_total": x["tot"] / x["n"], "over": x["ou_over"] / x["ou_n"] if x["ou_n"] >= 50 else None, "ou_n": x["ou_n"]})
    order = {"baseball": 0, "soccer": 1, "basketball": 2, "volleyball": 3}
    out.sort(key=lambda s: (order.get(s["sport"], 9), -s["n"]))
    return out


UNIT = {"soccer": "골", "baseball": "점", "basketball": "점", "volleyball": "세트"}


def _p(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.1f}%"


def build(rows: list[list], perf: dict | None) -> dict:
    """{"leagues": [{league, qa:[(질문, 답)]}], "site": [(질문, 답)], "faq_ld": JSON-LD}"""
    leagues = []
    for s in _league_stats(rows):
        u = UNIT.get(s["sport"], "점")
        lg = s["league"]
        qa = [(f"{lg}에서 홈팀은 얼마나 이기나요?", f"베트맨 발매 {lg} {s['n']:,}경기에서 홈팀 승률은 {_p(s['home'])}입니다."),
              (f"{lg} 정배는 얼마나 맞나요?", f"두 팀 중 배당이 낮은 정배가 이긴 비율은 {_p(s['fav'])}입니다({s['fav_n']:,}경기, 베트맨 배당 기준).")]
        if s["dog"] is not None:
            qa.append((f"{lg}에서 배당 3.0 이상 역배는 얼마나 맞나요?", f"배당 3.0 이상 역배가 이긴 비율은 {_p(s['dog'])}입니다({s['dog_n']:,}경기)."))
        qa.append((f"{lg} 한 경기 평균 합계는 얼마인가요?", f"두 팀 합계는 경기당 평균 {s['avg_total']:.1f}{u}입니다."))
        if s["over"] is not None:
            qa.append((f"{lg} 언더오버는 어느 쪽이 더 많이 나오나요?", f"베트맨 언더오버 기준점을 넘긴(오버) 경기는 {_p(s['over'])}입니다({s['ou_n']:,}경기)."))
        leagues.append({"league": lg, "sport": s["sport"], "n": s["n"], "qa": qa})
    site = [("스포츠분석.kr은 어떤 사이트인가요?",
             "베트맨 프로토 승부식 발매 경기를 해외 배당과 과거 기록으로 분석해, 경기별 확률·예상 스코어·조합을 매일 자동으로 공개하는 개인 운영 분석 사이트입니다. 구매 대행이나 픽 판매는 하지 않습니다."),
            ("확률은 어떻게 계산하나요?",
             "해외 배당에서 발행처 몫을 걷어낸 확률을 기본으로, 레이팅과 과거 배당 기록, 최근 경기 내용을 함께 반영합니다. 결과가 나오면 매일 자동으로 채점하고 그 기록으로 계산 방식을 스스로 고칩니다."),
            ("분석은 언제 갱신되나요?", "매일 정해진 시각에 자동으로 갱신됩니다. 다음 구매일 분석은 오후 7시에 공개됩니다.")]
    pk = ((perf or {}).get("picks") or {}).get("all") or {}
    if pk.get("n"):
        site.append(("지금까지 적중률은 얼마인가요?", f"지금까지 채점한 추천 {pk['n']:,}개의 적중률은 {_p(pk.get('hit_rate'))}이고, 모델이 미리 계산한 기대 적중률은 {_p(pk.get('expected'))}입니다."))
    site.append(("누가 이용할 수 있나요?", "체육진흥투표권은 만 19세 이상만 구매할 수 있고, 베트맨 공식 사이트와 공식 판매점에서만 구매할 수 있습니다."))
    allqa = site + [q for L in leagues for q in L["qa"]]
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in allqa[:60]]}
    return {"leagues": leagues, "site": site, "faq_ld": faq_ld}


def llms_txt(site_url: str, name: str, facts: dict, knowhow: list[dict] | None = None) -> str:
    """AI 도구용 안내(llms.txt 형식: 제목, 한 줄 요약, 주요 페이지 목록)."""
    lines = [f"# {name}", "",
             "> 베트맨 프로토 승부식 발매 경기를 해외 배당과 과거 기록으로 분석해 경기별 확률, 예상 스코어, 조합을 매일 자동으로 공개하는 한국어 스포츠 분석 사이트. "
             "결과는 매일 자동 채점해 공개한다. 만 19세 이상, 베트맨 공식 채널 구매 기준의 참고용 분석.", "",
             "## 주요 페이지",
             f"- [오늘의 분석]({site_url}/): 오늘 구매일 경기별 확률·추천·전략별 조합(매일 갱신)",
             f"- [경기 분석]({site_url}/analysis/): 경기별 예상 스코어와 두 팀 비교 숫자",
             f"- [리그·순위]({site_url}/leagues/): 리그별 순위와 팀 기록",
             f"- [노하우]({site_url}/knowhow/): 기록으로 계산한 분석 노하우·리그별 특징 글",
             f"- [숫자로 보는 리그]({site_url}/facts/): 리그별 홈 승률·정배 적중률·평균 합계 질문과 답",
             f"- [성과]({site_url}/performance/): 추천 적중 기록과 확률 보정",
             f"- [분석 방법]({site_url}/method/): 확률 계산 방법", "",
             "## 리그별 핵심 숫자"]
    for L in facts.get("leagues", [])[:20]:
        for q, a in L["qa"][:2]:
            lines.append(f"- {q} {a}")
    if knowhow:
        lines += ["", "## 노하우 글(일부)"]
        for k in knowhow[:30]:
            lines.append(f"- [{k['title']}]({site_url}{k['url']})")
    lines += ["", "## 출처", "- 발매 경기·배당·결과: 베트맨 공개 정보", "- 해외 배당: The Odds API, football-data.co.uk 공개 기록", ""]
    return "\n".join(lines)
