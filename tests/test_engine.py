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


class OddsBook(unittest.TestCase):
    def test_build_lookup(self):
        from engine.analysis import oddsbook as OB
        rows = []
        for i in range(100):  # 1.25배 정배 100번 중 85번 적중, 승패 농구
            rows.append(["basketball", "NBA", "WL", 0, 1.25, 0, 3.4, 0 if i < 85 else 2, 0, 0])
        book = OB.build(rows)
        s = OB.lookup(book, "basketball", "WL", "H", 1.27)
        self.assertEqual(s["n"], 100)
        self.assertAlmostEqual(s["hit"], 0.85)
        self.assertAlmostEqual(s["roi"], 0.85 * 1.25 - 1, places=3)
        p, info = OB.hist_probs(book, {"sport": "basketball", "market": "WL", "odds": {"H": 1.25, "A": 3.4}})
        self.assertGreater(p["H"], 0.75)


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


if __name__ == "__main__":
    unittest.main()
