import math
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())

from engine.analysis import combos as C  # noqa: E402
from engine.analysis.grading import grade_report, settle  # noqa: E402
from engine.analysis.probability import combine, remove_margin_power, remove_margin_proportional, shrink  # noqa: E402
from engine.schema import InvalidMarket, validate  # noqa: E402


def mk(i, odds, market="1X2", league="L", day="2026-11-16", **kw):
    m = {"id": f"t{i}", "league": league, "home": f"H{i}", "away": f"A{i}", "market": market,
         "kickoff": f"{day}T20:00:00+09:00", "odds": odds, "sport": "soccer", "pool": "proto"}
    m.update(kw)
    return m


class Probability(unittest.TestCase):
    def test_power_sums_to_one_and_favours_favourite(self):
        o = {"H": 1.30, "D": 4.20, "A": 7.50}
        pw, pr = remove_margin_power(o), remove_margin_proportional(o)
        self.assertAlmostEqual(sum(pw.values()), 1, places=6)
        self.assertGreater(pw["H"], pr["H"])  # 롱샷 편향 보정
        self.assertLess(pw["A"], pr["A"])

    def test_combine_handles_missing(self):
        self.assertEqual(combine([]), {})
        p = combine([({"H": .6, "A": .4}, 1), (None, 1)])
        self.assertAlmostEqual(p["H"], .6, places=6)

    def test_shrink(self):
        p = shrink({"H": .9, "A": .1}, .1)
        self.assertAlmostEqual(p["H"], .86)


class Schema(unittest.TestCase):
    def test_rejects_bad_odds(self):
        with self.assertRaises(InvalidMarket):
            validate(mk(1, {"H": 0.9, "D": 3, "A": 3}))
        with self.assertRaises(InvalidMarket):
            validate(mk(1, {"H": 1.5, "A": 2.5}))  # 1X2 인데 무 배당 누락
        with self.assertRaises(InvalidMarket):
            validate(mk(1, {"H": 3.3, "D": 3.3, "A": 3.3}))  # 합 < 1 (오타 가능성)

    def test_same_team(self):
        m = mk(1, {"H": 1.5, "D": 3.5, "A": 5})
        m["away"] = m["home"]
        with self.assertRaises(InvalidMarket):
            validate(m)


class Settle(unittest.TestCase):
    def test_markets(self):
        self.assertEqual(settle(mk(1, {}), {"home_score": 2, "away_score": 2}), "D")
        self.assertEqual(settle(mk(1, {}, market="WL", sport="basketball"), {"home_score": 90, "away_score": 80}), "H")
        self.assertEqual(settle(mk(1, {"H": 1.8, "A": 1.8}, market="HANDICAP", line=-5.5, sport="basketball"),
                                {"home_score": 90, "away_score": 86}), "A")
        self.assertEqual(settle(mk(1, {}, market="OU", line=200.5), {"home_score": 100, "away_score": 101}), "O")
        self.assertEqual(settle(mk(1, {}), {"status": "CANCELLED"}), "VOID")
        self.assertIsNone(settle(mk(1, {}), {"status": "LIVE"}))


def analyzed(i, p, odds, **kw):
    m = mk(i, odds, **kw)
    pick = max(p, key=p.get)
    m["analysis"] = {"p": p, "pick": pick, "value_key": pick, "confidence": 70, "upset_risk": 20}
    return m


class Combos(unittest.TestCase):
    def setUp(self):
        self.ms = [analyzed(i, {"H": .75, "D": .15, "A": .10}, {"H": 1.25, "D": 5, "A": 9}, league="L" if i < 3 else f"X{i}")
                   for i in range(8)]

    def test_no_duplicate_match_and_correlation(self):
        dup = analyzed(99, {"H": .75, "D": .15, "A": .10}, {"H": 1.25, "D": 5, "A": 9})
        dup.update(home="H0", away="A0")
        legs = C.legs_from(self.ms + [dup])
        for name in C.STRATEGIES:
            for c in C.strategy_combos(legs, name):
                self.assertEqual(len({l["match"] for l in c["legs"]}), c["size"])
        same = [l for l in legs if l["league"] == "L"][:2]
        self.assertLess(C.joint_prob(same), .75 * .75)

    def test_total_odds_truncated(self):
        legs = C.legs_from(self.ms[:3])
        self.assertEqual(C.total_odds(legs), math.floor(1.25 ** 3 * 100) / 100)

    def test_kelly_zero_when_negative(self):
        self.assertEqual(C.kelly(.4, 2.0), 0)
        self.assertGreater(C.kelly(.6, 2.0), 0)


