"""자동화가 끊기지 않게 지키는 검사.

정해진 시각·권한·쓰레드 재시도 연결이 어긋나면 여기서 바로 실패한다(세션이 바뀌어도 같은 실수를 반복하지 않게).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"


def _slots_in_worker() -> set[str]:
    src = (ROOT / "cron" / "worker.js").read_text(encoding="utf-8")
    block = src[src.index("const SCHEDULE"):src.index("};", src.index("const SCHEDULE"))]
    return set(re.findall(r'"\d{2}:\d{2}":\s*"([^"]+)"', block))


class AutomationTest(unittest.TestCase):
    def setUp(self):
        self.daily_src = (WF / "daily.yml").read_text(encoding="utf-8")

    def test_daily_can_start_threads_retry(self):
        # 이 권한이 빠지면 '쓰레드 다시 올리기' 시작 요청이 403 으로 거절된다(11/20 저녁 글 누락 원인)
        perms = self.daily_src[self.daily_src.index("\npermissions:"):self.daily_src.index("\njobs:")]
        self.assertRegex(perms, r"\n  actions: write")
        self.assertRegex(perms, r"\n  contents: write")
        self.assertTrue((WF / "threads.yml").exists())
        self.assertIn("threads.yml/dispatches", self.daily_src)

    def test_threads_retry_workflow(self):
        src = (WF / "threads.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", src)
        self.assertRegex(src[src.index("\npermissions:"):src.index("\njobs:")], r"\n  actions: write")
        for kind in ("analysis)", "result)", "kh)", "preview)"):
            self.assertIn(kind, src)

    def test_worker_slots_are_handled(self):
        # Worker 가 시작하는 시각마다 daily.yml 이 알고 있어야 한다
        slots = _slots_in_worker()
        self.assertTrue(slots)
        for s in slots:
            self.assertIn(s, self.daily_src, s)

    def test_watchdog_matches_worker(self):
        p = WF / "watchdog.yml"
        if not p.exists():
            return
        src = p.read_text(encoding="utf-8")
        block = src[src.index("const SCHEDULE"):src.index("};", src.index("const SCHEDULE"))]
        self.assertEqual(set(re.findall(r'"\d{2}:\d{2}":\s*"([^"]+)"', block)), _slots_in_worker())

    def test_no_long_sleep_in_daily(self):
        # 실행 안에서 오래 기다리면 무료 시간이 줄어 한 달 중간에 모든 실행이 멈춘다
        for m in re.finditer(r"sleep (\d+)", self.daily_src):
            self.assertLessEqual(int(m.group(1)), 60, m.group(0))


if __name__ == "__main__":
    unittest.main()


class BudgetTest(unittest.TestCase):
    def test_cycle_contains_now(self):
        from datetime import datetime, timezone
        from engine import budget
        s, e = budget._cycle()
        now = datetime.now(timezone.utc)
        self.assertTrue(s <= now < e)
        self.assertGreaterEqual((e - s).days, 28)

    def test_essential_slots_never_skipped(self):
        from engine import budget
        for slot in ("0 21 * * *", "0 22 * * *", "0 2 * * *", "0 6 * * *", "0 10 * * *", "5 14 * * *", "release"):
            self.assertNotIn(slot, budget.OPTIONAL)

    def test_chrome_setup_used(self):
        for wf in ("daily.yml", "threads.yml"):
            src = (WF / wf).read_text(encoding="utf-8")
            self.assertNotIn("playwright install", src, wf)  # 내려받기는 chrome.sh 안에서 미리 깔린 크롬이 없을 때만
        self.assertTrue((ROOT / ".github" / "scripts" / "chrome.sh").exists())


class PreviewTest(unittest.TestCase):
    def test_slots_cover_day_without_overlap(self):
        from engine import threads as TH
        spans = sorted(TH.PV_SLOTS.items())
        for (s1, (a1, b1)), (s2, (a2, b2)) in zip(spans, spans[1:]):
            self.assertEqual(b1, a2)          # 칸 사이에 빈 시간이 없다
            self.assertGreaterEqual(a1 - s1, 3)  # 킥오프 3시간 이상 전에 올라간다
        src = (WF / "daily.yml").read_text(encoding="utf-8")
        self.assertIn("--pv-prepare", src)
        self.assertIn("--pv-post", src)
