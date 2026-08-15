from _common import ROOT, CHROMIUM
"""Cycle 13 verification: per-session turn cap + create rate limit."""
import shutil, sys, os
sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)

from pathlib import Path

shutil.rmtree(Path(ROOT) / ".sessions", ignore_errors=True)

from fastapi.testclient import TestClient
import classroom_sim.web.server as server

client = TestClient(server.app)

def create():
    return client.post("/api/sessions", json={
        "classroom_path": "personas/class_6_3.json",
        "lesson_path": "lessons/ratio_and_rate.md",
        "backend": "mock",
    })

# ① 턴 상한: 상한 도달 후 일반 입력은 429, /상태·/종료는 허용
r = create()
sid = r.json()["session_id"]
rec = server.SESSIONS[sid]
rec.session.state.turn = server.MAX_TURNS_PER_SESSION  # 200턴을 실제로 돌리는 대신 직접 설정
r = client.post(f"/api/sessions/{sid}/turn", json={"input": "한 마디 더"})
assert r.status_code == 429, r.text
assert "턴 상한" in r.json()["detail"]
r = client.post(f"/api/sessions/{sid}/turn", json={"input": "/상태"})
assert r.status_code == 200, "/상태가 막힘"
r = client.post(f"/api/sessions/{sid}/turn", json={"input": "/종료"})
assert r.status_code == 200 and r.json()["ended"], "/종료가 막힘"
print("① 턴 상한 (일반 429, /상태·/종료 허용) OK")

# ② 상한 임박 안내(notice)
r = create()
sid = r.json()["session_id"]
server.SESSIONS[sid].session.state.turn = server.TURNS_WARN_AT - 1
r = client.post(f"/api/sessions/{sid}/turn", json={"input": "따라와 볼까요"})
assert r.status_code == 200
assert "턴째입니다" in (r.json().get("notice") or ""), r.json().get("notice")
print("② 상한 임박 안내 OK")

# ③ 생성 속도 제한: 같은 IP에서 한도 초과 시 429
made = 2  # 위에서 이미 2회 생성
while made < server.CREATE_RATE_LIMIT:
    assert create().status_code == 200
    made += 1
r = create()
assert r.status_code == 429, f"속도 제한 미동작: {r.status_code}"
assert "너무 잦습니다" in r.json()["detail"]
print("③ 세션 생성 속도 제한 OK")

# ④ 시간이 지나면 다시 허용 (기록 조작으로 시간 경과 시뮬레이션)
with server._CREATE_GUARD:
    server._CREATE_TIMES["testclient"] = [t - server.CREATE_RATE_WINDOW - 1
                                          for t in server._CREATE_TIMES["testclient"]]
assert create().status_code == 200
print("④ 윈도 경과 후 재허용 OK")

shutil.rmtree(Path(ROOT) / ".sessions", ignore_errors=True)
shutil.rmtree(Path(ROOT) / "reports" / "stage", ignore_errors=True)
print("CYCLE13 ALL PASS")
