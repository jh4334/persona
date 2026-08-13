"""uvicorn 실행 래퍼.

    PYTHONPATH=src python -m classroom_sim.web --port 8000
    PYTHONPATH=src CLASSROOM_SIM_FAKE=1 python -m classroom_sim.web  # 엔진 없이 개발
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m classroom_sim.web", description="보이는 교실 웹 서버")
    ap.add_argument("--host", default="127.0.0.1", help="바인드 주소 (기본 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8000, help="포트 (기본 8000)")
    ap.add_argument("--reload", action="store_true", help="코드 변경 시 자동 재시작")
    ap.add_argument(
        "--fake",
        action="store_true",
        help="무대 엔진 대신 개발용 FakeSession 사용 (CLASSROOM_SIM_FAKE=1 과 동일)",
    )
    args = ap.parse_args()

    if args.fake:
        os.environ["CLASSROOM_SIM_FAKE"] = "1"

    import uvicorn

    uvicorn.run(
        "classroom_sim.web.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
