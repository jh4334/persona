from _common import ROOT
"""Cycle 28 verification: 서버리스(Vercel) 모드.

서버리스는 요청마다 다른 인스턴스일 수 있고 로컬 디스크가 남지 않는다.
디스크에 써 놓고 "저장됐다"고 믿는 것이 가장 나쁜 실패이므로, 이 모드에서는
디스크를 아예 쓰지 않고 원격만 쓴다. 저장이 실패하면 교사에게 알린다.
"""
import importlib, json, os, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)

ENV_KEYS = ("VERCEL", "CLASSROOM_SIM_STATELESS", "AWS_LAMBDA_FUNCTION_NAME",
            "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_JWT_SECRET", "AUTH_REQUIRED", "SUPABASE_TABLE")
for k in ENV_KEYS:
    os.environ.pop(k, None)

from classroom_sim.web import store as S

# ---------------------------------------------------------------------------
# ① 서버리스 감지
# ---------------------------------------------------------------------------
assert S.stateless() is False
for var, val in [("VERCEL", "1"), ("AWS_LAMBDA_FUNCTION_NAME", "fn"),
                 ("CLASSROOM_SIM_STATELESS", "1"), ("CLASSROOM_SIM_STATELESS", "true")]:
    os.environ[var] = val
    importlib.reload(S)
    assert S.stateless() is True, var
    os.environ.pop(var)
os.environ["CLASSROOM_SIM_STATELESS"] = "0"
importlib.reload(S)
assert S.stateless() is False, "0으로 끌 수 없음"
os.environ.pop("CLASSROOM_SIM_STATELESS")
importlib.reload(S)
print("① 서버리스 감지(VERCEL·LAMBDA·명시 설정·끄기) OK")

# ---------------------------------------------------------------------------
# ② 서버리스면 디스크 저장소를 붙이지 않는다
# ---------------------------------------------------------------------------
tmp = Path(ROOT) / ".sessions_test28"
shutil.rmtree(tmp, ignore_errors=True)
assert S.make_store(tmp).name == "disk", "일반 모드인데 디스크가 없음"

os.environ["VERCEL"] = "1"
importlib.reload(S)
st = S.make_store(tmp)
assert st.name == "none", f"서버리스인데 저장소가 {st.name} (Supabase 미설정이면 아무 데도 안 써야)"
st.save("x", {"saved_at": time.time()})          # 조용히 무시되어야 (예외 없음)
assert st.load_one("x") is None and st.load_all() == []
assert not tmp.exists(), "서버리스인데 디스크에 씀"
print("② 서버리스 + Supabase 없음 → 디스크에 쓰지 않음 OK")

# ---------------------------------------------------------------------------
# ③ 가짜 PostgREST 를 붙이면 원격 전용이 된다
# ---------------------------------------------------------------------------
TABLES: dict[str, list[dict]] = {"stage_sessions": [], "classrooms": [], "reports": []}
FAIL = {"n": 0}


class PG(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _tbl(self):
        return urlparse(self.path).path.rsplit("/", 1)[-1]

    def _send(self, code, obj=None):
        blob = json.dumps(obj if obj is not None else []).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _boom(self):
        if FAIL["n"] > 0:
            FAIL["n"] -= 1
            self._send(500, {"message": "boom"})
            return True
        return False

    def do_GET(self):
        if self._boom():
            return
        q = parse_qs(urlparse(self.path).query)
        rows = list(TABLES[self._tbl()])
        if "id" in q:
            rid = q["id"][0].split(".", 1)[1]
            rows = [r for r in rows if str(r.get("id")) == rid]
        self._send(200, rows)

    def do_POST(self):
        if self._boom():
            return
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n))
        t = TABLES[self._tbl()]
        for i, r in enumerate(t):
            if str(r.get("id")) == str(body.get("id")):
                t[i] = body
                return self._send(201)
        t.append(body)
        self._send(201)

    def do_DELETE(self):
        if self._boom():
            return
        q = parse_qs(urlparse(self.path).query)
        rid = q["id"][0].split(".", 1)[1]
        t = TABLES[self._tbl()]
        hit = [r for r in t if str(r.get("id")) == rid]
        for r in hit:
            t.remove(r)
        self._send(200, hit)


pg = ThreadingHTTPServer(("127.0.0.1", 0), PG)
threading.Thread(target=pg.serve_forever, daemon=True).start()
PG_URL = f"http://127.0.0.1:{pg.server_address[1]}"

