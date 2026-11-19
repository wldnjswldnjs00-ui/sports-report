"""노하우 '연구·심리': 잘 알려진 연구 결과와 실험을 소개하고, 가능한 것은 이 사이트의 기록으로 직접 확인한다.

- 연구 소개 문단은 고정이지만, '우리 기록으로 보면' 숫자는 매 빌드마다 저장된 기록으로 다시 계산한다(사람 손 없음).
- 시뮬레이션 실험은 난수 씨앗을 고정해 매번 같은 조건으로 돌린다(기록이 늘면 입력 확률이 바뀌어 결과도 바뀐다).
- 인용한 연구는 저자·연도·학술지를 적고, 논문에 없는 숫자를 지어내지 않는다.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict

from . import knowhow as KH

CAT = "연구·심리"


def _A(slug, title, lead, secs):
    return KH.A(f"rs-{slug}", title, CAT, lead, secs, tags=["연구", "심리"])


def _odds_buckets(games):
    """모든 선택(승·무·패)을 배당 구간으로 나눠, 그 구간을 전부 샀을 때의 적중률·돌려받는 비율."""
    edges = [(1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 10.0), (10.0, 100.0)]
    acc = {e: [0, 0, 0.0] for e in edges}
    for g in games:
        for i, o in enumerate(g["o"]):
            if not o or o <= 1:
                continue
            for e in edges:
                if e[0] <= o < e[1]:
                    a = acc[e]
                    a[0] += 1
                    if g["res"] == i:
                        a[1] += 1
                        a[2] += o
                    break
    return [(e, a) for e, a in acc.items() if a[0] >= 50]


def _fd_buckets(fd):
    """해외 마감 배당 기준(유럽 축구) 같은 계산."""
    edges = [(1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 10.0), (10.0, 100.0)]
    acc = {e: [0, 0, 0.0] for e in edges}
    for rows in fd.values():
        for r in rows:
            if len(r) < 4:
                continue
            res = r[3]
            for i, o in enumerate(r[:3]):
                if not o or o <= 1:
                    continue
                for e in edges:
                    if e[0] <= o < e[1]:
                        a = acc[e]
                        a[0] += 1
                        if res == i:
                            a[1] += 1
                            a[2] += o
                        break
    return [(e, a) for e, a in acc.items() if a[0] >= 200]


def r_longshot(games, fd):
    bm = _odds_buckets(games)
    xs = _fd_buckets(fd)
    if len(bm) < 3:
        return None
    rows = [[f"{e[0]:g} ~ {e[1]:g}" if e[1] < 100 else f"{e[0]:g} 이상", f"{a[0]:,}", KH.pct(a[1] / a[0]), KH.pct(a[2] / a[0])] for e, a in bm]
    rows2 = [[f"{e[0]:g} ~ {e[1]:g}" if e[1] < 100 else f"{e[0]:g} 이상", f"{a[0]:,}", KH.pct(a[1] / a[0]), KH.pct(a[2] / a[0])] for e, a in xs]
    lo, hi = bm[0][1], bm[-1][1]
    lead = (f"배당 1.5 미만 선택을 모두 샀다면 건 돈의 {KH.pct(lo[2] / lo[0])}를 돌려받았고, 가장 높은 배당 구간은 {KH.pct(hi[2] / hi[0])}를 돌려받았습니다. "
            "고배당일수록 돌려받는 비율이 낮아지는 '정배-고배당 편향'이 우리 기록에서도 보입니다.")
    secs = [("연구가 말하는 것", [
        "경마 연구에서 처음 알려진 현상입니다. 그리피스(Griffith, 1949, American Journal of Psychology)는 경마 배당을 분석해, 승산이 낮은 말(고배당)에 사람들이 실제 가능성보다 많이 건다는 점을 보였습니다. "
        "이후 탈러와 지엠바(Thaler & Ziemba, 1988, Journal of Economic Perspectives)가 여러 시장의 연구를 정리하며 이를 '정배-고배당 편향(favorite-longshot bias)'이라고 불렀습니다. "
        "고배당 선택은 맞으면 크게 돌려받기 때문에 실제 확률보다 매력적으로 느껴지고, 그만큼 값이 비싸게 매겨진다는 뜻입니다."]),
        ("우리 기록으로 보면(베트맨 배당)", [
            "베트맨 지난 회차의 모든 선택(승·무·패)을 배당 구간으로 나눠, 그 구간 선택을 전부 샀다고 가정했을 때 건 돈 대비 돌려받은 비율을 계산했습니다. 100%면 본전입니다.",
            ("table", ["배당 구간", "선택 수", "적중", "돌려받은 비율"], rows)])]
    if rows2:
        secs.append(("해외 마감 배당으로 보면(유럽 축구)", [
            "같은 계산을 유럽 축구 해외 마감 배당으로 했습니다. 해외 배당은 발행처 몫이 작아 전체적으로 100%에 더 가깝지만, 구간에 따른 기울기는 비슷하게 나타납니다.",
            ("table", ["배당 구간", "선택 수", "적중", "돌려받은 비율"], rows2)]))
    secs.append(("실전에서", [
        "고배당은 '맞으면 크다'는 점 때문에 실제 확률보다 커 보입니다. 같은 금액이라면 배당보다 확률이 맞는지부터 봅니다.",
        "로또처럼 긴 조합에 고배당을 여러 개 넣으면 이 편향이 곱으로 쌓입니다. 고배당은 한 조합에 하나 정도로 두는 편이 낫습니다.",
        "참고: Griffith, R. M. (1949). Odds adjustments by American horse-race bettors. American Journal of Psychology. / Thaler, R. H., & Ziemba, W. T. (1988). Anomalies: Parimutuel betting markets. Journal of Economic Perspectives."]))
    return _A("favorite-longshot-bias", "고배당은 왜 돌려받는 비율이 낮을까: 정배-고배당 편향", lead, secs)


def r_hot_hand(games):
    seq = defaultdict(list)
    for g in games:
        seq[(g["sport"], g["home"])].append((g, 0))
        seq[(g["sport"], g["away"])].append((g, 2))
    n = w = 0
    e = 0.0
    for lst in seq.values():
        run = 0
        for g, side in lst:
            if run >= 3:
                n += 1
                w += g["res"] == side
                e += KH.fair(g["o"])[side]
            run = run + 1 if g["res"] == side else 0
    if n < 60:
        return None
    lead = (f"3연승 중인 팀의 다음 경기 승률은 {KH.pct(w / n)}, 배당이 본 확률은 {KH.pct(e / n)}였습니다. "
            "'잘 풀리는 팀은 계속 잘 풀린다'는 느낌은 연구와 기록에서 생각보다 약하게 나타납니다.")
    secs = [("연구가 말하는 것", [
        "길로비치·발론·트버스키(Gilovich, Vallone & Tversky, 1985, Cognitive Psychology)는 농구 선수의 슛 기록을 분석해, 사람들이 믿는 '핫핸드(연속 성공이 다음 성공을 부른다)'가 기록에서는 거의 보이지 않는다고 발표했습니다. "
        "오랫동안 대표적인 착각으로 소개됐지만, 밀러와 산후르호(Miller & Sanjurjo, 2018, Econometrica)는 원래 분석 방식에 통계적 편향이 있었다는 점을 밝히고, 보정하면 작은 핫핸드 효과가 있을 수 있다고 반박했습니다.",
        "정리하면, 흐름 효과는 '없다'와 '크다' 사이 어딘가에 있고, 사람들이 느끼는 것보다는 작다는 쪽이 지금의 이해입니다."]),
        ("우리 기록으로 보면", [
            f"베트맨 발매 경기에서 3연승 이상 중이던 팀이 다음 경기에 나선 {n:,}번을 모았습니다. 실제 승률은 {KH.pct(w / n)}, 배당이 본 승리 확률의 평균은 {KH.pct(e / n)}입니다. "
            + ("둘이 거의 같습니다. 흐름이 있다 해도 시장이 이미 값에 넣고 있다는 뜻입니다." if abs(w / n - e / n) < 0.03 else
               f"차이는 {KH.pp(w / n - e / n)}입니다. 표본이 쌓이면서 이 차이가 이어지는지 지켜볼 만합니다.")]),
        ("실전에서", [
            "연승 기록 자체보다 연승의 내용(득실 차, 상대 수준)을 봅니다. 운이 따른 연승은 금방 끝납니다.",
            "참고: Gilovich, T., Vallone, R., & Tversky, A. (1985). The hot hand in basketball. Cognitive Psychology. / Miller, J. B., & Sanjurjo, A. (2018). Surprised by the hot hand fallacy? Econometrica."])]
    return _A("hot-hand", "잘 풀리는 팀은 계속 잘 풀릴까: 핫핸드 연구", lead, secs)


def r_gambler(games):
    seq = defaultdict(list)
    for g in games:
        seq[(g["sport"], g["home"])].append((g, 0))
        seq[(g["sport"], g["away"])].append((g, 2))
    n = w = 0
    e = 0.0
    for lst in seq.values():
        run = 0
        for g, side in lst:
            if run >= 3:
                n += 1
                w += g["res"] == side
                e += KH.fair(g["o"])[side]
            lost = g["res"] not in (side, 1)
            run = run + 1 if lost else 0
    if n < 60:
        return None
    lead = (f"3연패 중인 팀이 다음 경기에서 이긴 비율은 {KH.pct(w / n)}, 배당이 본 확률은 {KH.pct(e / n)}였습니다. "
            "'이제 이길 차례'라는 느낌은 결과를 바꾸지 않습니다.")
    secs = [("연구가 말하는 것", [
        "트버스키와 카너먼(Tversky & Kahneman, 1974, Science)은 사람들이 짧은 결과 묶음도 전체 확률을 닮아야 한다고 믿는 '대표성 휴리스틱'을 설명했습니다. 동전이 앞면만 연속으로 나오면 '이제 뒷면이 나올 차례'라고 느끼는 것이 대표적입니다.",
        "크로슨과 선달리(Croson & Sundali, 2005, Journal of Risk and Uncertainty)는 실제 카지노 룰렛 기록을 분석해, 같은 결과가 이어진 뒤에는 사람들이 반대쪽에 거는 경향(도박사의 오류)이 실제로 나타난다고 보고했습니다."]),
        ("우리 기록으로 보면", [
            f"3연패 이상 중이던 팀의 다음 경기 {n:,}번에서 실제 승률은 {KH.pct(w / n)}, 배당이 본 확률은 {KH.pct(e / n)}입니다. 연패가 길다는 이유만으로 다음 경기 승률이 올라가지는 않았습니다. "
            "다음 경기 결과를 정하는 건 '차례'가 아니라 그 경기의 두 팀 전력입니다."]),
        ("실전에서", [
            "내 결과도 같습니다. 몇 번 연속 빗나간 뒤 '이번엔 맞을 차례'라며 금액을 키우는 건 도박사의 오류입니다. 직전 결과와 관계없이 같은 금액을 유지합니다.",
            "참고: Tversky, A., & Kahneman, D. (1974). Judgment under uncertainty: Heuristics and biases. Science. / Croson, R., & Sundali, J. (2005). The gambler's fallacy and the hot hand. Journal of Risk and Uncertainty."])]
    return _A("gamblers-fallacy", "이제 이길 차례일까: 도박사의 오류", lead, secs)


def r_loss_aversion():
    lead = "사람은 같은 금액이라도 잃는 아픔을 얻는 기쁨보다 약 두 배 크게 느낍니다. 잃은 뒤에 무리한 선택이 나오는 이유입니다."
    rows = [[f"{x:,}원 잃음", f"약 {x * 2:,}원을 얻어야 같은 크기로 느낌"] for x in (10000, 30000, 50000)]
    secs = [("연구가 말하는 것", [
        "카너먼과 트버스키(Kahneman & Tversky, 1979, Econometrica)의 '전망 이론'은 사람이 결과를 절대 금액이 아니라 기준점에서의 이익·손실로 느끼며, 손실을 훨씬 크게 느낀다고 설명합니다. "
        "이후 연구(Tversky & Kahneman, 1992)에서 손실을 이익보다 약 2.25배 무겁게 느낀다는 추정치를 내놓았습니다."]),
        ("숫자로 보면", ["아래는 '손실은 이익의 약 두 배로 느낀다'는 연구 결과를 금액으로 옮긴 예시입니다.",
                     ("table", ["손실", "같은 크기로 느끼려면"], rows)]),
        ("왜 무리한 선택으로 이어질까", [
            "잃은 상태에서는 '본전'이 기준점이 됩니다. 본전으로 돌아가려는 마음이 강해 평소라면 고르지 않을 고배당·긴 조합을 고르게 됩니다. "
            "탈러와 존슨(Thaler & Johnson, 1990, Management Science)은 손실 뒤에 본전을 찾을 기회가 보이면 위험을 더 감수하는 '본전 효과(break-even effect)'를 실험으로 보였습니다."]),
        ("실전에서", [
            "하루·한 주 쓸 금액을 미리 정하고, 잃었다고 늘리지 않습니다.",
            "잃은 날에는 폴더 수를 줄입니다. 손실을 한 번에 되찾으려는 선택이 가장 확률이 낮은 선택입니다.",
            "부담이 된다면 한국도박문제예방치유원(국번 없이 1336, 24시간 무료)에서 상담을 받을 수 있습니다.",
            "참고: Kahneman, D., & Tversky, A. (1979). Prospect theory. Econometrica. / Tversky, A., & Kahneman, D. (1992). Advances in prospect theory. Journal of Risk and Uncertainty. / Thaler, R. H., & Johnson, E. J. (1990). Gambling with the house money and trying to break even. Management Science."])]
    return _A("loss-aversion", "잃은 돈이 더 아픈 이유: 손실 회피", lead, secs)


def r_house_money():
    lead = "딴 돈은 '공짜 돈'처럼 느껴져 더 쉽게 걸게 됩니다. 연구에서는 이를 하우스 머니 효과라고 부릅니다."
    secs = [("연구가 말하는 것", [
        "탈러와 존슨(Thaler & Johnson, 1990, Management Science)은 실험 참가자들이 앞서 돈을 딴 뒤에는 위험한 선택을 더 많이 한다는 것을 보였습니다. 딴 돈을 원래 내 돈과 다른 주머니에 넣어 생각하기 때문입니다. "
        "탈러는 이런 습관을 '심적 회계(mental accounting)'라고 불렀습니다. 같은 1만 원이라도 월급에서 나온 돈과 딴 돈을 다르게 쓰는 것입니다."]),
        ("왜 문제가 될까", [
            "딴 돈을 더 크게 걸면, 좋은 날 번 것을 한두 번의 큰 선택으로 돌려주게 됩니다. 결과적으로 이긴 날의 흐름이 길게 이어지지 않습니다. "
            "돈에는 꼬리표가 없습니다. 딴 돈도 원래 내 돈과 똑같이 다루는 것이 숫자로는 맞는 방법입니다."]),
        ("실전에서", [
            "적중한 날에도 다음 금액은 미리 정한 기준대로 둡니다.",
            "딴 금액의 일부를 따로 떼어 두는 규칙을 정해 두면 하우스 머니 효과를 줄일 수 있습니다.",
            "참고: Thaler, R. H., & Johnson, E. J. (1990). Gambling with the house money and trying to break even. Management Science. / Thaler, R. H. (1999). Mental accounting matters. Journal of Behavioral Decision Making."])]
    return _A("house-money", "딴 돈은 왜 쉽게 걸게 될까: 하우스 머니 효과", lead, secs)


def r_illusion_control():
    lead = "직접 고르면 더 잘 맞을 것 같은 느낌, 그건 착각일 가능성이 높습니다. 랭어의 '통제 착각' 실험 이야기입니다."
    secs = [("연구가 말하는 것", [
        "엘런 랭어(Langer, 1975, Journal of Personality and Social Psychology)는 복권 실험에서, 번호를 직접 고른 사람이 받은 사람보다 자기 복권을 훨씬 비싸게 되팔려 한다는 것을 보였습니다. "
        "결과는 순전히 운인데도, 직접 고르는 행동 자체가 '내가 결과를 조절할 수 있다'는 느낌을 준다는 것입니다. 이를 통제 착각(illusion of control)이라고 합니다."]),
        ("스포츠 분석에서는", [
            "경기를 오래 보고, 팀을 잘 알수록 '내 판단이 맞을 것'이라는 느낌이 강해집니다. 정보가 많아지면 실제 정확도보다 자신감이 먼저 커지는 일이 흔합니다. "
            "이 사이트가 모든 추천을 결과와 매일 자동으로 대조해 공개하는 이유도 여기에 있습니다. 느낌이 아니라 기록으로 확인하기 위해서입니다."]),
        ("실전에서", [
            "내가 고른 선택도 결과와 함께 기록해 둡니다. 한 달만 모아도 실제 적중률이 느낌과 얼마나 다른지 보입니다.",
            "'이번엔 확실하다'는 느낌이 들 때가 오히려 금액을 줄일 때입니다.",
            "참고: Langer, E. J. (1975). The illusion of control. Journal of Personality and Social Psychology."])]
    return _A("illusion-of-control", "직접 고르면 더 잘 맞을까: 통제 착각", lead, secs)


def r_near_miss(perf):
    lead = "조합이 한 경기 차이로 빗나가면 '거의 맞았다'고 느낍니다. 연구에 따르면 이 느낌은 실제로 이긴 것처럼 뇌를 자극해, 다시 하고 싶게 만듭니다."
    secs = [("연구가 말하는 것", [
        "리드(Reid, 1986, Journal of Gambling Behavior)는 슬롯머신의 '아깝게 놓친' 결과가 사람들을 계속 하게 만드는 장치라고 지적했습니다. "
        "클라크 등(Clark et al., 2009, Neuron)은 뇌 영상 실험에서, 아깝게 놓친 결과가 실제 승리 때 반응하는 뇌 보상 영역을 함께 자극한다는 것을 보였습니다. 졌는데도 뇌는 이긴 것처럼 반응한다는 뜻입니다."]),
        ("조합에서는 왜 자주 생길까", [
            "5폴더 조합에서 각 경기 확률이 70%라면, 다섯 개가 모두 맞을 확률은 약 17%입니다. 그런데 '하나만 빗나갈' 확률은 약 36%로 오히려 더 높습니다. "
            "그래서 긴 조합을 하면 '한 경기 차이'로 놓치는 경험을 아주 자주 하게 되고, 그때마다 거의 맞았다는 느낌이 쌓입니다. 이건 실력이 아까웠다는 신호가 아니라 조합 구조상 당연히 자주 생기는 결과입니다."]),
        ("숫자로 보면", [("table", ["폴더 수(경기당 70%)", "모두 적중", "한 경기만 빗나감"],
                       [[f"{k}폴더", KH.pct(0.7 ** k), KH.pct(k * 0.3 * 0.7 ** (k - 1))] for k in (3, 4, 5, 6, 8)])]),
        ("실전에서", [
            "'거의 맞았다'는 느낌이 들면 폴더 수를 늘리지 말고 줄입니다.",
            "한 경기 차이로 놓친 조합은 아깝게 놓친 것이 아니라 확률대로 빗나간 것입니다.",
            "참고: Reid, R. L. (1986). The psychology of the near miss. Journal of Gambling Behavior. / Clark, L., et al. (2009). Gambling near-misses enhance motivation to gamble and recruit win-related brain circuitry. Neuron."])]
    return _A("near-miss", "한 경기 차이로 놓친 조합: 니어미스 효과", lead, secs)


def r_kelly():
    """실험: 같은 우위(edge)에서 금액 비율에 따라 1,000명의 자금이 어떻게 갈리는지(씨앗 고정)."""
    rng = random.Random(20261119)
    p, odds, rounds, people = 0.55, 2.0, 200, 1000
    kelly = (p * odds - 1) / (odds - 1)
    res = {}
    for name, f in (("켈리의 절반", kelly / 2), ("켈리", kelly), ("켈리의 2배", kelly * 2), ("매번 25%", 0.25)):
        finals = []
        for _ in range(people):
            b = 100.0
            for _ in range(rounds):
                stake = b * f
                b += stake * (odds - 1) if rng.random() < p else -stake
            finals.append(b)
        finals.sort()
        res[name] = (finals[len(finals) // 2], sum(1 for x in finals if x < 100) / people, sum(1 for x in finals if x < 10) / people)
    rows = [[k, f"{v[0]:,.0f}", KH.pct(v[1]), KH.pct(v[2])] for k, v in res.items()]
    lead = (f"이길 확률 55%, 배당 2.00인 유리한 선택을 200번 하는 실험을 1,000명에게 돌렸습니다. 같은 선택이라도 매번 거는 비율에 따라 "
            f"결과가 크게 갈렸습니다. 켈리 기준의 2배를 건 사람은 {KH.pct(res['켈리의 2배'][1])}가 시작 금액보다 줄었습니다.")
    secs = [("켈리 기준이란", [
        "켈리(Kelly, 1956, Bell System Technical Journal)가 제안한 공식으로, 유리한 선택을 반복할 때 자금이 가장 빠르게 불어나는 '거는 비율'을 계산합니다. "
        f"이길 확률이 p, 배당이 b일 때 (p×b-1)/(b-1)입니다. 이 실험 조건(55%, 2.00배)에서는 {KH.pct(kelly)}입니다. 이 사이트의 금액 계산기도 이 공식을 씁니다."]),
        ("실험", ["시작 금액 100에서 200번 반복했습니다. 표의 '중간값'은 1,000명 중 가운데 사람의 최종 금액입니다.",
                ("table", ["거는 비율", "중간값", "줄어든 사람", "90%↑ 잃음"], rows)]),
        ("무엇을 알 수 있나", [
            "유리한 선택이라도 너무 크게 걸면 운이 나쁜 구간에서 자금이 크게 줄고, 다시 회복하기 어렵습니다. 켈리의 2배 이상을 걸면 우위가 있어도 오히려 줄어드는 사람이 많아집니다. "
            "반대로 켈리의 절반은 불어나는 속도는 조금 느리지만 크게 잃는 사람이 훨씬 적습니다. 실제로는 내 확률 추정이 틀릴 수 있으니, 켈리의 절반 이하가 현실적인 선택으로 많이 권해집니다.",
            "참고: Kelly, J. L. (1956). A new interpretation of information rate. Bell System Technical Journal."]),
        ("실전에서", ["확률 추정이 불확실할수록 켈리 비율보다 작게 겁니다.",
                    "한 번에 자금의 큰 비율을 거는 습관은 우위가 있어도 결과를 운에 맡기는 것입니다."])]
    return _A("kelly-experiment", "얼마씩 걸어야 오래 갈까: 켈리 기준 실험", lead, secs)


def r_parlay_sim():
    rng = random.Random(7)
    rows = []
    for k in (2, 3, 5, 8):
        hit = sum(1 for _ in range(10000) if all(rng.random() < 0.7 for _ in range(k)))
        rows.append([f"{k}폴더", f"{hit:,}", KH.pct(hit / 10000), KH.pct(0.7 ** k)])
    lead = f"적중 확률 70% 경기로 만든 조합 1만 장을 컴퓨터로 돌려 봤습니다. 5폴더는 1만 장 중 {rows[2][1]}장만 맞았습니다."
    secs = [("실험 방법", ["경기마다 70% 확률로 맞는다고 두고, 2·3·5·8폴더 조합을 각각 1만 장씩 무작위로 만들어 모든 경기가 맞은 조합을 셌습니다. 같은 조건으로 매번 같은 결과가 나오게 난수 씨앗을 고정했습니다."]),
            ("결과", [("table", ["조합", "1만 장 중 적중", "적중률(실험)", "계산값"], rows)]),
            ("무엇을 알 수 있나", [
                "경기 하나하나는 열 번 중 일곱 번 맞는 '좋은 선택'이어도, 묶을수록 적중은 빠르게 줄어듭니다. 8폴더는 1만 장 중 수백 장만 맞습니다. "
                "긴 조합을 몇 번 해 보고 '운이 없다'고 느끼는 건 자연스러운 결과입니다. 이 실험은 그 느낌이 운이 아니라 구조라는 것을 보여줍니다."]),
            ("실전에서", ["확신 있는 경기 수만큼만 묶습니다.", "배당을 키우려고 경기를 하나 더 넣는 순간, 적중 확률은 그 경기 확률만큼 곱해져 줄어듭니다."])]
    return _A("parlay-simulation", "조합 1만 장을 돌려 보면: 폴더 수 실험", lead, secs)


def r_poisson(fd):
    goals = defaultdict(int)
    n = tot = 0
    for rows in fd.values():
        for r in rows:
            if len(r) >= 9 and r[7] is not None and r[7] >= 0:
                goals[int(r[7])] += 1
                goals[int(r[8])] += 1
                n += 2
                tot += r[7] + r[8]
    if n < 2000:
        return None
    lam = tot / n
    rows = []
    for k in range(0, 6):
        pk = math.exp(-lam) * lam ** k / math.factorial(k)
        rows.append([f"{k}골" if k < 5 else "5골 이상", KH.pct(goals.get(k, 0) / n) if k < 5 else KH.pct(sum(v for g, v in goals.items() if g >= 5) / n),
                     KH.pct(pk) if k < 5 else KH.pct(1 - sum(math.exp(-lam) * lam ** j / math.factorial(j) for j in range(5)))])
    lead = f"유럽 축구에서 한 팀의 득점 분포를 포아송 분포와 비교했습니다. 팀당 평균 {lam:.2f}골일 때, 실제 분포와 계산이 몇 %p 안쪽으로 맞아떨어집니다."
    secs = [("연구가 말하는 것", [
        "마허(Maher, 1982, Statistica Neerlandica)는 축구 한 팀의 득점이 포아송 분포를 따른다고 보고 공격력·수비력으로 경기 결과를 예측하는 모형을 제시했습니다. "
        "딕슨과 콜스(Dixon & Coles, 1997, Applied Statistics)는 0:0, 1:0 같은 낮은 점수가 실제로 조금 더 자주 나오는 점을 보정해 모형을 다듬었고, 지금도 축구 예측의 기본 틀로 쓰입니다. "
        "이 사이트의 축구 '예상 스코어'도 같은 원리로, 해외 배당에서 두 팀 기대 득점을 거꾸로 구해 가장 나올 법한 점수를 냅니다."]),
        ("우리 기록으로 보면(실험)", [f"유럽 축구 기록에서 팀 득점 {n:,}개를 모아, 평균 {lam:.2f}골인 포아송 분포와 나란히 놓았습니다.",
                               ("table", ["팀 득점", "실제", "포아송 계산"], rows)]),
        ("실전에서", ["축구에서 한 팀이 3골 이상 넣는 경기는 생각보다 드뭅니다. 큰 핸디나 높은 합계는 이 분포로 먼저 감을 잡습니다.",
                    "참고: Maher, M. J. (1982). Modelling association football scores. Statistica Neerlandica. / Dixon, M. J., & Coles, S. G. (1997). Modelling association football scores and inefficiencies in the football betting market. Applied Statistics."])]
    return _A("poisson-goals", "축구 골은 왜 포아송을 따를까: 예상 스코어의 원리", lead, secs)


def r_home_research(games):
    sp = defaultdict(lambda: [0, 0])
    for g in games:
        sp[g["sport"]][0] += 1
        sp[g["sport"]][1] += g["res"] == 0
    name = {"soccer": "축구", "baseball": "야구", "basketball": "농구", "volleyball": "배구"}
    rows = [[name.get(k, k), f"{v[0]:,}", KH.pct(v[1] / v[0])] for k, v in sp.items() if v[0] >= 100]
    if not rows:
        return None
    lead = "홈팀이 유리한 이유로 관중 응원과 이동 피로를 떠올리지만, 연구들은 심판 판정과 익숙함도 큰 몫을 한다고 봅니다. 무관중 경기는 그걸 확인할 기회가 됐습니다."
    secs = [("연구가 말하는 것", [
        "폴라드(Pollard, 1986, Journal of Sports Sciences)는 잉글랜드 축구에서 홈팀이 오랫동안 꾸준히 더 많은 승점을 얻었다는 점을 정리하며 홈 이점 연구의 출발점을 만들었습니다. "
        "모스코비츠와 워스하임(Moskowitz & Wertheim, 2011, 책 Scorecasting)은 여러 종목 자료를 바탕으로, 홈 이점의 큰 부분이 관중 분위기에 영향을 받은 심판 판정에서 나온다고 주장했습니다."]),
        ("무관중 경기라는 실험", [
            "코로나19로 관중 없이 치른 경기들은 자연스러운 실험이 됐습니다. 여러 리그를 분석한 연구들에서 무관중 기간에 홈 이점이 줄어들었다는 결과가 많이 보고됐고, 원정팀에 대한 경고·파울 판정 차이도 줄었다는 분석이 나왔습니다. "
            "관중이 홈 이점의 중요한 재료라는 것을 보여주는 결과입니다."]),
        ("우리 기록으로 보면", ["베트맨 발매 경기의 종목별 홈 승률입니다. 축구는 무승부가 있어 숫자가 낮게 나옵니다.",
                           ("table", ["종목", "경기", "홈 승률"], rows)]),
        ("실전에서", ["홈 이점은 배당에 이미 들어 있습니다. 관중이 적은 경기(중립 구장, 무관중, 컵대회 초반)는 홈 이점을 평소보다 작게 봅니다.",
                    "참고: Pollard, R. (1986). Home advantage in soccer. Journal of Sports Sciences. / Moskowitz, T., & Wertheim, L. J. (2011). Scorecasting. Crown Archetype."])]
    return _A("home-advantage-research", "홈 이점은 어디서 올까: 심판과 관중 연구", lead, secs)


def r_market(games):
    edges = [0.2, 0.35, 0.5, 0.65, 0.8, 1.01]
    acc = defaultdict(lambda: [0, 0, 0.0])
    for g in games:
        f = KH.fair(g["o"])
        for i in (0, 2):
            p = f[i]
            for lo, hi in zip([0] + edges, edges):
                if lo <= p < hi:
                    a = acc[(lo, hi)]
                    a[0] += 1
                    a[1] += g["res"] == i
                    a[2] += p
                    break
    rows = [[f"{lo * 100:.0f}~{min(hi, 1) * 100:.0f}%", f"{a[0]:,}", KH.pct(a[2] / a[0]), KH.pct(a[1] / a[0])] for (lo, hi), a in sorted(acc.items()) if a[0] >= 80]
    if len(rows) < 3:
        return None
    lead = "배당이 본 확률과 실제 결과를 나란히 놓으면 대부분 몇 %p 안쪽으로 맞습니다. 배당은 많은 사람의 판단이 모인 꽤 정확한 예측입니다."
    secs = [("연구가 말하는 것", [
        "레빗(Levitt, 2004, Economic Journal)은 스포츠 배당 시장을 분석해, 발행처가 단순히 양쪽 금액을 맞추는 것이 아니라 결과를 꽤 정확하게 예측해 값을 매긴다는 점을 보였습니다. "
        "많은 사람의 정보가 배당에 모이기 때문에, 한 사람이 배당보다 꾸준히 정확하기는 어렵다는 것이 '시장 효율성' 연구의 공통된 결론입니다."]),
        ("우리 기록으로 보면", ["베트맨 배당에서 발행처 몫을 걷어낸 확률을 구간으로 나눠, 그 구간 선택이 실제로 몇 % 맞았는지 비교했습니다.",
                           ("table", ["배당이 본 확률", "선택 수", "평균 확률", "실제 적중"], rows)]),
        ("그럼 분석은 왜 할까", [
            "배당이 정확하다는 건 '배당과 다르게 볼 근거가 있을 때만' 의미 있는 선택이 생긴다는 뜻입니다. 이 사이트가 해외 배당을 기준으로 삼고, 해외와 베트맨 배당의 차이와 과거 기록이 배당과 어긋나는 구간을 찾는 이유입니다.",
            "참고: Levitt, S. D. (2004). Why are gambling markets organised so differently from financial markets? Economic Journal."])]
    return _A("market-efficiency", "배당은 얼마나 정확할까: 시장 효율성 연구", lead, secs)


def r_regression(games):
    seq = defaultdict(list)
    for g in games:
        seq[(g["sport"], g["home"])].append((g, 0))
        seq[(g["sport"], g["away"])].append((g, 2))
    hot_first, hot_second = [], []
    for lst in seq.values():
        if len(lst) < 20:
            continue
        a, b = lst[:len(lst) // 2], lst[len(lst) // 2:]
        wa = sum(g["res"] == s for g, s in a) / len(a)
        wb = sum(g["res"] == s for g, s in b) / len(b)
        hot_first.append((wa, wb))
    if len(hot_first) < 20:
        return None
    hot_first.sort(key=lambda x: -x[0])
    top = hot_first[: max(5, len(hot_first) // 5)]
    bot = hot_first[-max(5, len(hot_first) // 5):]
    ta, tb = sum(x[0] for x in top) / len(top), sum(x[1] for x in top) / len(top)
    ba, bb = sum(x[0] for x in bot) / len(bot), sum(x[1] for x in bot) / len(bot)
    lead = f"기록 앞쪽에서 승률이 가장 높았던 팀들은 {KH.pct(ta)}에서 뒤쪽 {KH.pct(tb)}로, 가장 낮았던 팀들은 {KH.pct(ba)}에서 {KH.pct(bb)}로 평균 쪽으로 움직였습니다."
    secs = [("연구가 말하는 것", [
        "골턴(Galton, 1886)은 아주 큰 부모의 자녀가 부모보다는 평균에 가까운 키를 갖는 경향을 발견하고 '평균으로의 회귀'라고 불렀습니다. 극단적인 결과에는 운이 섞여 있어서, 다음에는 그 운이 빠지며 평균 쪽으로 돌아오기 쉽다는 뜻입니다. "
        "스포츠에서 잡지 표지를 장식한 선수가 다음 시즌 부진하다는 '표지 징크스'도 대부분 이 현상으로 설명됩니다."]),
        ("우리 기록으로 보면", [f"베트맨 발매 경기가 20경기 이상인 팀 {len(hot_first)}곳의 기록을 앞쪽 절반과 뒤쪽 절반으로 나눴습니다.",
                           ("table", ["팀 묶음", "앞쪽 승률", "뒤쪽 승률"], [["앞쪽 상위 20%", KH.pct(ta), KH.pct(tb)], ["앞쪽 하위 20%", KH.pct(ba), KH.pct(bb)]])]),
        ("실전에서", ["최근 성적이 유난히 좋거나 나쁜 팀은 원래 실력 쪽으로 돌아올 가능성을 같이 봅니다. 득실 차가 그 팀의 원래 수준을 더 잘 보여줍니다.",
                    "참고: Galton, F. (1886). Regression towards mediocrity in hereditary stature. Journal of the Anthropological Institute."])]
    return _A("regression-to-mean", "잘나가던 팀은 왜 식을까: 평균으로의 회귀", lead, secs)


def r_action_bias():
    lead = "승부차기에서 골키퍼가 가운데 서 있는 편이 통계적으로 나은데도 대부분 좌우로 몸을 던진다는 연구가 있습니다. 가만히 서 있다가 골을 내주는 쪽이 더 후회되기 때문입니다."
    secs = [("연구가 말하는 것", [
        "바-엘리 등(Bar-Eli et al., 2007, Journal of Economic Psychology)은 정상급 리그 페널티킥을 분석해, 골키퍼가 가운데 머물 때 막는 비율이 가장 높았는데도 골키퍼 대부분이 좌우로 몸을 던졌다고 보고했습니다. "
        "연구진은 '아무것도 안 하다 실점하는 것'이 '움직였다 실점하는 것'보다 더 비난받고 후회되기 때문에 행동 쪽으로 기우는 '행동 편향'으로 설명했습니다."]),
        ("우리에게 주는 의미", [
            "분석도 같습니다. 오늘 경기가 있으면 뭐라도 골라야 할 것 같은 압박이 생깁니다. 하지만 확실한 근거가 없는 날에는 고르지 않는 것도 좋은 선택입니다. "
            "이 사이트가 확률이 55% 미만인 경기를 '박빙'으로 두고 추천하지 않는 이유도 같습니다."]),
        ("실전에서", ["근거가 없으면 건너뜁니다. 고르지 않은 경기는 잃지 않은 경기입니다.",
                    "참고: Bar-Eli, M., Azar, O. H., Ritov, I., Keidar-Levin, Y., & Schein, G. (2007). Action bias among elite soccer goalkeepers: The case of penalty kicks. Journal of Economic Psychology."])]
    return _A("action-bias", "가만히 있는 게 나을 때: 골키퍼의 행동 편향", lead, secs)


def r_anchoring(games):
    mv = [(g, i) for g in games for i in (0, 2) if g.get("open") and g["open"][i] and g["o"][i] and (g["o"][i] - g["open"][i]) / g["open"][i] <= -0.05]
    if len(mv) < 40:
        return None
    hit = sum(1 for g, i in mv if g["res"] == i) / len(mv)
    p_open = sum(KH.fair(g["open"])[i] for g, i in mv) / len(mv)
    p_close = sum(KH.fair(g["o"])[i] for g, i in mv) / len(mv)
    lead = (f"처음 발매 때보다 배당이 5% 넘게 내려간 쪽은 실제로 {KH.pct(hit)} 맞았습니다. 처음 배당이 본 확률은 {KH.pct(p_open)}, 마감 배당은 {KH.pct(p_close)}였습니다. "
            "처음 본 숫자에 기준을 두면 이런 변화를 놓치기 쉽습니다.")
    secs = [("연구가 말하는 것", [
        "트버스키와 카너먼(Tversky & Kahneman, 1974, Science)은 사람들이 처음 본 숫자를 기준(닻)으로 삼고 그 근처에서 판단을 조금씩만 고친다는 '기준점 효과(anchoring)'를 보였습니다. "
        "실험에서는 판단과 아무 관계없는 숫자를 먼저 보여 줘도 그 숫자 쪽으로 답이 끌려갔습니다."]),
        ("우리 기록으로 보면", [
            f"베트맨에서 처음 발매 배당보다 5% 넘게 낮아진 선택 {len(mv):,}개를 모았습니다. 실제 적중은 {KH.pct(hit)}였고, 처음 배당이 본 확률({KH.pct(p_open)})보다 마감 배당이 본 확률({KH.pct(p_close)})에 더 가까웠습니다. "
            "배당이 움직였다면 그 사이에 새로운 정보(부상, 선발 명단 등)가 들어왔을 가능성이 높고, 처음 배당을 기준으로 삼으면 그 정보를 놓치게 됩니다."]),
        ("실전에서", ["처음 본 배당에 기준을 두지 말고, 고르기 직전의 배당과 이유를 다시 봅니다. 경기 페이지의 배당 흐름 차트가 그 변화를 보여줍니다.",
                    "참고: Tversky, A., & Kahneman, D. (1974). Judgment under uncertainty: Heuristics and biases. Science."])]
    return _A("anchoring-odds", "처음 본 배당에 끌리는 이유: 기준점 효과", lead, secs)


def r_choice(games):
    lead = "고를 게 많을수록 더 좋은 선택을 할 것 같지만, 연구에서는 선택지가 많을수록 고르기 어려워하고 고른 뒤 만족도 낮아졌습니다. 한 회차 수십 경기 앞에서도 같은 일이 생깁니다."
    secs = [("연구가 말하는 것", [
        "아이엔가와 레퍼(Iyengar & Lepper, 2000, Journal of Personality and Social Psychology)의 잼 실험이 유명합니다. 마트 시식대에 잼을 24종류 놓았을 때보다 6종류만 놓았을 때 실제로 사는 사람이 훨씬 많았습니다. "
        "선택지가 너무 많으면 비교에 지치고, 결정을 미루거나 대충 고르게 된다는 것입니다. 이를 '선택 과부하'라고 부릅니다. 이후 연구들에서는 상황에 따라 효과의 크기가 다르다는 반론도 나왔습니다."]),
        ("한 회차 앞에서", [
            "베트맨 한 회차에는 수십 경기, 마켓까지 합치면 백 개가 넘는 선택지가 있습니다. 모든 경기를 다 보려 하면 오히려 근거가 약한 경기까지 끼워 넣게 됩니다. "
            "이 사이트가 '적중 확률 높은 경기'와 전략별 조합을 몇 개로 추려 보여주는 이유입니다."]),
        ("실전에서", ["한 회차에서 볼 리그나 종목을 2~3개로 정하고 그 안에서만 고릅니다.", "추린 목록에서 출발해 근거를 확인하는 순서가 시간도 덜 들고 판단도 깔끔합니다.",
                    "참고: Iyengar, S. S., & Lepper, M. R. (2000). When choice is demotivating. Journal of Personality and Social Psychology."])]
    return _A("choice-overload", "경기가 많으면 더 잘 고를까: 선택 과부하", lead, secs)


def r_sunk_cost():
    lead = "이미 쓴 돈 때문에 그만두지 못하는 것을 매몰 비용 효과라고 합니다. 이번 주에 잃은 금액은 다음 선택과 아무 관계가 없습니다."
    secs = [("연구가 말하는 것", [
        "아크스와 블루머(Arkes & Blumer, 1985, Organizational Behavior and Human Decision Processes)는 비싼 값을 치른 공연이나 여행일수록, 더 즐거운 다른 선택이 있어도 이미 낸 돈 때문에 그쪽을 고르는 경향을 실험으로 보였습니다. "
        "되돌릴 수 없는 비용(매몰 비용)이 앞으로의 판단을 끌어당기는 현상입니다."]),
        ("스포츠 분석에서는", ["'이번 주에 이만큼 썼으니 여기서 멈추면 손해'라는 생각이 대표적입니다. 이미 쓴 금액은 어떤 선택을 해도 돌아오지 않습니다. 다음 선택은 그 경기의 확률과 배당만으로 판단해야 합니다."]),
        ("실전에서", ["기간별 쓸 금액을 정하고, 다 쓰면 그 기간은 멈춥니다.", "이미 쓴 금액을 생각하며 고른 선택은 거의 항상 평소보다 무리한 선택입니다.",
                    "참고: Arkes, H. R., & Blumer, C. (1985). The psychology of sunk cost. Organizational Behavior and Human Decision Processes."])]
    return _A("sunk-cost", "이미 쓴 돈 때문에 멈추지 못할 때: 매몰 비용", lead, secs)


def r_recency(games):
    seq = defaultdict(list)
    for g in games:
        seq[(g["sport"], g["home"])].append((g, 0))
        seq[(g["sport"], g["away"])].append((g, 2))
    n = w = 0
    e = 0.0
    for lst in seq.values():
        for (g0, s0), (g1, s1) in zip(lst, lst[1:]):
            if g0.get("hs") is None:
                continue
            my = (g0["hs"] - g0["as"]) if s0 == 0 else (g0["as"] - g0["hs"])
            if g0["sport"] == "soccer" and my <= -3 or g0["sport"] == "basketball" and my <= -20 or g0["sport"] == "baseball" and my <= -7:
                n += 1
                w += g1["res"] == s1
                e += KH.fair(g1["o"])[s1]
    if n < 40:
        return None
    lead = (f"직전 경기에서 크게 진 팀의 다음 경기 승률은 {KH.pct(w / n)}, 배당이 본 확률은 {KH.pct(e / n)}였습니다. "
            "방금 본 큰 패배는 머릿속에 크게 남지만, 다음 경기는 그 기억만큼 달라지지 않습니다.")
    secs = [("연구가 말하는 것", [
        "트버스키와 카너먼(Tversky & Kahneman, 1973, Cognitive Psychology)은 사람들이 떠올리기 쉬운 사례일수록 더 자주 일어난다고 판단하는 '가용성 휴리스틱'을 보였습니다. "
        "최근에 본 장면, 충격적인 장면일수록 쉽게 떠오르기 때문에 그 영향이 실제보다 크게 계산됩니다."]),
        ("우리 기록으로 보면", [
            f"직전 경기에서 큰 점수 차(축구 3골, 농구 20점, 야구 7점 이상)로 진 팀이 다음 경기에 나선 {n:,}번을 모았습니다. 실제 승률은 {KH.pct(w / n)}, 배당이 본 확률은 {KH.pct(e / n)}입니다. "
            + ("배당과 거의 같습니다. 큰 패배 한 번은 시장도 사람들도 크게 흔들지 못했습니다." if abs(w / n - e / n) < 0.03 else
               f"차이는 {KH.pp(w / n - e / n)}입니다. " + ("큰 패배 뒤 팀이 과소평가됐을 가능성이 있습니다." if w / n > e / n else "큰 패배가 실제로 팀 상태가 나쁘다는 신호였을 수 있습니다."))]),
        ("실전에서", ["한 경기의 큰 점수 차보다 최근 여러 경기의 득실 흐름을 봅니다.",
                    "참고: Tversky, A., & Kahneman, D. (1973). Availability: A heuristic for judging frequency and probability. Cognitive Psychology."])]
    return _A("availability-big-loss", "크게 진 다음 경기: 가용성 휴리스틱", lead, secs)


def r_overconfidence(perf):
    cal = (perf or {}).get("calibration") or []
    n = (((perf or {}).get("picks") or {}).get("all") or {}).get("n")
    if not cal or not n or n < 50:
        return None
    rows = [[c["bucket"], f"{c['n']:,}", KH.pct(c["expected"]), KH.pct(c["actual"])] for c in cal]
    hi = [c for c in cal if c["bucket"][:1] in "789"]
    lead = (f"이 사이트는 추천 {n:,}개의 '추정 확률'과 '실제 적중'을 매일 자동으로 대조합니다. 사람이 자기 예측을 이렇게 기록해 보면 "
            "대부분 실제보다 자신 있게 예측했다는 것을 알게 됩니다.")
    secs = [("연구가 말하는 것", [
        "리히텐슈타인·피쇼프·필립스(Lichtenstein, Fischhoff & Phillips, 1982)는 확률 판단 연구를 정리하며, 사람들이 '90% 확실하다'고 답한 문제의 실제 정답률이 그보다 낮은 경우가 흔하다는 '과신(overconfidence)'을 보고했습니다. "
        "확률을 말하는 것과, 그 확률이 실제로 맞는지 기록으로 확인하는 것(보정, calibration)은 전혀 다른 일입니다."]),
        ("이 사이트의 보정 기록", ["추정 확률 구간마다 실제 적중률을 나란히 놓았습니다. 두 숫자가 비슷할수록 확률이 정직하다는 뜻이고, 표본이 쌓이며 매일 바뀝니다.",
                             ("table", ["추정 확률", "추천 수", "추정 평균", "실제 적중"], rows)]),
        ("왜 기록이 중요한가", [
            "기억은 맞힌 경기를 오래 남기고 빗나간 경기를 쉽게 잊습니다. 그래서 기록 없이 느끼는 적중률은 거의 항상 실제보다 높습니다. "
            "이 사이트가 모든 추천을 숨기지 않고 매일 채점해 '성과' 페이지에 공개하는 이유이고, 그 결과로 계산 방식을 스스로 고칩니다."]),
        ("실전에서", ["내 선택을 확률과 함께 적어 두고, 한 달 뒤 구간별로 실제 적중률을 비교해 봅니다.",
                    "참고: Lichtenstein, S., Fischhoff, B., & Phillips, L. D. (1982). Calibration of probabilities: The state of the art to 1980. In Kahneman, Slovic & Tversky (Eds.), Judgment under Uncertainty. Cambridge University Press."])]
    return _A("overconfidence-calibration", "내 예측은 몇 % 맞을까: 과신과 보정", lead, secs)


def r_confirmation():
    lead = "응원하는 팀, 이미 고른 쪽의 근거만 눈에 들어오는 것을 확증 편향이라고 합니다. 분석을 할수록 오히려 강해질 수 있습니다."
    secs = [("연구가 말하는 것", [
        "로드·로스·레퍼(Lord, Ross & Lepper, 1979, Journal of Personality and Social Psychology)는 사형제도에 찬반 의견이 다른 사람들에게 같은 연구 자료를 보여 줬습니다. "
        "양쪽 모두 자기 의견을 지지하는 자료는 믿을 만하다고, 반대 자료는 허점이 많다고 평가했고, 자료를 본 뒤 오히려 원래 의견이 더 강해졌습니다. 같은 정보를 보고도 각자 보고 싶은 쪽으로 읽는다는 뜻입니다."]),
        ("스포츠 분석에서는", [
            "한 팀을 고르고 나면 그 팀이 이길 이유는 잘 보이고, 질 이유는 '이번엔 괜찮겠지'로 넘기게 됩니다. 좋아하는 팀이 있다면 더 강해집니다. "
            "이 사이트의 경기 페이지가 추천과 함께 '이변 위험'과 반대쪽 근거, 숫자 비교를 같이 보여주는 이유입니다."]),
        ("실전에서", ["고르기 전에 반대쪽이 이길 이유를 세 가지 적어 봅니다. 적기 어렵다면 확신해도 되고, 쉽게 적힌다면 다시 봅니다.",
                    "응원하는 팀 경기는 따로 떼어 두는 것도 방법입니다.",
                    "참고: Lord, C. G., Ross, L., & Lepper, M. R. (1979). Biased assimilation and attitude polarization. Journal of Personality and Social Psychology."])]
    return _A("confirmation-bias", "보고 싶은 것만 보일 때: 확증 편향", lead, secs)


def r_crowd(games):
    edges = [0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 1.01]
    n = hit = 0
    for g in games:
        f = KH.fair(g["o"])
        k = max((0, 2), key=lambda i: f[i])
        n += 1
        hit += g["res"] == k
    if n < 200:
        return None
    lead = (f"1906년 영국의 한 장터에서 사람들이 소의 무게를 맞히는 내기를 했는데, 800명 가까운 답을 모아 평균 내자 실제 무게와 거의 같았습니다. "
            f"배당도 수많은 사람의 판단이 모인 숫자라, 배당의 정배는 베트맨 기록에서 {KH.pct(hit / n)} 맞았습니다.")
    secs = [("연구가 말하는 것", [
        "프랜시스 골턴(Galton, 1907, Nature, 'Vox populi')은 장터의 소 무게 맞히기 대회에서 모인 답들의 가운데 값이 실제 무게와 1% 안쪽으로 맞았다고 보고했습니다. "
        "한 사람 한 사람은 크게 틀려도, 서로 다른 정보를 가진 많은 사람의 판단을 모으면 오차가 서로 상쇄된다는 '군중의 지혜'의 출발점이 된 기록입니다."]),
        ("배당은 군중의 판단", [
            f"배당은 많은 사람의 판단과 정보가 모여 정해집니다. 베트맨 기록 {n:,}경기에서 배당이 더 낮은 쪽(정배)이 이긴 비율은 {KH.pct(hit / n)}입니다. "
            "개인이 이 숫자를 꾸준히 넘기는 것은 쉽지 않습니다. 다만 군중의 지혜는 사람들이 서로 독립적으로 판단할 때 잘 작동합니다. 모두가 같은 소문을 따라가면 오히려 함께 틀립니다."]),
        ("실전에서", ["배당을 '군중이 본 확률'로 먼저 읽고, 그와 다르게 볼 분명한 근거가 있을 때만 다르게 고릅니다.",
                    "갑자기 한쪽으로 쏠린 배당은 새 정보일 수도, 같은 소문을 따라간 쏠림일 수도 있습니다. 쏠린 이유를 확인합니다.",
                    "참고: Galton, F. (1907). Vox populi. Nature. / Surowiecki, J. (2004). The Wisdom of Crowds. Doubleday."])]
    return _A("wisdom-of-crowds", "배당은 왜 잘 맞을까: 군중의 지혜", lead, secs)


def r_clustering():
    rng = random.Random(42)
    flips = [rng.random() < 0.5 for _ in range(100)]
    best = run = 1
    for a, b in zip(flips, flips[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    sims = []
    for _ in range(5000):
        f = [rng.random() < 0.5 for _ in range(100)]
        m = r = 1
        for a, b in zip(f, f[1:]):
            r = r + 1 if a == b else 1
            m = max(m, r)
        sims.append(m)
    p6 = sum(1 for x in sims if x >= 6) / len(sims)
    lead = f"동전을 100번 던지면 같은 면이 6번 이상 연속으로 나올 확률이 {KH.pct(p6)}입니다. 무작위에도 '흐름'처럼 보이는 덩어리가 자주 생깁니다."
    secs = [("연구가 말하는 것", [
        "토머스 길로비치(Gilovich, 1991, 책 How We Know What Isn't So)는 사람들이 무작위로 흩어진 결과에서도 패턴을 찾아내는 경향을 '군집 착각(clustering illusion)'이라고 설명했습니다. "
        "2차 세계대전 때 런던 시민들은 폭탄이 특정 지역을 노리고 떨어진다고 믿었지만, 이후 분석(Clarke, 1946)에서는 낙하 지점이 무작위 분포와 잘 맞았다는 이야기가 대표적입니다."]),
        ("실험", [f"컴퓨터로 동전 100번 던지기를 5,000번 반복했습니다. 같은 면이 6번 이상 이어진 경우가 {KH.pct(p6)}였습니다. 한 번의 예시 기록에서는 최장 {best}번 연속이 나왔습니다. "
                "완전히 무작위인데도 '연승' '연패'처럼 보이는 흐름이 이렇게 자주 생깁니다."]),
        ("실전에서", ["몇 경기 연속 같은 결과는 흐름이 아니라 우연일 가능성을 먼저 생각합니다.",
                    "내 적중과 빗나감이 몰려 오는 것도 대부분 우연입니다. 몰린 결과를 보고 방법을 자주 바꾸지 않습니다.",
                    "참고: Gilovich, T. (1991). How We Know What Isn't So. Free Press. / Clarke, R. D. (1946). An application of the Poisson distribution. Journal of the Institute of Actuaries."])]
    return _A("clustering-illusion", "무작위에도 흐름이 보이는 이유: 군집 착각", lead, secs)


def r_red_card():
    lead = "축구에서 레드카드 한 장은 경기의 기울기를 바꿉니다. 연구에 따르면 일찍 나온 퇴장일수록 영향이 크고, 퇴장당한 팀의 득점 기대가 크게 줄어듭니다."
    secs = [("연구가 말하는 것", [
        "리더·크라머·홉스태컨(Ridder, Cramer & Hopstaken, 1994, Journal of the American Statistical Association)은 네덜란드 리그 경기를 분석해, 레드카드 이후 퇴장당한 팀의 득점 속도가 줄고 상대 팀의 득점 속도가 늘어난다는 것을 추정했습니다. "
        "연구진은 이를 바탕으로, 경기 초반에는 확실한 실점을 반칙으로 막고 퇴장당하는 것이 오히려 더 불리할 수 있다고 계산했습니다. 퇴장의 무게가 남은 시간에 따라 달라진다는 뜻입니다."]),
        ("의미", [
            "레드카드는 남은 시간이 길수록 영향이 큽니다. 전반 초반의 퇴장은 경기 전체 흐름을 바꾸지만, 후반 막판의 퇴장은 결과를 바꾸지 못하는 경우가 많습니다. "
            "카드가 많은 리그나 거친 경기 스타일의 팀끼리 만나는 경기는 이런 변수가 생길 가능성이 상대적으로 높습니다."]),
        ("실전에서", ["경기 전 분석에서는 두 팀의 경기 스타일과 리그의 카드 빈도를 참고합니다(노하우의 리그 비교 글).",
                    "참고: Ridder, G., Cramer, J. S., & Hopstaken, P. (1994). Down to ten: Estimating the effect of a red card in soccer. Journal of the American Statistical Association."])]
    return _A("red-card-effect", "레드카드 한 장의 무게: 퇴장 효과 연구", lead, secs)


def r_back_to_back(games):
    from datetime import datetime, timedelta, timezone
    kst = timezone(timedelta(hours=9))
    nba = [g for g in games if g["league"] == "NBA"]
    last = {}
    n = w = 0
    e = 0.0
    for g in sorted(nba, key=lambda x: x["ko"]):
        d = datetime.fromtimestamp(g["ko"] / 1000, kst).date()
        for side, team in ((0, g["home"]), (2, g["away"])):
            prev = last.get(team)
            if prev and (d - prev).days == 1:
                n += 1
                w += g["res"] == side
                e += KH.fair(g["o"])[side]
            last[team] = d
    lead = "NBA에서 이틀 연속 경기를 치르는 '백투백'은 오랫동안 불리한 조건으로 꼽혀 왔습니다. 연구는 휴식 차이가 홈 이점의 일부까지 설명한다고 봅니다."
    secs = [("연구가 말하는 것", [
        "엔타인과 스몰(Entine & Small, 2008, Journal of Quantitative Analysis in Sports)은 NBA 경기에서 휴식일 차이를 분석해, 원정팀이 백투백으로 치르는 경우가 더 많다는 점이 홈 이점의 일부를 설명한다고 보고했습니다. "
        "즉, 홈팀이 유리한 이유 중에는 관중뿐 아니라 '원정팀이 더 지쳐 있다'는 일정 요인도 섞여 있다는 뜻입니다."])]
    if n >= 30:
        secs.append(("우리 기록으로 보면", [
            f"베트맨 발매 NBA 경기에서 전날에도 경기를 치른 팀이 나선 {n:,}번을 모았습니다. 실제 승률은 {KH.pct(w / n)}, 배당이 본 승리 확률은 {KH.pct(e / n)}입니다. "
            + ("배당과 거의 같습니다. 연전 부담은 이미 배당에 들어가 있습니다." if abs(w / n - e / n) < 0.03 else
               f"차이는 {KH.pp(w / n - e / n)}입니다. 표본이 쌓이면서 이 차이가 유지되는지 지켜볼 만합니다.")]))
    secs.append(("실전에서", ["경기 페이지의 '숫자가 말하는 것'에서 연전 여부를 확인할 수 있습니다. 한 팀만 연전이면 그 차이를 눈여겨봅니다.",
                            "연전 막바지 경기는 주전 출전 시간이 줄어 큰 핸디·합계 결과가 흔들리기 쉽습니다.",
                            "참고: Entine, O. A., & Small, D. S. (2008). The role of rest in the NBA home-court advantage. Journal of Quantitative Analysis in Sports."]))
    return _A("nba-back-to-back", "NBA 백투백은 정말 불리할까: 휴식 연구", lead, secs)


def r_outcome_bias(perf):
    lead = "좋은 결정이 나쁜 결과로 끝나기도 하고, 나쁜 결정이 운 좋게 맞기도 합니다. 결과만 보고 결정을 평가하는 것을 결과 편향이라고 합니다."
    pk = (((perf or {}).get("picks") or {}).get("all") or {})
    extra = (f" 이 사이트의 추천도 지금까지 {pk['n']:,}개 중 {KH.pct(pk.get('hit_rate') or 0)}가 맞았습니다. 나머지는 확률대로 빗나간 것이지, 그 결정이 모두 틀렸던 것은 아닙니다." if pk.get("n") else "")
    secs = [("연구가 말하는 것", [
        "배런과 허시(Baron & Hershey, 1988, Journal of Personality and Social Psychology)는 같은 의학적 결정을 두고 결과만 다르게 알려 주는 실험을 했습니다. "
        "참가자들은 결과가 좋았다고 들은 경우 그 결정을 훨씬 좋게 평가했습니다. 결정할 때 알 수 있었던 정보는 똑같았는데도 말입니다."]),
        ("스포츠 분석에서는", ["70% 확률 선택이 빗나갔다고 그 선택이 틀린 것은 아닙니다. 열 번 중 세 번은 원래 빗나갑니다." + extra]),
        ("실전에서", ["결과가 아니라 '고를 때의 근거가 맞았나'로 내 선택을 돌아봅니다.",
                    "한두 번의 결과로 방법을 바꾸지 않고, 충분히 쌓인 기록으로 판단합니다.",
                    "참고: Baron, J., & Hershey, J. C. (1988). Outcome bias in decision evaluation. Journal of Personality and Social Psychology."])]
    return _A("outcome-bias", "빗나갔다고 틀린 결정일까: 결과 편향", lead, secs)


def build(perf: dict | None = None) -> list[dict]:
    from ..sources import betman_history
    rows = betman_history.load_all()
    games = KH._games(rows)
    fd = KH._load_fd()
    arts = []
    for fn in (lambda: r_longshot(games, fd), lambda: r_market(games), lambda: r_hot_hand(games), lambda: r_gambler(games),
               lambda: r_regression(games), lambda: r_anchoring(games), lambda: r_recency(games), lambda: r_home_research(games),
               lambda: r_poisson(fd), r_kelly, r_parlay_sim, lambda: r_near_miss(perf), r_loss_aversion, r_house_money,
               r_illusion_control, r_action_bias, lambda: r_choice(games), r_sunk_cost,
               lambda: r_overconfidence(perf), r_confirmation, lambda: r_crowd(games), r_clustering, r_red_card,
               lambda: r_back_to_back(games), lambda: r_outcome_bias(perf)):
        try:
            a = fn()
        except Exception:  # noqa: BLE001
            a = None
        if a:
            d = a.to_dict()
            d["games"] = 0
            arts.append(d)
    return arts
