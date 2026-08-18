from _common import ROOT
"""Cycle 21 verification: 세션 스냅샷 저장소 추상화 (디스크 ↔ Supabase 이중 기록).

Supabase에 실제로 붙지 않고, PostgREST 호출 규약을 그대로 흉내내는 가짜 서버를
127.0.0.1에 띄워 검증한다. 네트워크 정책·키 없이도 회귀로 돌릴 수 있다.
"""
import json, os, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)

from classroom_sim.web.store import DiskStore, MirrorStore, SupabaseStore, make_store, supabase_config
from pathlib import Path

# ---------------------------------------------------------------------------
# 가짜 PostgREST
# ---------------------------------------------------------------------------

ROWS: dict[str, dict] = {}
CALLS: list[tuple[str, str, dict]] = []   # (method, path+query, headers)
FAIL_NEXT = {"n": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 조용히
        pass

    def _record(self):
        CALLS.append((self.command, self.path, dict(self.headers)))

    def _fail_if_asked(self) -> bool:
        if FAIL_NEXT["n"] > 0:
            FAIL_NEXT["n"] -= 1
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"message":"boom"}')
            return True
        return False

    def do_POST(self):
        self._record()
        if self._fail_if_asked():
            return
        assert self.headers.get("apikey") == "test-key", "apikey 헤더 누락"
        assert self.headers.get("Authorization") == "Bearer test-key", "Authorization 누락"
        assert "merge-duplicates" in (self.headers.get("Prefer") or ""), "upsert Prefer 누락"
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ROWS[body["id"]] = body          # 같은 id면 덮어씀 = upsert
        self.send_response(201)
        self.end_headers()

    def do_GET(self):
        self._record()
        if self._fail_if_asked():
            return
        q = parse_qs(urlparse(self.path).query)
        gt = float(q["saved_at"][0].split(".", 1)[1])
        limit = int(q["limit"][0])
        rows = [r for r in ROWS.values() if r["saved_at"] > gt]
        rows.sort(key=lambda r: r["saved_at"], reverse=True)
        out = [{"id": r["id"], "payload": r["payload"]} for r in rows[:limit]]
        blob = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_DELETE(self):
        self._record()
        if self._fail_if_asked():
            return
        q = parse_qs(urlparse(self.path).query)
        ROWS.pop(q["id"][0].split(".", 1)[1], None)
        self.send_response(204)
        self.end_headers()


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"


def snap(saved_at: float, turn: int = 1, ended: bool = False) -> dict:
    return {
        "meta": {"classroom_path": "personas/class_6_3.json",
                 "lesson_path": "lessons/ratio_and_rate.md",
                 "backend": "mock", "class_name": "6학년 3반"},
        "saved_at": saved_at,
        "snapshot": {"state": {"turn": turn, "ended": ended}},
    }


now = time.time()

# ---------------------------------------------------------------------------
# ① SupabaseStore: upsert / select / delete 규약
# ---------------------------------------------------------------------------
sb = SupabaseStore(BASE, "test-key", "stage_sessions")
sb.save("aaa", snap(now, turn=1))
sb.save("aaa", snap(now + 1, turn=2))          # 같은 id → 행이 늘지 않아야
sb.save("bbb", snap(now + 2, turn=9))
assert len(ROWS) == 2, f"upsert가 아니라 행이 쌓임: {list(ROWS)}"
assert ROWS["aaa"]["payload"]["snapshot"]["state"]["turn"] == 2
assert ROWS["aaa"]["class_name"] == "6학년 3반", "표시용 class_name 누락"
assert CALLS[0][1].endswith("/rest/v1/stage_sessions"), CALLS[0][1]
print("① upsert 규약(헤더·경로·중복 갱신) OK")

rows = sb.load_all(newer_than=now - 10, limit=100)
assert [sid for sid, _ in rows] == ["bbb", "aaa"], rows       # 최신순
assert rows[0][1]["snapshot"]["state"]["turn"] == 9
assert sb.load_all(newer_than=now + 1.5) == [("bbb", ROWS["bbb"]["payload"])], "TTL 필터 미적용"
print("② select 최신순·TTL 필터 OK")

sb.delete("aaa")
assert list(ROWS) == ["bbb"], ROWS
print("③ delete OK")

# ---------------------------------------------------------------------------
# ④ MirrorStore: 양쪽에 쓰고, 한쪽이 죽어도 계속된다
# ---------------------------------------------------------------------------
ROWS.clear(); CALLS.clear()
tmpdir = Path(ROOT) / ".sessions_test21"
shutil.rmtree(tmpdir, ignore_errors=True)
disk = DiskStore(tmpdir)
mirror = MirrorStore([disk, SupabaseStore(BASE, "test-key")])

mirror.save("s1", snap(now, turn=3))
assert (tmpdir / "s1.json").is_file(), "디스크에 안 씀"
assert "s1" in ROWS, "Supabase에 안 씀"
print("④ 이중 기록 OK")