class Grading(unittest.TestCase):
    def test_combo_void_counts_as_one(self):
        ms = [analyzed(i, {"H": .7, "A": .3}, {"H": 1.5, "A": 2.6}, market="WL") for i in range(3)]
        legs = C.legs_from(ms)
        combo = C.build_combo(legs)
        combo.update(strategy="safe", rank=1)
        rep = {"markets": ms, "combos": {"safe": [combo]}, "value_picks": []}
        res = {"markets": {"t0": {"home_score": 2, "away_score": 1}, "t1": {"status": "CANCELLED"},
                           "t2": {"home_score": 3, "away_score": 0}}}
        grade_report(rep, res)
        c = rep["combos"]["safe"][0]
        self.assertEqual(c["result"], "win")
        self.assertEqual(c["return"], int(10000 * 2.25 // 10 * 10))


class BetmanParse(unittest.TestCase):
    def test_parse_columnar(self):
        from engine.sources.betman import parse_round
        ko = 1795000000000
        base = dict(itemCode="SC", leagueName="EPL", homeName="맨체스C", awayName="리버풀", gameDate=ko,
                    gameReject="0", buyReject="0", winHandi=0, winTxt="승", loseTxt="패")
        rows = [
            dict(base, matchSeq=1, betNm="축구 승무패", winAllot=1.85, drawAllot=3.4, loseAllot=3.6),
            dict(base, matchSeq=2, betNm="축구 전반 승무패", winAllot=2.5, drawAllot=2.0, loseAllot=4.0),
            dict(base, matchSeq=3, betNm="축구 언더오버", winHandi=2.5, winTxt="언더", loseTxt="오버", winAllot=1.7, drawAllot=0, loseAllot=1.9),
            dict(base, matchSeq=4, itemCode="BK", leagueName="KBL", betNm="농구 핸디캡", winHandi=-3.5, winAllot=1.75, drawAllot=0, loseAllot=1.8),
            dict(base, matchSeq=5, itemCode="VL", leagueName="KOVO남", betNm="배구 승패", winAllot=0, drawAllot=0, loseAllot=0),
            dict(base, matchSeq=6, itemCode="BS", betNm="야구 승패", winAllot=1.5, drawAllot=0, loseAllot=2.3, gameReject="1"),
        ]
        payload = {"compSchedules": {"keys": list(rows[0].keys()) + ["betNm", "matchSeq", "winAllot", "drawAllot", "loseAllot"],
                                     "datas": []}}
        keys = sorted({k for r in rows for k in r})
        payload["compSchedules"] = {"keys": keys, "datas": [[r.get(k) for k in keys] for r in rows]}
        out = {m["game_no"]: m for m in parse_round(payload, "260133")}
        self.assertEqual(set(out), {1, 3, 4})  # 전반·미발매·취소 제외
        self.assertEqual(out[1]["market"], "1X2")
        self.assertEqual(out[3]["odds"], {"U": 1.7, "O": 1.9})
        self.assertEqual(out[4]["sport"], "basketball")
        self.assertEqual(out[4]["line"], -3.5)
        from engine.schema import validate
        for m in out.values():
            validate(dict(m))


class BetmanResults(unittest.TestCase):
    def test_codes_not_adjusted_scores(self):
        from engine.analysis.grading import settle
        from engine.sources.betman import parse_results
        keys = ["matchSeq", "mchScore", "gameReject", "gameResult", "betNm", "winTxt"]
        rows = [
            [1, "106:113", "0", "2", "농구 승패", "승"],
            [2, "114.5:113", "0", "0", "농구 핸디캡", "승"],   # 핸디 적용 점수: 홈 핸디승
            [3, "219:0", "0", "0", "농구 언더오버", "언더"],    # 합계: 언더
            [4, "266:0", "0", "2", "농구 언더오버", "언더"],    # 합계: 오버
            [5, None, "0", None, "축구 승무패", "승"],
            [6, None, "1", None, "축구 승무패", "승"],
            [7, "1:1", "0", "1", "축구 승무패", "승"],
        ]
        r = parse_results({"compSchedules": {"keys": keys, "datas": rows}}, "260133")
        g = lambda n: r[f"betman:G101:260133:{n}"]
        self.assertEqual(g(1)["outcome"], "A")
        self.assertEqual(g(1)["away_score"], 113)
        self.assertEqual(g(2)["outcome"], "H")
        self.assertNotIn("home_score", g(2))  # 조정 점수는 Elo 에 쓰지 않는다
        self.assertEqual(g(3)["outcome"], "U")
        self.assertEqual(g(4)["outcome"], "O")
        self.assertNotIn("betman:G101:260133:5", r)
        self.assertEqual(g(6)["status"], "CANCELLED")
        self.assertEqual(g(7)["outcome"], "D")
        m = mk(2, {"H": 1.7, "A": 1.8}, market="HANDICAP", line=8.5, sport="basketball")
        self.assertEqual(settle(m, g(2)), "H")


class XBook(unittest.TestCase):
    """해외 기록 구도표: 베트맨 기록 없이 해외 배당 + 실제 점수만으로 센다."""

    def setUp(self):
        from engine.analysis import xbook as X
        self.X = X
        soccer = []
        for i in range(400):  # 홈 60%·무 24%·원정 16% 구도. 홈 2-0 승 240, 1-1 96, 0-1 64
            hg, ag, res = (2, 0, 0) if i < 240 else (1, 1, 1) if i < 336 else (0, 1, 2)
            soccer.append([1.6, 4.0, 6.0, res, 1.9, 1.9, hg + ag, hg, ag])
        nba = [[0.7, 110 if i % 10 < 7 else 100, 100 if i % 10 < 7 else 108, 212.5] for i in range(300)]  # 70% 팀이 70% 승리, 10점 차
        self.book = X.build(soccer, {"nba": nba, "mlb": []})

    def test_soccer_all_markets(self):
        X, b = self.X, self.book
        x = {"h2h": {"H": 0.6, "D": 0.24, "A": 0.16}, "total": [2.5, 0.5]}
        r = X.market_stat(b, {"sport": "soccer", "market": "1X2", "odds": {"H": 1.5, "D": 3.9, "A": 5.8}, "x": x, "line": None})
        self.assertAlmostEqual(r["p"]["H"], 0.6, places=3)
        h = X.market_stat(b, {"sport": "soccer", "market": "HANDICAP", "odds": {"H": 2.0, "D": 3.5, "A": 2.8}, "x": x, "line": -2.0})
        self.assertAlmostEqual(h["p"]["D"], 0.6, places=3)   # 2-0 승은 핸디 -2 에서 무
        o = X.market_stat(b, {"sport": "soccer", "market": "OU", "odds": {"O": 1.5, "U": 2.5}, "x": x, "line": 1.5})
        self.assertAlmostEqual(o["p"]["O"], 336 / 400, places=3)  # 2골 경기 336개만 1.5 오버
        self.assertIsNone(X.market_stat(b, {"sport": "soccer", "market": "1X2", "odds": {"H": 1.5, "D": 3.9, "A": 5.8}, "x": {}, "line": None}))

    def test_us_and_old_values(self):
        X, b = self.X, self.book
        x = {"h2h": {"H": 0.7, "A": 0.3}, "total": [212.5, 0.5]}
        w = X.market_stat(b, {"sport": "basketball", "market": "WL", "odds": {"H": 1.3, "A": 3.4}, "x": x, "line": None})
        self.assertAlmostEqual(w["p"]["H"], 0.7, places=3)
        hc = X.market_stat(b, {"sport": "basketball", "market": "HANDICAP", "odds": {"H": 1.8, "A": 1.8}, "x": x, "line": -12.5})
        self.assertEqual(hc["p"]["H"], 0)                    # 10점 차 승리는 -12.5 를 못 넘는다
        self.assertFalse(X.is_x({"bucket": "1.3배대", "hit": 0.8}))  # 예전 베트맨 구간 값은 해외 기록으로 쓰지 않는다
        self.assertTrue(X.is_x({"bucket": "NBA", "hit": 0.7}))


class Derive(unittest.TestCase):
    def test_line_conversion(self):
        from engine.analysis import derive as D
        x = {"spread": [-7.5, 0.5], "total": [229.5, 0.5]}
        h = D.normal_market("basketball", x, "HANDICAP", -8.5, {"H", "A"})
        self.assertLess(h["H"], 0.5)                      # 더 큰 핸디를 주면 홈 커버 확률은 내려간다
        o = D.normal_market("basketball", x, "OU", 224.5, {"O", "U"})
        self.assertGreater(o["O"], 0.5)                   # 기준점이 낮아지면 오버 확률은 올라간다
        lam = D.fit_soccer({"H": 0.655, "D": 0.21, "A": 0.135}, (2.5, 0.56))
        hc = D.soccer_market(lam, "HANDICAP", -1.0, {"H", "D", "A"})
        self.assertAlmostEqual(sum(hc.values()), 1, places=6)
        self.assertLess(hc["H"], 0.655)


class Pipeline(unittest.TestCase):
    def test_demo_end_to_end_and_lock(self):
        from engine import config, pipeline
        config.DEMO = True
        try:
            day = (config.now_kst() - timedelta(days=1)).strftime("%Y-%m-%d")
            r1 = pipeline.collect(day)
            self.assertTrue(r1["markets"])
            first_pick = {m["id"]: m["analysis"]["pick"] for m in r1["markets"] if m.get("analysis")}
            # 다시 수집해도 킥오프가 지난 경기의 픽은 바뀌지 않는다
            r2 = pipeline.collect(day)
            for m in r2["markets"]:
                if m.get("analysis"):
                    self.assertEqual(first_pick[m["id"]], m["analysis"]["pick"])
            perf = pipeline.grade(config.today_kst())
            self.assertGreater(perf["picks"]["all"]["n"], 0)
        finally:
            config.DEMO = False


class PickRule(unittest.TestCase):
    def test_lean_not_pick_and_single(self):
        from engine.analysis.grading import is_pick
        from engine.analysis import combos as C
        self.assertFalse(is_pick({"pick_prob": 0.52}))
        self.assertTrue(is_pick({"pick_prob": 0.55}))

        def mk(i, p, o, single):
            return {"id": f"m{i}", "pool": "proto", "odds": {"H": o, "A": 2.0}, "kickoff": "2026-11-18T10:00+09:00", "home": f"h{i}", "away": f"a{i}",
                    "league": "NBA", "sport": "basketball", "market": "WL", "line": None, "round": "260136", "single": single,
                    "analysis": {"pick": "H", "p": {"H": p, "A": 1 - p}, "pick_prob": p, "confidence": 60, "upset_risk": 20, "x_odds": {"H": o}}}
        res = C.all_combos([mk(1, 0.6, 1.7, True), mk(2, 0.6, 1.7, False), mk(3, 0.7, 1.2, True), mk(4, 0.52, 1.9, True)])
        got = [c["legs"][0]["market_id"] for c in res["single"]]
        self.assertEqual(got, ["m1"])  # 단폴 불가·똥배(1.2)·박빙(52%)은 빠진다


if __name__ == "__main__":
    unittest.main()


class SalesDay(unittest.TestCase):
    """구매일: 08:00~23:00 구매, 23시에 다음 날로, 08:30 전 킥오프는 전날 구매일."""

    def test_boundaries(self):
        from datetime import datetime
        from unittest import mock
        from engine import config as c
        self.assertEqual(c.sales_day("2026-11-18T04:45:00+09:00"), "2026-11-17")
        self.assertEqual(c.sales_day("2026-11-18T08:30:00+09:00"), "2026-11-18")
        with mock.patch.object(c, "now_kst", lambda: datetime.fromisoformat("2026-11-17T22:59:00+09:00")):
            self.assertEqual(c.today_kst(), "2026-11-17")
        with mock.patch.object(c, "now_kst", lambda: datetime.fromisoformat("2026-11-17T23:00:00+09:00")):
            self.assertEqual(c.today_kst(), "2026-11-18")


class Intl(unittest.TestCase):
    def test_rating_and_markets(self):
        from engine.sources import intl_history as I
        rows = ["date,home_team,away_team,home_score,away_score,tournament,city,country,neutral"]
        for i in range(400):  # 한국이 카타르에 꾸준히 이기는 기록 + 비교용 다른 경기
            rows.append(f"2010-01-{1 + i % 28:02d},South Korea,Qatar,2,0,Friendly,X,X,FALSE")
            rows.append(f"2010-01-{1 + i % 28:02d},Qatar,South Korea,0,1,Friendly,X,X,FALSE")
        b = I.build("\n".join(rows))
        self.assertGreater(b["teams"]["South Korea"][0], b["teams"]["Qatar"][0])
        st = I.stat("카타르", "한국", b)
        self.assertIsNotNone(st)
        self.assertGreater(st["A"], st["H"])
        p = I.market_probs(st, "OU", 2.5, {"O", "U"})
        self.assertAlmostEqual(p["O"] + p["U"], 1, places=6)


class ComboRound(unittest.TestCase):
    def test_same_round_only(self):
        from engine.analysis.combos import _valid
        a = {"match": "1", "round": "260136"}
        b = {"match": "2", "round": "260136"}
        c = {"match": "3", "round": "260137"}
        self.assertTrue(_valid([a, b]))
        self.assertFalse(_valid([a, c]))          # 회차가 다르면 한 장으로 살 수 없다
        self.assertFalse(_valid([a, dict(a)]))    # 같은 경기 중복


class FreeTier(unittest.TestCase):
    def test_odds_budget(self):
        from unittest import mock
        from engine.sources import odds_api as O
        with mock.patch.object(O, "_days_left", lambda: 10):
            with mock.patch.object(O, "_remaining", lambda: 200.0):
                self.assertTrue(O._credits_ok(refresh=True))    # 200-3 >= 10*12
            with mock.patch.object(O, "_remaining", lambda: 100.0):
                self.assertFalse(O._credits_ok(refresh=True))   # 월말까지 기본 수집 몫을 남긴다
                self.assertTrue(O._credits_ok())                # 기본 수집은 허용
            with mock.patch.object(O, "_remaining", lambda: 2.0):
                self.assertFalse(O._credits_ok())

    def test_betman_round_guess(self):
        from unittest import mock
        from engine.sources import betman as B
        with mock.patch.object(B, "read_json", lambda *a, **k: {"rounds": ["260136"]}):
            self.assertEqual([g["gmTs"] for g in B._guess_rounds()], [260136, 260137, 260138])


class InsightTest(__import__("unittest").TestCase):
    def test_josa(self):
        from engine.site.insight import j
        self.assertEqual(j("보스턴 셀틱스", "은는"), "보스턴 셀틱스는")
        self.assertEqual(j("미국", "은는"), "미국은")
        self.assertEqual(j("+2.0점", "으로"), "+2.0점으로")
        self.assertEqual(j("3.8골", "으로"), "3.8골로")
        self.assertEqual(j("", "은는"), "는")

    def test_small_sample_and_bad_data(self):
        from engine.site.insight import build
        g = {"sport": "basketball", "kickoff": "2026-11-18T10:00+09:00", "home": "A", "away": "B", "markets": []}
        few = {"games": [{"date": "2026-11-10", "me": 100, "op": 90, "res": "W"}] * 3}
        self.assertIsNone(build(g, few, few))
        self.assertIsNone(build(g, None, None))
        zero = {"games": [{"date": f"2026-11-{d:02d}", "me": 0, "op": 0, "res": "D"} for d in range(1, 12)]}
        out = build(g, zero, zero)
        self.assertTrue(out and out["notes"])

    def test_future_games_ignored(self):
        from engine.site.insight import metrics
        t = {"games": [{"date": "2026-11-20", "me": 1, "op": 0, "res": "W"}] * 10}
        self.assertIsNone(metrics(t, "soccer", "2026-11-18T10:00+09:00"))


class BetmanNoSaleTest(__import__("unittest").TestCase):
    def test_nosale_is_runtimeerror(self):
        from engine.sources.betman import NoSale
        self.assertTrue(issubclass(NoSale, RuntimeError))
