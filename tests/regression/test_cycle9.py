from _common import ROOT, CHROMIUM
"""Cycle 9 verification: /healthz + structured logs."""
import logging, sys, os, io
sys.path.insert(0, f"{ROOT}/src")
os.chdir(f"{ROOT}")

from fastapi.testclient import TestClient
from classroom_sim.web import server

buf = io.StringIO()
h = logging.StreamHandler(buf)
h.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
logging.getLogger("classroom_sim.web").addHandler(h)
logging.getLogger("classroom_sim.web").setLevel(logging.INFO)

client = TestClient(server.app)

# ① /healthz
r = client.get("/healthz")
assert r.status_code == 200, r.text
j = r.json()
assert j["status"] == "ok" and j["sessions"] == 0 and "uptime_s" in j, j
print("① /healthz OK:", j)

# ② 세션 생성·턴·종료가 로그로 남는지
r = client.post("/api/sessions", json={
    "classroom_path": "personas/class_6_3.json",
    "lesson_path": "lessons/ratio_and_rate.md",
    "backend": "mock",
})
sid = r.json()["session_id"]
client.post(f"/api/sessions/{sid}/turn", json={"input": "안녕하세요"})
client.post(f"/api/sessions/{sid}/turn", json={"input": "/종료"})

logs = buf.getvalue()
assert "session created" in logs, logs
assert "turn ok" in logs and "took=" in logs, logs
assert "report saved" in logs, logs
print("② 생성/턴(처리시간)/리포트 저장 로그 OK")

# ③ healthz 세션 수 반영
j = client.get("/healthz").json()
assert j["sessions"] == 1, j
print("③ healthz 세션 수 OK")

# ④ 턴 실패도 스택과 함께 로그 (없는 세션은 404라 로그 대상 아님 → 강제 예외)
rec = server.SESSIONS[sid]
orig = rec.session.turn
rec.session.turn = lambda t: (_ for _ in ()).throw(RuntimeError("boom"))
r = client.post(f"/api/sessions/{sid}/turn", json={"input": "x"})
rec.session.turn = orig
assert r.status_code == 500
assert "turn failed" in buf.getvalue() and "boom" in buf.getvalue()
print("④ 턴 실패 로그(스택 포함) OK")

import shutil
shutil.rmtree("reports/stage", ignore_errors=True)
print("CYCLE9 ALL PASS")
