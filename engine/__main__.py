"""사용법

  python -m engine run              # 오늘 수집·분석 + 최근 7일 채점 (자동 실행용)
  python -m engine collect [--date YYYY-MM-DD] [--refresh]
  python -m engine grade
  python -m engine build            # dist/ 에 정적 사이트 생성
  DEMO=1 DATA_DIR=.demo python -m engine demo   # 샘플 데이터로 미리보기
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import config


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="engine")
    ap.add_argument("cmd", choices=["run", "collect", "grade", "build", "demo", "indexnow"])
    ap.add_argument("--date", default=None)
    ap.add_argument("--refresh", action="store_true", help="해외 배당 캐시 무시")
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--no-scores", action="store_true", help="외부 결과 API 호출 생략(크레딧 절약)")
    a = ap.parse_args(argv)

    from . import pipeline

    day = a.date or config.today_kst()
    if a.cmd == "collect":
        pipeline.collect(day, refresh_ref=a.refresh)
    elif a.cmd == "grade":
        pipeline.grade(day, fetch_scores=not a.no_scores)
    elif a.cmd == "run":
        # 채점을 먼저 해서 Elo·보정값이 최신 상태로 분석에 들어가게 한다.
        failed = False
        pipeline.history(int(a.days if a.days != 21 else 8))
        try:
            pipeline.grade(day, fetch_scores=not a.no_scores)
        except Exception:  # noqa: BLE001
            logging.exception("채점 실패(수집은 계속)")
            failed = True
        pipeline.collect(day, refresh_ref=a.refresh)
        return 1 if failed else 0
    elif a.cmd == "demo":
        if not config.DEMO:
            print("DEMO=1 환경변수가 필요합니다.", file=sys.stderr)
            return 2
        pipeline.demo(a.days)
    elif a.cmd == "indexnow":
        from .indexnow import ping
        ping()
    elif a.cmd == "build":
        from .site.build import build
        build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
