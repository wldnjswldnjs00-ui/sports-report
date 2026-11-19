"""짧은 리그별 노하우 글 보강: 같은 종목 다른 리그와의 비교표, 그 리그 숫자로 계산한 실전 활용, 같은 리그 다른 글 연결.

리그 이름만 바꾼 문장이 되지 않도록, 문장마다 그 리그의 숫자(순위·차이·조합 확률)가 들어간다. 매 빌드마다 기록으로 다시 계산한다.
대상: 베트맨 리그 주제 글(fav·home·upset·ou·hc)과 유럽 축구 주제 글(goals·draws·o25).
"""
from __future__ import annotations

from collections import defaultdict

from . import knowhow as KH

SPORT_KO = {"soccer": "축구", "baseball": "야구", "basketball": "농구", "volleyball": "배구"}
TOPIC = {"fav": ("정배 적중", "정배"), "home": ("홈 승률", "홈 이점"), "upset": ("역배 적중", "이변"),
         "ou": ("오버 비율", "언더오버"), "hc": ("받은 쪽 버틴 비율", "핸디캡"),
         "goals": ("경기당 골", "골"), "draws": ("무승부 비율", "무승부"), "o25": ("2.5골 오버 비율", "오버 2.5")}


def _metrics(games, ou, hc):
    """베트맨 리그별 지표: {lk: {name, sport, n, fav, home, upset, ou, hc}}"""
    lg = defaultdict(list)
    for g in games:
        lg[g["lk"]].append(g)
    ou_by, hc_by = defaultdict(list), defaultdict(list)
    for x in ou:
        ou_by[x["lk"]].append(x)
    for x in hc:
        if x["line"]:
            hc_by[x["lk"]].append(x)
    out = {}
    for lk, gs in lg.items():
        if len(gs) < 80:
            continue
        fv = [(g, KH._fav(g)) for g in gs if KH._fav(g)]
        lo, lh = ou_by.get(lk, []), hc_by.get(lk, [])
        out[lk] = {"name": gs[0]["league"], "sport": gs[0]["sport"], "n": len(gs),
                   "home": sum(1 for g in gs if g["res"] == 0) / len(gs),
                   "fav": sum(1 for g, f in fv if g["res"] == f[0]) / len(fv) if fv else None,
                   "upset": sum(1 for g, f in fv if g["res"] == 2 - f[0]) / len(fv) if fv else None,
                   "ou": sum(1 for x in lo if x["res"] == (2 if x["uf"] else 0)) / len(lo) if len(lo) >= 60 else None,
                   "hc": sum(1 for x in lh if x["res"] == (0 if x["line"] > 0 else 2)) / len(lh) if len(lh) >= 60 else None}
    return out


def _recent(key, lk, games, ou, hc, n=100):
    """최근 n경기 지표(시간순 뒤쪽). 표본이 모자라면 None."""
    if key in ("fav", "home", "upset"):
        gs = sorted([g for g in games if g["lk"] == lk], key=lambda g: g["ko"])[-n:]
        if len(gs) < n:
            return None
        if key == "home":
            return sum(1 for g in gs if g["res"] == 0) / len(gs)
        fv = [(g, KH._fav(g)) for g in gs if KH._fav(g)]
        if not fv:
            return None
        return sum(1 for g, f in fv if g["res"] == (f[0] if key == "fav" else 2 - f[0])) / len(fv)
    lst = sorted([x for x in (ou if key == "ou" else hc) if x["lk"] == lk and (key == "ou" or x["line"])], key=lambda x: x["ko"])[-n:]
    if len(lst) < n:
        return None
    if key == "ou":
        return sum(1 for x in lst if x["res"] == (2 if x["uf"] else 0)) / len(lst)
    return sum(1 for x in lst if x["res"] == (0 if x["line"] > 0 else 2)) / len(lst)


def _fmt(key, v):
    return f"{v:.2f}골" if key == "goals" else KH.pct(v)


