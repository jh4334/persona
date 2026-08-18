from _common import ROOT
"""Cycle 26 verification: service_role 키 없이 운영 (RLS 모드 + 지연 복구).

목표는 "서버가 털려도 남의 데이터를 꺼낼 수 있는 키가 없다"이다. anon 키만 두고
요청마다 그 사용자의 JWT로 Supabase에 접근하며, 기동 시 전체 세션을 긁어오지
않는다(그러려면 RLS 우회 키가 필요하므로).
"""
import base64, hashlib, hmac, importlib, json, os, shutil, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)

SECRET = "test-secret-0123456789"
ANON = "anon-public-key"


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def tok(sub):
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = b64(json.dumps({"sub": sub, "aud": "authenticated",
                        "exp": int(time.time() + 3600), "email": sub + "@s.kr"}).encode())
    return f"{h}.{p}.{b64(hmac.new(SECRET.encode(), f'{h}.{p}'.encode(), hashlib.sha256).digest())}"


# ---------------------------------------------------------------------------
# RLS를 흉내내는 가짜 PostgREST — Authorization의 JWT에서 sub를 꺼내 행을 거른다
# ---------------------------------------------------------------------------

TABLES: dict[str, list[dict]] = {"stage_sessions": [], "classrooms": [], "reports": []}
SEEN_KEYS: set[str] = set()          # 어떤 키로 인증했는지 (service_role 유출 감시)


def sub_of(auth: str) -> str | None:
    """RLS의 auth.uid() 흉내 — 토큰이 유효해야 행이 보인다."""
    t = (auth or "").replace("Bearer ", "")
    parts = t.split(".")
    if len(parts) != 3:
        return None
    h, p, sig = parts
    expect = b64(hmac.new(SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    if sig != expect:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))["sub"]
    except Exception:
        return None


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

    def _uid(self):
        SEEN_KEYS.add(self.headers.get("apikey") or "")
        return sub_of(self.headers.get("Authorization") or "")

    def do_GET(self):
        uid = self._uid()
        if uid is None:
            return self._send(200, [])          # RLS: 인증 없으면 아무 행도 안 보인다
        q = parse_qs(urlparse(self.path).query)
        rows = [r for r in TABLES[self._tbl()] if r.get("user_id") == uid]
        if "id" in q:
            rid = q["id"][0].split(".", 1)[1]
            rows = [r for r in rows if str(r.get("id")) == rid]
        self._send(200, rows)

    def do_POST(self):
        uid = self._uid()
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n))
        if uid is None or body.get("user_id") != uid:
            return self._send(403, {"message": "RLS 위반"})   # with check (user_id = auth.uid())
        t = TABLES[self._tbl()]
        for i, r in enumerate(t):
            if str(r.get("id")) == str(body.get("id")):
                t[i] = body
                return self._send(201)
        t.append(body)
        self._send(201)

    def do_DELETE(self):
        uid = self._uid()
        q = parse_qs(urlparse(self.path).query)
        rid = q["id"][0].split(".", 1)[1]
        t = TABLES[self._tbl()]
        hit = [r for r in t if str(r.get("id")) == rid and r.get("user_id") == uid]
        for r in hit:
            t.remove(r)
        self._send(200, hit)


pg = ThreadingHTTPServer(("127.0.0.1", 0), PG)
threading.Thread(target=pg.serve_forever, daemon=True).start()
PG_URL = f"http://127.0.0.1:{pg.server_address[1]}"

# ---------------------------------------------------------------------------
# ① service_role 없이 구성된다
# ---------------------------------------------------------------------------
for k in ("SUPABASE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_TABLE"):
    os.environ.pop(k, None)
os.environ.update({"SUPABASE_URL": PG_URL, "SUPABASE_ANON_KEY": ANON,
                   "SUPABASE_JWT_SECRET": SECRET, "AUTH_REQUIRED": "1"})

from classroom_sim.web import store as S
importlib.reload(S)
r = S.remote_config()
assert r is not None and r.rls_mode and r.needs_token, r
assert r.describe() == "RLS(사용자 토큰)"
assert r.headers("jwt-abc")["Authorization"] == "Bearer jwt-abc", "사용자 토큰을 안 씀"
assert r.headers("jwt-abc")["apikey"] == ANON
assert r.headers(None)["Authorization"] == f"Bearer {ANON}", "토큰 없으면 anon으로"
# service_role이 함께 있으면? — 더 안전한 RLS 모드가 이긴다
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "srv"
r2 = S.remote_config()
assert r2.rls_mode and not r2.needs_token, "두 키가 다 있을 때 모드 판단이 이상함"
assert r2.headers("jwt-abc")["Authorization"] == "Bearer jwt-abc", "토큰이 있는데 service 키를 씀"
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY")
print("① RLS 모드 구성·헤더 선택 OK")

# ---------------------------------------------------------------------------
# ② 서버 전체가 service_role 없이 동작한다
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient
from classroom_sim.web import server
importlib.reload(server)
assert server.remote_config().needs_token
c = TestClient(server.app)
assert c.get("/healthz").json()["remote_auth"] == "RLS(사용자 토큰)"

