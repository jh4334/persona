"""보이는 교실 — 웹 UI 패키지.

- `server.py`  : FastAPI 앱 (`classroom_sim.web.server:app`)
- `dev_fake.py`: 엔진 없이 프론트를 개발·테스트하기 위한 FakeSession
- `static/`    : 바닐라 JS 프론트엔드 (외부 CDN·라이브러리 없음)

실행:
    PYTHONPATH=src python -m classroom_sim.web --port 8000
"""

__all__ = ["server"]
