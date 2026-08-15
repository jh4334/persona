from _common import ROOT, CHROMIUM
"""Cycle 12 verification: codex subprocess group kill, turn time budget."""
import os, stat, subprocess, sys, tempfile, time
sys.path.insert(0, f"{ROOT}/src")

from pathlib import Path
from classroom_sim.personas import load_classroom
from classroom_sim.stage.backend import BackendError, CodexBackend, make_backend
from classroom_sim.stage.session import StageSession, TURN_TIME_BUDGET

tmp = Path(tempfile.mkdtemp())

# ── 가짜 codex: 손자 프로세스(sleep)를 남기고 자신도 잠드는 스크립트 ──
fake = tmp / "fake_codex"
child_pid_file = tmp / "child.pid"
fake.write_text(f"""#!/bin/bash
sleep 1000 &
echo $! > {child_pid_file}
sleep 1000
""", encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

# ① 타임아웃 시 손자 프로세스까지 죽는가
be = CodexBackend(codex_bin=str(fake), timeout=2)
t0 = time.monotonic()
try:
    be.complete_text(system="s", messages=[{"role": "user", "content": "hi"}])
    raise AssertionError("타임아웃이 나지 않음")
except BackendError as e:
    assert "초 안에 오지 않았습니다" in str(e), e
took = time.monotonic() - t0
assert took < 15, f"타임아웃 처리에 {took:.1f}초"
time.sleep(0.5)
child_pid = int(child_pid_file.read_text().strip())

def running(pid):
    """좀비(Z)는 이미 죽은 것 — kill(pid,0) 성공만으로는 생존이라 볼 수 없다."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            state = f.read().rsplit(") ", 1)[-1].split()[0]
        return state not in ("Z", "X")
    except OSError:
        return False

assert not running(child_pid), f"손자 프로세스 {child_pid}가 실행 중 (프로세스 트리 정리 실패)"
print("① 타임아웃 시 프로세스 그룹째 정리 OK")

# ② deadline이 per-call timeout보다 짧으면 deadline이 이긴다
be2 = CodexBackend(codex_bin=str(fake), timeout=300)
be2.deadline = time.monotonic() + 3
t0 = time.monotonic()
try:
    be2.complete_text(system="s", messages=[{"role": "user", "content": "hi"}])
    raise AssertionError("deadline 타임아웃이 나지 않음")
except BackendError:
    pass
assert time.monotonic() - t0 < 15, "deadline이 무시됨"
print("② 턴 마감이 개별 타임아웃보다 우선 OK")

# ③ 예산 소진 후 호출은 프로세스도 안 띄우고 즉시 실패
be2.deadline = time.monotonic() + 1
t0 = time.monotonic()
try:
    be2.complete_text(system="s", messages=[{"role": "user", "content": "hi"}])
    raise AssertionError("예산 소진인데 실행됨")
except BackendError as e:
    assert "시간 예산" in str(e), e
assert time.monotonic() - t0 < 1, "즉시 실패가 아님"
print("③ 예산 소진 시 즉시 실패 OK")

# ④ 세션이 턴 동안 deadline을 걸고, 턴이 끝나면 해제하는가
classroom = load_classroom(f"{ROOT}/personas/class_6_3.json")
lesson = open(f"{ROOT}/lessons/ratio_and_rate.md", encoding="utf-8").read()

class SpyBackend:
    """mock처럼 동작하되 deadline 설정 여부를 기록"""
    def __init__(self):
        self._mock = make_backend("mock")
        self.deadline = None
        self.seen = []
    def complete_text(self, **kw):
        self.seen.append(self.deadline)
        return self._mock.complete_text(**kw)
    def complete_json(self, **kw):
        self.seen.append(self.deadline)
        return self._mock.complete_json(**kw)

spy = SpyBackend()
sess = StageSession(classroom, lesson, spy, seed=1)
sess.turn("여러분 안녕하세요")
assert spy.seen and all(d is not None for d in spy.seen), "턴 중 deadline 미설정"
assert spy.deadline is None, "턴 종료 후 deadline이 해제되지 않음"
lo = spy.seen[0] - time.monotonic()
assert 0 < lo <= TURN_TIME_BUDGET + 1, f"예산 크기 이상: {lo}"
print(f"④ 턴 예산 설정·해제 OK (LLM 호출 {len(spy.seen)}회 모두 마감 안에서)")

# ⑤ mock/anthropic 경로 회귀 없음 (deadline 없는 백엔드)
sess2 = StageSession(classroom, lesson, make_backend("mock"), seed=1)
r = sess2.turn("비와 비율을 배워봅시다")
assert any(e.kind.startswith("student") for e in r.events)
print("⑤ 일반 백엔드 회귀 없음 OK")

import shutil
shutil.rmtree(tmp, ignore_errors=True)
print("CYCLE12 ALL PASS")
