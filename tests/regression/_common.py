"""회귀 테스트 공통 경로 설정."""
import os
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[2])
CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM", "/opt/pw-browsers/chromium")