def _compare(key, me, rows, sport_word, hi, lo):
    """rows: [(이름, 값)] 같은 종목 리그들. me: 이 리그 이름."""
    rows = [r for r in rows if r[1] is not None]
    if len(rows) < 3:
        return []
    rows.sort(key=lambda r: -r[1])
    names = [r[0] for r in rows]
    if me not in names:
        return []
    rank = names.index(me) + 1
    val = rows[rank - 1][1]
    avg = sum(r[1] for r in rows) / len(rows)
    label = TOPIC[key][0]
    diff = (val - avg) if key != "goals" else None
    pos = (f"{len(rows)}개 {sport_word} 리그 중 {rank}번째로 높습니다" if 1 < rank < len(rows)
           else f"{len(rows)}개 {sport_word} 리그 중 가장 높습니다" if rank == 1 else f"{len(rows)}개 {sport_word} 리그 중 가장 낮습니다")
    gap = (f" 평균({_fmt(key, avg)})보다 {KH.pp(diff)} {'높아' if diff > 0 else '낮아'}, {hi if diff > 0.01 else lo if diff < -0.01 else '평균에 가까운 리그'}입니다."
           if diff is not None else f" 평균은 {avg:.2f}골입니다.")
    top = rows[:8]
    if me not in [r[0] for r in top]:
        top = top[:7] + [rows[rank - 1]]
    table = ("table", ["순위", "리그", label], [[str(names.index(n) + 1), n + (" (이 글)" if n == me else ""), _fmt(key, v)] for n, v in top])
    return [("같은 종목 다른 리그와 비교", [f"{me}의 {label}은 {_fmt(key, val)}로, {pos}." + gap, table])]


def _howto(key, me, v):
    if v is None:
        return []
    if key == "fav":
        tips = [f"{me} 정배 하나의 적중이 {KH.pct(v)}라면, 정배만 두 개 묶어도 {KH.pct(v ** 2)}, 세 개면 {KH.pct(v ** 3)}로 내려갑니다. 조합에 넣는 정배 수를 정할 때 이 숫자부터 봅니다.",
                "정배 배당이 낮을수록 적중은 높지만 맞을 때 얻는 것이 작습니다. 표의 배당 구간별 적중과 함께 보고 고릅니다."]
    elif key == "home":
        tips = [f"{me} 홈팀 승률 {KH.pct(v)}은 배당에 이미 들어 있는 숫자입니다. 홈팀이라는 이유만으로 고르기보다 이 숫자보다 홈팀을 훨씬 높게 볼 근거가 있을 때 고릅니다.",
                "원정팀이 정배인 경기는 홈 이점을 넘어설 만큼 전력 차가 있다는 뜻입니다. 이런 경기에서 원정 정배가 얼마나 맞는지는 정배 글에서 함께 확인할 수 있습니다."]
    elif key == "upset":
        tips = [f"{me}에서 역배가 이긴 비율 {KH.pct(v)}은 대략 {round(1 / v) if v else '-'}경기에 한 번꼴입니다. 역배는 한 경기에 크게 담기보다 작게 여러 번 나누는 방식이 맞습니다.",
                "역배를 조합에 넣을 때는 하나까지만 넣는 것이 적중 확률을 지키는 방법입니다."]
    elif key == "ou":
        tips = [f"{me} 오버 비율이 {KH.pct(v)}라는 건 기준점이 실제 득점보다 {'낮게' if v > 0.52 else '높게' if v < 0.48 else '거의 정확하게'} 잡혀 왔다는 뜻입니다.",
                "다만 경기마다 두 팀의 최근 득실과 선발·결장 정보가 기준점을 더 크게 움직입니다. 리그 비율은 기본값으로만 씁니다."]
    elif key == "hc":
        tips = [f"{me}에서 핸디를 받은 쪽이 버틴 비율은 {KH.pct(v)}입니다. " + ("받는 쪽이 유리했던 리그라, 강팀 핸디는 신중하게 봅니다." if v > 0.52 else
                                                                   "주는 쪽(강팀)이 기준점을 자주 넘긴 리그입니다." if v < 0.48 else "기준점이 점수 차를 잘 맞혀 온 리그입니다."),
                "기준점 크기별 표에서 큰 기준점일수록 숫자가 어떻게 바뀌는지 보면, 이 리그 강팀이 보통 몇 점 차까지 벌리는지 감을 잡을 수 있습니다."]
    elif key == "goals":
        tips = [f"{me} 경기당 {v:.2f}골은 언더오버 2.5 기준점의 기본값이 됩니다. " + ("평균이 3골에 가까워 오버 쪽이 기본값입니다." if v >= 2.8 else "평균이 2.5골 안팎이라 두 팀 성향이 더 중요합니다." if v >= 2.4 else "득점이 적은 리그라 언더와 무승부를 같이 봅니다."),
                "한 경기 득점은 운이 크게 섞이니, 리그 평균과 두 팀 최근 득실을 함께 봅니다."]
    elif key == "draws":
        tips = [f"{me} 무승부 {KH.pct(v)}는 {round(1 / v) if v else '-'}경기에 한 번꼴입니다. 승무패 정배를 조합에 넣을 때 이 확률만큼 빗나갈 여지가 있다는 뜻입니다.",
                "전력이 비슷한 경기일수록 무승부가 늘어납니다. 무 배당이 낮게 붙은 경기는 따로 살펴봅니다."]
    elif key == "o25":
        tips = [f"{me}에서 2.5골을 넘긴 경기는 {KH.pct(v)}입니다. " + ("오버가 기본값인 리그입니다." if v > 0.55 else "언더가 기본값인 리그입니다." if v < 0.45 else "거의 반반이라 경기마다 따로 봅니다."),
                "기준점이 3.5처럼 높게 잡힌 경기는 시장이 이미 고득점을 예상한 경기라, 리그 평균보다 두 팀 기록을 더 봅니다."]
    else:
        return []
    return [("이 숫자를 고를 때 쓰는 법", tips)]


