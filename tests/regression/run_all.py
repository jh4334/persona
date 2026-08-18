"""회귀 스위트 일괄 실행 — python tests/regression/run_all.py

각 test_cycle*.py를 순서대로 별도 프로세스로 실행하고 결과를 요약한다.
실패한 스위트가 있어도 끝까지 돌린 뒤 종료 코드 1로 알린다.
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def main() -> int:
    tests = sorted(HERE.glob("test_cycle*.py"),
                   key=lambda p: int("".join(ch for ch in p.stem if ch.isdigit())))
    if not tests:
        print("실행할 테스트가 없습니다.")
        return 1
    failures = []
    t0 = time.time()
    for t in tests:
        # 스위트 간 격리: 이전 스위트가 남긴 세션 스냅샷·학급이 다음 가정을 깨지 않게
        shutil.rmtree(REPO / ".sessions", ignore_errors=True)
        shutil.rmtree(REPO / ".classrooms", ignore_errors=True)
        started = time.time()
        r = subprocess.run([sys.executable, str(t)], cwd=str(HERE),
                           capture_output=True, text=True)
        took = time.time() - started
        ok = r.returncode == 0
        print(f"{'✅' if ok else '❌'} {t.name:22s} {took:5.1f}s")
        if not ok:
            failures.append(t.name)
            tail = (r.stdout + "\n" + r.stderr).strip().splitlines()[-15:]
            print("   └─ " + "\n      ".join(tail))
    print(f"\n총 {len(tests)}개 · 실패 {len(failures)}개 · {time.time() - t0:.0f}초")
    if failures:
        print("실패:", ", ".join(failures))
        return 1
    print("ALL REGRESSION PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
