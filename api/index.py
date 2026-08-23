"""Vercel 진입점 — 서버리스 함수 하나가 FastAPI 앱 전체를 받는다.

Vercel의 Python 런타임은 이 파일에서 `app`(ASGI)을 찾는다. 라우팅은
`vercel.json`의 rewrite가 모든 경로를 여기로 보내고, FastAPI가 나눠 맡는다.

서버리스에서 달라지는 것은 `web/store.py`의 `stateless()`가 판단한다 —
Vercel이 넣어 주는 VERCEL 환경변수를 보고 디스크 저장을 전부 끈다.
"""

import sys
from pathlib import Path

# 저장소 루트/src 를 임포트 경로에 넣는다 (Vercel은 패키지를 설치하지 않는다)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from classroom_sim.web.server import app  # noqa: E402

__all__ = ["app"]