HA = {"Authorization": f"Bearer {tok('teacherA')}"}
HB = {"Authorization": f"Bearer {tok('teacherB')}"}
CLS = json.dumps({"class_name": "5학년 2반", "students": [
    {"id": "S01", "name": "김하늘"}, {"id": "S02", "name": "박서준"}]}, ensure_ascii=False)

cid = c.post("/api/classrooms", json={"json_text": CLS}, headers=HA).json()["id"]
assert TABLES["classrooms"][0]["user_id"] == "teacherA"
sid = c.post("/api/sessions", json={"classroom_id": cid,
                                    "lesson_path": "lessons/ratio_and_rate.md",
                                    "backend": "mock"}, headers=HA).json()["session_id"]
c.post(f"/api/sessions/{sid}/turn", json={"input": "비를 배워 봅시다"}, headers=HA)
assert any(r["id"] == sid for r in TABLES["stage_sessions"]), "원격에 스냅샷 없음"
assert TABLES["stage_sessions"][0]["user_id"] == "teacherA"
assert SEEN_KEYS == {ANON}, f"anon 아닌 키가 쓰임: {SEEN_KEYS}"
print("② service_role 없이 학급·세션·스냅샷 저장 OK (쓰인 apikey: anon 뿐)")

# ---------------------------------------------------------------------------
# ③ 기동 시 원격을 통째로 긁어오지 않는다 (지연 복구)
# ---------------------------------------------------------------------------
remote_turn = [r for r in TABLES["stage_sessions"] if r["id"] == sid][0]["payload"]["snapshot"]["state"]["turn"]
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)     # 다른 서버로 옮긴 상황
importlib.reload(server)
assert sid not in server.SESSIONS, "기동 시 원격을 훑음 (service_role이 필요해진다)"
c2 = TestClient(server.app)
print("③ 기동 시 원격 미조회 OK")

# 주인이 요청하면 자기 토큰으로 되살아난다
r = c2.post(f"/api/sessions/{sid}/turn", json={"input": "이어서 해봅시다"}, headers=HA)
assert r.status_code == 200, r.text
assert r.json()["turn"] == remote_turn + 1, r.json()
assert sid in server.SESSIONS
print("④ 주인 요청 시 지연 복구 OK (turn %d→%d)" % (remote_turn, remote_turn + 1))

# ---------------------------------------------------------------------------
# ⑤ 남은 RLS가 남의 세션 복구를 막는다
# ---------------------------------------------------------------------------
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)
importlib.reload(server)
c3 = TestClient(server.app)
assert c3.get(f"/api/sessions/{sid}/state", headers=HB).status_code == 404, "남이 남의 수업을 되살림"
assert sid not in server.SESSIONS, "남의 요청으로 세션이 메모리에 올라옴"
assert c3.get(f"/api/sessions/{sid}/state", headers=HA).status_code == 200, "주인은 되살려야 한다"
print("⑤ 남의 세션은 지연 복구되지 않음 (RLS가 막음) OK")

# 토큰이 없으면 원격에서 아무것도 못 본다
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)
importlib.reload(server)
assert TestClient(server.app).get(f"/api/sessions/{sid}/state").status_code == 401
print("⑥ 토큰 없는 요청 차단 OK")

# ---------------------------------------------------------------------------
# ⑦ 학급·기록도 사용자 토큰으로만 오간다
# ---------------------------------------------------------------------------
c4 = TestClient(server.app)
assert [x["id"] for x in c4.get("/api/classrooms", headers=HA).json() if x["mine"]] == [cid]
assert [x for x in c4.get("/api/classrooms", headers=HB).json() if x["mine"]] == []
c4.post(f"/api/sessions/{sid}/turn", json={"input": "/종료"}, headers=HA)
assert TABLES["reports"] and TABLES["reports"][0]["user_id"] == "teacherA"
assert len(c4.get("/api/reports", headers=HA).json()) == 1
assert c4.get("/api/reports", headers=HB).json() == [], "남의 기록이 보임"
assert SEEN_KEYS == {ANON}, f"끝까지 anon만 쓰여야 한다: {SEEN_KEYS}"
print("⑦ 학급·기록도 사용자 토큰 경유 OK")

# ---------------------------------------------------------------------------
# ⑧ service 모드(로그인 없이 혼자 쓰기)는 그대로 동작한다
# ---------------------------------------------------------------------------
os.environ.pop("SUPABASE_ANON_KEY")
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "srv-key"
os.environ["AUTH_REQUIRED"] = "0"
importlib.reload(S)
r3 = S.remote_config()
assert not r3.rls_mode and not r3.needs_token and r3.describe() == "service_role"
assert r3.headers(None)["Authorization"] == "Bearer srv-key"
assert r3.headers("무시할토큰")["Authorization"] == "Bearer srv-key", "service 모드에서 토큰을 씀"
print("⑧ service 모드 회귀 OK")

pg.shutdown()
for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET",
          "SUPABASE_SERVICE_ROLE_KEY", "AUTH_REQUIRED"):
    os.environ.pop(k, None)
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)
print("CYCLE26 ALL PASS")
