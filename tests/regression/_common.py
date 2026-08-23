"""회귀 테스트 공통 경로 설정."""
import os
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[2])

# 크로미엄 경로. 이 저장소의 개발 컨테이너에는 /opt/pw-browsers/chromium 이 있고,
# CI 등에서 `playwright install` 로 받았다면 경로를 비워 두면 된다 — playwright가
# 알아서 찾는다. 빈 문자열이 실행 파일 경로로 넘어가면 기동에 실패하므로 None으로 바꾼다.
_env = (os.environ.get("PLAYWRIGHT_CHROMIUM") or "").strip()
if _env:
    CHROMIUM = _env
elif Path("/opt/pw-browsers/chromium").exists():
    CHROMIUM = "/opt/pw-browsers/chromium"
else:
    CHROMIUM = None          # playwright 기본 위치 사용
