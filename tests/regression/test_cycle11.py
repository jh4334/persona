from _common import ROOT, CHROMIUM
"""Cycle 11 verification: session snapshots survive a server 'restart'."""
import importlib, json, shutil, sys, os
sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)

from pathlib import Path

shutil.rmtree(Path(ROOT) / ".sessions", ignore_errors=True)

from fastapi.testclient import TestClient
import classroom_sim.web.server as server

client = TestClient(server.app)
r = client.post("/api/sessions", json={
    "classroom_path": "personas/class_6_3.json",
    "lesson_path": "lessons/ratio_and_rate.md",
    "backend": "mock",
})
sid = r.json()["session_id"]
client.post(f"/api/sessions/{sid}/turn", json={"input": "오늘은 비를 배웁니다"})
client.post(f"/api/sessions/{sid}/turn", json={"input": "/판서 3 : 5"})
client.post(f"/api/sessions/{sid}/turn", json={"input": "/모둠 4인"})
state_before = client.get(f"/api/sessions/{sid}/state").json()
tr_before = client.get(f"/api/sessions/{sid}/transcript").json()

snap_file = Path(ROOT) / ".sessions" / f"{sid}.json"
assert snap_file.is_file(), "스냅샷 파일이 없음"
payload = json.loads(snap_file.read_text(encoding="utf-8"))
assert payload["snapshot"]["state"]["turn"] == 3, payload["snapshot"]["state"]
print("① 턴마다 스냅샷 저장 OK")

# ── '재시작': 모듈을 다시 로드해 메모리 세션을 비우고 복구 경로를 태운다 ──
importlib.reload(server)
client2 = TestClient(server.app)
assert sid in server.SESSIONS, "재시작 후 세션 미복구"
state_after = client2.get(f"/api/sessions/{sid}/state").json()
assert state_after["turn"] == state_before["turn"], (state_after["turn"], state_before["turn"])
assert state_after["minute"] == state_before["minute"]
assert state_after["phase"] == state_before["phase"]
tr_after = client2.get(f"/api/sessions/{sid}/transcript").json()
assert len(tr_after) == len(tr_before), (len(tr_after), len(tr_before))
assert tr_after[-1]["content"] == tr_before[-1]["content"]
print(f"② 재시작 후 복구 OK (턴 {state_after['turn']}, 전사 {len(tr_after)}건)")

# ── 복구된 세션으로 수업 계속 진행 가능 ──
r = client2.post(f"/api/sessions/{sid}/turn", json={"input": "이어서 설명할게요"})
assert r.status_code == 200 and r.json()["turn"] == 4, r.text
print("③ 복구 세션에서 턴 계속 OK")

# ── 종료하면 스냅샷 정리 ──
r = client2.post(f"/api/sessions/{sid}/turn", json={"input": "/종료"})
assert r.status_code == 200 and r.json()["ended"]
assert not snap_file.exists(), "종료 후 스냅샷이 남아 있음"
print("④ 종료 시 스냅샷 정리 OK")

# ── 깨진 스냅샷은 건너뛰고 기동은 계속 ──
(Path(ROOT) / ".sessions").mkdir(exist_ok=True)
(Path(ROOT) / ".sessions" / "corrupt.json").write_text("{{{", encoding="utf-8")
importlib.reload(server)
assert "corrupt" not in server.SESSIONS
print("⑤ 깨진 스냅샷 무시 OK")

shutil.rmtree(Path(ROOT) / ".sessions", ignore_errors=True)
shutil.rmtree(Path(ROOT) / "reports" / "stage", ignore_errors=True)
print("CYCLE11 ALL PASS")