os.environ["SUPABASE_URL"] = PG_URL
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "srv"
importlib.reload(S)
st = S.make_store(tmp)
assert st.name == "supabase", st.name          # mirror가 아니라 원격 단독
st.save("s1", {"meta": {}, "saved_at": time.time(), "snapshot": {"state": {"turn": 1}}})
assert len(TABLES["stage_sessions"]) == 1
assert not tmp.exists(), "서버리스인데 디스크에 씀"
print("③ 서버리스 + Supabase → 원격 단독(mirror 아님) OK")

# ---------------------------------------------------------------------------
# ④ 서버 전체: 디스크 산출물이 하나도 생기지 않는다
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient
from classroom_sim.web import server
importlib.reload(server)
c = TestClient(server.app)

h = c.get("/healthz").json()
assert h["mode"] == "serverless", h
assert h["store"] == "supabase", h
assert "codex" not in h["backends"], h["backends"]      # 하위 프로세스를 못 띄운다
print("④ /healthz mode·store·backends OK:", h["mode"], h["store"], h["backends"])

r = c.post("/api/sessions", json={"classroom_id": "sample:class_6_3",
                                  "lesson_path": "lessons/ratio_and_rate.md",
                                  "backend": "codex"})
assert r.status_code == 400 and "지원하지 않는" in r.json()["detail"], r.text
print("⑤ 서버리스에서 codex 백엔드 거부 OK")

sid = c.post("/api/sessions", json={"classroom_id": "sample:class_6_3",
                                    "lesson_path": "lessons/ratio_and_rate.md",
                                    "backend": "mock"}).json()["session_id"]
turn = c.post(f"/api/sessions/{sid}/turn", json={"input": "비를 배워 봅시다"}).json()
assert "notice" not in turn, turn.get("notice")
assert any(r["id"] == sid for r in TABLES["stage_sessions"]), "원격에 스냅샷 없음"
assert not Path(f"{ROOT}/.sessions").exists(), "서버리스인데 .sessions/ 가 생김"

cls = c.post("/api/classrooms", json={"json_text": json.dumps(
    {"class_name": "5학년 2반", "students": [{"id": "S1", "name": "김하늘"}]}, ensure_ascii=False)})
assert cls.status_code == 201, cls.text
assert TABLES["classrooms"], "학급이 원격에 없음"
assert not Path(f"{ROOT}/.classrooms").exists(), "서버리스인데 .classrooms/ 가 생김"

c.post(f"/api/sessions/{sid}/turn", json={"input": "/종료"})
assert TABLES["reports"], "리포트가 원격에 없음"
assert not Path(f"{ROOT}/reports/stage").exists(), "서버리스인데 reports/stage/ 가 생김"
print("⑥ 디스크 산출물 0건 — 스냅샷·학급·리포트 모두 원격 OK")

# ---------------------------------------------------------------------------
# ⑦ 인스턴스가 바뀌어도 이어진다 (지연 복구)
# ---------------------------------------------------------------------------
sid2 = c.post("/api/sessions", json={"classroom_id": "sample:class_6_3",
                                     "lesson_path": "lessons/ratio_and_rate.md",
                                     "backend": "mock"}).json()["session_id"]
c.post(f"/api/sessions/{sid2}/turn", json={"input": "비란 두 수의 비교예요"})
row = [r for r in TABLES["stage_sessions"] if r["id"] == sid2][0]
before = row["payload"]["snapshot"]["state"]["turn"]

importlib.reload(server)          # 새 인스턴스 (메모리 비어 있음)
assert sid2 not in server.SESSIONS, "기동 시 원격을 훑음"
c2 = TestClient(server.app)
r = c2.post(f"/api/sessions/{sid2}/turn", json={"input": "이어서 해봅시다"})
assert r.status_code == 200, r.text
assert r.json()["turn"] == before + 1, r.json()
print("⑦ 인스턴스 교체 후 지연 복구로 이어짐 OK (turn %d→%d)" % (before, before + 1))

def mcp_tool(client, name, arguments):
    response = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["isError"] is False, result
    return result["structuredContent"]


mcp_started = mcp_tool(c2, "start_session", {
    "classroom_id": "sample:class_6_3", "lesson_text": "분수 비교 수업",
})
mcp_sid = mcp_started["session_id"]
assert mcp_sid.startswith("mcp_")
assert any(r["id"] == mcp_sid for r in TABLES["stage_sessions"])