def enrich(arts: list, games, ou, hc, fd) -> None:
    """A 객체 목록을 제자리에서 보강한다."""
    met = _metrics(games, ou, hc)
    by_name = {lk: (lk, m) for lk, m in met.items()}  # 리그 이름 표기가 달라도(띄어쓰기) 같은 리그로
    fdst = KH._fd_stats(fd)
    fd_name = {KH.FD_NAME.get(c, c): c for c in fdst}
    same_league = defaultdict(list)
    for a in arts:
        if a and a.league:
            same_league[a.league].append(a)
    for a in arts:
        if not a or not a.league:
            continue
        key = a.slug.split("-")[0]
        if key not in TOPIC:
            continue
        extra = []
        if key in ("goals", "draws", "o25", "fav", "home") and a.league in fd_name:
            fk = {"goals": "goals", "draws": "draw", "o25": "o25", "fav": "fav16", "home": "home"}[key]
            rows = [(KH.FD_NAME.get(c, c), s[fk]) for c, s in fdst.items()]
            v = fdst[fd_name[a.league]][fk]
            hl = {"draws": ("무승부가 잦은", "무승부가 드문"), "fav": ("정배(1.6 미만)가 잘 맞는", "정배(1.6 미만)가 자주 흔들리는"),
                  "home": ("홈 이점이 큰", "홈 이점이 작은")}.get(key, ("골이 많은", "골이 적은"))
            extra += _compare(key, a.league, rows, "유럽 축구", *hl)
            extra.append(("기록의 범위", [f"{KH.esc(a.league)} 최근 여러 시즌 {fdst[fd_name[a.league]]['n']:,}경기의 해외 마감 배당과 실제 결과로 계산했습니다. "
                                      "한 시즌만 보면 출렁임이 크기 때문에 여러 시즌을 합쳐 보고, 새 경기가 끝날 때마다 자동으로 다시 계산합니다."]))
            extra += _howto(key, a.league, v)
        elif a.league.replace(" ", "") in by_name:
            lk, m = by_name[a.league.replace(" ", "")]
            sp = m["sport"]
            rows = [(a.league if k2 == lk else x["name"], x[key]) for k2, x in met.items() if x["sport"] == sp]
            hi, lo = {"fav": ("정배가 잘 맞는", "정배가 자주 흔들리는"), "home": ("홈 이점이 큰", "홈 이점이 작은"), "upset": ("이변이 잦은", "이변이 드문"),
                      "ou": ("오버가 잦은", "언더가 잦은"), "hc": ("받는 쪽이 잘 버틴", "주는 쪽이 잘 벌린")}[key]
            extra += _compare(key, a.league, rows, SPORT_KO.get(sp, ""), hi, lo)
            extra += _howto(key, a.league, m[key])
            rv = _recent(key, lk, games, ou, hc)
            if rv is not None and m[key] is not None:
                d = rv - m[key]
                extra.append(("최근 흐름", [f"가장 최근 100경기만 떼어 보면 {TOPIC[key][0]}은 {KH.pct(rv)}로, 전체 기록({KH.pct(m[key])})보다 {KH.pp(d)} "
                                          + ("높습니다. 최근 들어 이 경향이 강해졌습니다." if d > 0.03 else "낮습니다. 최근 들어 이 경향이 약해졌습니다." if d < -0.03 else "차이로, 전체 기록과 비슷하게 이어지고 있습니다.")]))
            extra.append(("기록의 범위", [f"베트맨 발매 {KH.esc(a.league)} {m['n']:,}경기의 베트맨 배당과 공식 결과로 계산했습니다. "
                                      "베트맨에 발매되지 않은 경기는 들어가지 않으며, 새 회차 결과가 나올 때마다 자동으로 다시 계산합니다."]))
        else:
            continue
        rel = [x for x in same_league.get(a.league, []) if x is not a][:5]
        if rel:
            links = " · ".join(f'<a href="/knowhow/{x.slug}/">{KH.esc(x.title)}</a>' for x in rel)
            extra.append(("같은 리그 다른 글", [f"{KH.esc(a.league)} 숫자를 다른 각도로 본 글입니다: {links}",
                                            '두 팀이 직접 만났을 때의 기록은 <a href="/vs/">상대전적</a>에서 볼 수 있습니다.']))
        if extra:
            a.sections = list(a.sections) + extra
