"""Vercel FastAPI entrypoint."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from classroom_sim.web.server import app  # noqa: E402

__all__ = ["app"]