importlib.reload(server)
c_mcp = TestClient(server.app)
mcp_turn = mcp_tool(c_mcp, "record_turn", {
    "session_id": mcp_sid,
    "teacher_input": "분수를 비교해 봅시다.",
    "minute": 5,
    "phase": "전개",
    "state_updates": {"S01": {"comprehension": 70}},
    "events": [{"student_id": "S01", "utterance": "분모부터 볼게요."}],
})
assert mcp_turn["turn"] == 1, mcp_turn

importlib.reload(server)
c_mcp2 = TestClient(server.app)
mcp_state = mcp_tool(c_mcp2, "get_state", {"session_id": mcp_sid})
assert mcp_state["turn"] == 1 and mcp_state["minute"] == 5, mcp_state
print("⑦-B MCP도 인스턴스 3개를 건너 원격 복구됨 OK")

# ---------------------------------------------------------------------------
# ⑧ 저장이 실패하면 교사에게 알린다 (서버리스에서는 곧 유실이므로)
# ---------------------------------------------------------------------------
c2 = TestClient(server.app)
assert c2.get(f"/api/sessions/{sid2}/state").status_code == 200
FAIL["n"] = 1
r = c2.post(f"/api/sessions/{sid2}/turn", json={"input": "저장이 실패하는 턴"}).json()
assert "notice" in r and "저장하지 못했습니다" in r["notice"], r.get("notice")
assert "전사 내려받기" in r["notice"], r["notice"]
print("⑧ 저장 실패 시 안내 OK:", r["notice"][:45] + "…")

# 일반 서버 모드에서는 조용히 넘어간다 (디스크 사본이 남으므로)
os.environ.pop("VERCEL")
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)
importlib.reload(server)
c3 = TestClient(server.app)
assert c3.get("/healthz").json()["mode"] == "server"
sid3 = c3.post("/api/sessions", json={"classroom_id": "sample:class_6_3",
                                      "lesson_path": "lessons/ratio_and_rate.md",
                                      "backend": "mock"}).json()["session_id"]
FAIL["n"] = 1
r = c3.post(f"/api/sessions/{sid3}/turn", json={"input": "x"}).json()
assert "notice" not in r, "일반 서버인데 저장 실패를 알림 (디스크에 남았는데)"
assert Path(f"{ROOT}/.sessions/{sid3}.json").is_file(), "일반 서버인데 디스크 사본이 없음"
print("⑨ 일반 서버 모드 회귀 — 저장 실패해도 디스크 사본으로 계속 OK")

# ---------------------------------------------------------------------------
# ⑩ 배포 산출물
# ---------------------------------------------------------------------------
root = Path(ROOT)
for f in ("vercel.json", "app.py", "Dockerfile", ".dockerignore",
          ".vercelignore", ".github/workflows/ci.yml", "requirements.txt"):
    assert (root / f).is_file(), f"{f} 없음"

# Vercel 네이티브 FastAPI 라우팅 — 루트의 app.py 하나가 전 경로를 받는다.
# rewrite를 두지 않으므로, 진입점이 vercel.json이 가리키는 파일과 같아야 한다.
vj = json.loads((root / "vercel.json").read_text(encoding="utf-8"))
assert list(vj["functions"]) == ["app.py"], vj["functions"]
assert vj["functions"]["app.py"]["maxDuration"] >= 60, vj
assert not (root / "api").exists(), "옛 진입점 api/ 가 남아 있음 (vercel.json이 안 가리킴)"

idx = (root / "app.py").read_text(encoding="utf-8")
assert "from classroom_sim.web.server import app" in idx
assert 'sys.path.insert(0, str(ROOT / "src"))' in idx

dk = (root / "Dockerfile").read_text(encoding="utf-8")
assert "USER app" in dk, "컨테이너를 루트로 돌림"
assert "HEALTHCHECK" in dk
assert "COPY personas/" in dk and "COPY lessons/" in dk, "샘플 데이터 미포함"

di = (root / ".dockerignore").read_text(encoding="utf-8")
assert ".env" in di, ".env 가 이미지에 들어갈 수 있음"
print("⑩ 배포 산출물(vercel.json·api/index.py·Dockerfile·CI) OK")

pg.shutdown()
for k in ENV_KEYS:
    os.environ.pop(k, None)
shutil.rmtree(tmp, ignore_errors=True)
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)
print("CYCLE28 ALL PASS")