FAIL_NEXT["n"] = 1                        # Supabase 한 번 실패
mirror.save("s2", snap(now + 1, turn=4))  # 예외가 밖으로 새면 안 된다
assert (tmpdir / "s2.json").is_file(), "원격 실패가 디스크 기록까지 막음"
assert "s2" not in ROWS
print("⑤ 원격 실패해도 디스크 기록 계속·예외 미전파 OK")

# ---------------------------------------------------------------------------
# ⑥ 병합 시 더 최근 스냅샷이 이긴다
# ---------------------------------------------------------------------------
disk.save("s3", snap(now + 5, turn=10))                      # 디스크가 구버전
SupabaseStore(BASE, "test-key").save("s3", snap(now + 9, turn=42))   # 원격이 최신
merged = dict(mirror.load_all(newer_than=now - 100))
assert merged["s3"]["snapshot"]["state"]["turn"] == 42, merged["s3"]
disk.save("s4", snap(now + 9, turn=77))
SupabaseStore(BASE, "test-key").save("s4", snap(now + 5, turn=1))    # 원격이 구버전
merged = dict(mirror.load_all(newer_than=now - 100))
assert merged["s4"]["snapshot"]["state"]["turn"] == 77, merged["s4"]
print("⑥ 병합 시 최신 스냅샷 우선 OK")

FAIL_NEXT["n"] = 1
merged = dict(mirror.load_all(newer_than=now - 100))
assert "s1" in merged, "원격 조회 실패 시 디스크 결과까지 잃음"
print("⑦ 원격 조회 실패해도 디스크로 복구 OK")

# ---------------------------------------------------------------------------
# ⑧ 환경변수 구성
# ---------------------------------------------------------------------------
for k in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY",
          "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_TABLE"):
    os.environ.pop(k, None)
assert supabase_config() is None
assert make_store(tmpdir).name == "disk", "미설정인데 원격을 붙임"

os.environ["SUPABASE_URL"] = BASE
assert supabase_config() is None, "키 없이 URL만으로 구성되면 안 됨"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-key"
assert supabase_config() == (BASE, "test-key", "stage_sessions")
assert make_store(tmpdir).name == "disk+supabase"

os.environ["SUPABASE_URL"] = "obmlsijdaknzwktplklr.supabase.co"    # 스킴 빠짐
assert supabase_config() is None, "잘못된 URL을 걸러내지 못함"
print("⑧ 환경변수 구성·오설정 방어 OK")

# ---------------------------------------------------------------------------
# ⑨ 서버 전체 경로: SUPABASE_* 설정 상태에서 세션 생성·턴·복구
# ---------------------------------------------------------------------------
os.environ["SUPABASE_URL"] = BASE
os.environ["SUPABASE_TABLE"] = "stage_sessions"
ROWS.clear()
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)

from fastapi.testclient import TestClient
import importlib
from classroom_sim.web import server
importlib.reload(server)
assert server.STORE.name == "disk+supabase", server.STORE.name

client = TestClient(server.app)
assert client.get("/healthz").json()["store"] == "disk+supabase"
sid = client.post("/api/sessions", json={
    "classroom_path": "personas/class_6_3.json",
    "lesson_path": "lessons/ratio_and_rate.md",
    "backend": "mock"}).json()["session_id"]
client.post(f"/api/sessions/{sid}/turn", json={"input": "비는 두 수의 비교예요"})
assert sid in ROWS, "턴 후 원격 스냅샷 없음"
remote_turn = ROWS[sid]["payload"]["snapshot"]["state"]["turn"]
assert remote_turn >= 1, ROWS[sid]

# 디스크만 날리고 재시작 → 원격 스냅샷만으로 되살아나야 한다 (다른 서버로 옮긴 상황)
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)
importlib.reload(server)
assert sid in server.SESSIONS, "원격 스냅샷으로 복구하지 못함"
assert server.SESSIONS[sid].session.state.turn == remote_turn
client2 = TestClient(server.app)
r = client2.post(f"/api/sessions/{sid}/turn", json={"input": "이어서 해봅시다"})
assert r.status_code == 200, r.text
assert r.json()["turn"] == remote_turn + 1, r.json()
print("⑨ 디스크 없이 원격 스냅샷만으로 서버 이전 복구 OK (turn %d→%d)"
      % (remote_turn, remote_turn + 1))

# ⑩ 종료하면 원격 스냅샷도 지워진다
client2.post(f"/api/sessions/{sid}/turn", json={"input": "/종료"})
assert sid not in ROWS, "종료 후 원격 스냅샷이 남음"
print("⑩ 종료 시 원격 정리 OK")

srv.shutdown()
shutil.rmtree(tmpdir, ignore_errors=True)
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)
shutil.rmtree("reports/stage", ignore_errors=True)
print("CYCLE21 ALL PASS")
