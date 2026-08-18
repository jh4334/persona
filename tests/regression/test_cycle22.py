from _common import ROOT, CHROMIUM
"""Cycle 22 verification: Supabase Auth 로그인 게이트 + 세션 소유권.

실제 Supabase에 붙지 않는다. `/auth/v1/*` 규약을 흉내내는 가짜 서버를
127.0.0.1에 띄우고, HS256 토큰은 표준 라이브러리로 직접 만든다.
"""
import base64, hashlib, hmac, json, os, shutil, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)

SECRET = "test-jwt-secret-0123456789"
ANON = "test-anon-key"

# ---------------------------------------------------------------------------
# 토큰 만들기
# ---------------------------------------------------------------------------


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_token(sub="user-1", email="a@b.kr", exp_in=3600, secret=SECRET, alg="HS256", aud="authenticated"):
    header = b64(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    claims = {"sub": sub, "email": email, "aud": aud, "exp": int(time.time() + exp_in), "role": "authenticated"}
    payload = b64(json.dumps(claims).encode())
    signing = f"{header}.{payload}".encode()
    sig = b64(hmac.new(secret.encode(), signing, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


# ---------------------------------------------------------------------------
# 1부: 서버 측 검증 (브라우저 없이)
# ---------------------------------------------------------------------------

from classroom_sim.web import auth as A

cfg = A.AuthConfig(url="http://127.0.0.1:1", anon_key=ANON, jwt_secret=SECRET, required=True)
V = A.Verifier(cfg)

u = V.verify(make_token(sub="teacher-7", email="kim@school.kr"))
assert (u.id, u.email) == ("teacher-7", "kim@school.kr"), u
print("① HS256 로컬 검증 OK")

bad = [
    ("서명 위조", make_token(secret="wrong-secret")),
    ("만료", make_token(exp_in=-3600)),
    ("대상 불일치", make_token(aud="anon")),
    ("형식 오류", "not.a.jwt"),
    ("빈 토큰", ""),
]
for label, tok in bad:
    try:
        V.verify(tok)
    except A.AuthError:
        pass
    else:
        raise AssertionError(f"{label} 토큰이 통과됨")
# 페이로드만 바꿔치기 (서명은 원본 유지) — 서명 검증이 실제로 도는지 확인
h, p, s = make_token(sub="teacher-7").split(".")
forged = f"{h}.{b64(json.dumps({'sub': 'admin', 'aud': 'authenticated', 'exp': int(time.time()+3600)}).encode())}.{s}"
try:
    V.verify(forged)
except A.AuthError:
    pass
else:
    raise AssertionError("페이로드 변조 토큰이 통과됨")
print("② 위조·만료·형식오류·페이로드 변조 차단 OK (%d종)" % (len(bad) + 1))

assert A.bearer_token("Bearer abc") == "abc"
assert A.bearer_token("bearer abc") == "abc"
assert A.bearer_token("Basic abc") == ""
assert A.bearer_token(None) == ""
print("③ Authorization 헤더 파싱 OK")

# ---------------------------------------------------------------------------
# 2부: 가짜 Supabase Auth — 비대칭 서명(원격 확인 폴백)
# ---------------------------------------------------------------------------

SENT: list[dict] = []          # /otp 로 보낸 메일
REMOTE_CALLS = {"user": 0}


class AuthHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        blob = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(blob)

    def do_OPTIONS(self):
        self._json(200, {})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/auth/v1/user":
            REMOTE_CALLS["user"] += 1
            tok = (self.headers.get("Authorization") or "").replace("Bearer ", "")
            if tok.startswith("remote-good"):
                return self._json(200, {"id": "remote-user", "email": "remote@school.kr"})
            return self._json(401, {"msg": "invalid token"})
        self._json(404, {})

    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.headers.get("apikey") != ANON:
            return self._json(401, {"msg": "no apikey"})
        if path == "/auth/v1/otp":
            if body.get("email") == "blocked@school.kr":
                return self._json(429, {"error_description": "rate limit"})
            SENT.append(body)
            return self._json(200, {})
        if path == "/auth/v1/verify":
            if body.get("token") != "123456":
                return self._json(403, {"error_description": "invalid otp"})
            return self._json(200, {
                "access_token": make_token(sub="teacher-9", email=body.get("email", "")),
                "refresh_token": "refresh-abc", "expires_in": 3600})
        if path == "/auth/v1/token":
            if body.get("refresh_token") != "refresh-abc":
                return self._json(401, {"error_description": "bad refresh"})
            return self._json(200, {
                "access_token": make_token(sub="teacher-9", email="kim@school.kr"),
                "refresh_token": "refresh-abc", "expires_in": 3600})
        if path == "/auth/v1/logout":
            return self._json(204, {})
        self._json(404, {})


auth_srv = ThreadingHTTPServer(("127.0.0.1", 0), AuthHandler)
threading.Thread(target=auth_srv.serve_forever, daemon=True).start()
AUTH_URL = f"http://127.0.0.1:{auth_srv.server_address[1]}"

# 시크릿 없이 → 원격 확인으로 넘어가고, 결과는 캐시된다
remote_cfg = A.AuthConfig(url=AUTH_URL, anon_key=ANON, jwt_secret="", required=True)
RV = A.Verifier(remote_cfg)
tok_remote = make_token(sub="ignored", alg="ES256")   # 비대칭 → 로컬 검증 불가
import classroom_sim.web.auth as _a
_orig = _a.Verifier._verify_remote
_a.Verifier._verify_remote = lambda self, t: A.User(id="remote-user", email="remote@school.kr")
u = RV.verify(tok_remote)
assert u.id == "remote-user", u
_a.Verifier._verify_remote = lambda self, t: (_ for _ in ()).throw(AssertionError("캐시를 안 씀"))
assert RV.verify(tok_remote).id == "remote-user", "원격 확인 결과가 캐시되지 않음"
_a.Verifier._verify_remote = _orig
print("④ 비대칭 서명 → 원격 확인 폴백 + 캐시 OK")

# 만료 토큰은 원격에 묻지도 않는다 (불필요한 왕복 방지)
before = REMOTE_CALLS["user"]
try:
    RV.verify(make_token(exp_in=-3600, alg="ES256"))   # 시계 오차 허용(30초) 밖
except A.AuthError:
    pass
assert REMOTE_CALLS["user"] == before, "만료가 뻔한 토큰으로 원격을 호출함"
print("⑤ 만료 토큰은 원격 호출 없이 차단 OK")

# ---------------------------------------------------------------------------
# 3부: FastAPI 게이트 + 소유권
# ---------------------------------------------------------------------------

os.environ["SUPABASE_URL"] = AUTH_URL
os.environ["SUPABASE_ANON_KEY"] = ANON
os.environ["SUPABASE_JWT_SECRET"] = SECRET
os.environ["AUTH_REQUIRED"] = "1"

import importlib
from fastapi.testclient import TestClient
from classroom_sim.web import server
importlib.reload(server)
assert server.AUTH.required is True
client = TestClient(server.app)

assert client.get("/healthz").json()["auth"] == "required"
cfgj = client.get("/api/auth/config").json()
assert cfgj["required"] is True and cfgj["anon_key"] == ANON and cfgj["url"] == AUTH_URL
print("⑥ /healthz·/api/auth/config OK")

BODY = {"classroom_path": "personas/class_6_3.json",
        "lesson_path": "lessons/ratio_and_rate.md", "backend": "mock"}

# 토큰 없이 → 전부 401
for path, kw in [("/api/classrooms", {}), ("/api/lessons", {}), ("/api/sessions", {"json": BODY})]:
    m = client.post if "json" in kw else client.get
    r = m(path, **kw)
    assert r.status_code == 401, f"{path} 가 인증 없이 통과됨: {r.status_code}"
    assert r.headers.get("WWW-Authenticate") == "Bearer"
assert client.get("/api/auth/me").status_code == 401
print("⑦ 토큰 없으면 401 (학급 목록·수업 생성 포함) OK")

A_TOK = make_token(sub="teacher-A", email="a@school.kr")
B_TOK = make_token(sub="teacher-B", email="b@school.kr")
HA = {"Authorization": f"Bearer {A_TOK}"}
HB = {"Authorization": f"Bearer {B_TOK}"}

me = client.get("/api/auth/me", headers=HA).json()
assert me["authenticated"] and me["user_id"] == "teacher-A" and me["email"] == "a@school.kr", me
assert client.get("/api/classrooms", headers=HA).status_code == 200
r = client.post("/api/sessions", json=BODY, headers=HA)
assert r.status_code == 200, r.text
sid = r.json()["session_id"]
assert server.SESSIONS[sid].user_id == "teacher-A"
print("⑧ 로그인 후 수업 생성·소유자 기록 OK")

# B는 A의 수업에 접근할 수 없다 — 존재 여부까지 숨기려고 404
for path, kw in [(f"/api/sessions/{sid}/state", {}),
                 (f"/api/sessions/{sid}/transcript", {}),
                 (f"/api/sessions/{sid}/turn", {"json": {"input": "가로채기"}}),
                 (f"/api/sessions/{sid}/end", {"json": None})]:
    m = client.post if "json" in kw else client.get
    r = m(path, headers=HB, **({k: v for k, v in kw.items() if v is not None}))
    assert r.status_code == 404, f"{path} 를 남이 열람함: {r.status_code}"
print("⑨ 남의 수업 접근 차단(404로 은닉) OK")

r = client.post(f"/api/sessions/{sid}/turn", json={"input": "비는 두 수의 비교예요"}, headers=HA)
assert r.status_code == 200, r.text
assert client.get(f"/api/sessions/{sid}/state", headers=HA).status_code == 200
print("⑩ 주인은 정상 진행 OK")

# 만료 토큰으로는 진행 불가
old_tok = {"Authorization": f"Bearer {make_token(sub='teacher-A', exp_in=-3600)}"}
assert client.post(f"/api/sessions/{sid}/turn", json={"input": "x"}, headers=old_tok).status_code == 401
print("⑪ 만료 토큰 차단 OK")

# 스냅샷에 소유자가 남아, 재시작 후에도 소유권이 유지된다
snap = json.loads((server.SNAP_DIR / f"{sid}.json").read_text(encoding="utf-8"))
assert snap["meta"]["user_id"] == "teacher-A", snap["meta"]
importlib.reload(server)
assert server.SESSIONS[sid].user_id == "teacher-A", "재시작 후 소유자 유실"
c2 = TestClient(server.app)
assert c2.get(f"/api/sessions/{sid}/state", headers=HB).status_code == 404, "재시작 후 소유권 검사 누락"
assert c2.get(f"/api/sessions/{sid}/state", headers=HA).status_code == 200
print("⑫ 재시작 후에도 소유권 유지 OK")

# 생성 속도 제한이 IP가 아니라 사용자 기준으로 걸린다
importlib.reload(server)
c3 = TestClient(server.app)
codes = [c3.post("/api/sessions", json=BODY, headers=HA).status_code for _ in range(11)]
assert codes[-1] == 429, codes
assert c3.post("/api/sessions", json=BODY, headers=HB).status_code == 200, "다른 사용자까지 막힘"
print("⑬ 생성 속도 제한이 사용자별로 적용 OK")

# ---------------------------------------------------------------------------
# 4부: 인증을 끄면 기존 동작 그대로
# ---------------------------------------------------------------------------
os.environ["AUTH_REQUIRED"] = "0"
importlib.reload(server)
c4 = TestClient(server.app)
assert c4.get("/healthz").json()["auth"] == "open"
assert c4.get("/api/auth/config").json() == {"required": False, "url": "", "anon_key": ""}, "인증 꺼짐인데 키가 노출됨"
assert c4.get("/api/classrooms").status_code == 200
assert c4.post("/api/sessions", json=BODY).status_code == 200
print("⑭ AUTH_REQUIRED=0 이면 기존 동작·키 미노출 OK")

# ---------------------------------------------------------------------------
# 5부: 브라우저 — 로그인 게이트 전 과정
# ---------------------------------------------------------------------------
for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET", "AUTH_REQUIRED"):
    os.environ.pop(k, None)

PORT = 8771
proc = subprocess.Popen(
    [sys.executable, "-m", "classroom_sim.web", "--port", str(PORT)],
    cwd=ROOT,
    env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin:/usr/local/bin",
         "SUPABASE_URL": AUTH_URL, "SUPABASE_ANON_KEY": ANON,
         "SUPABASE_JWT_SECRET": SECRET, "AUTH_REQUIRED": "1"},
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        raise RuntimeError("서버 기동 실패")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(f"http://127.0.0.1:{PORT}/")
        page.wait_for_function("document.body.dataset.screen === 'login'")
        assert not page.is_visible("#screen-setup"), "로그인 전에 셋업 화면이 보임"
        print("⑮ 로그인 필요 시 셋업 화면 대신 로그인 화면 OK")

        # 잘못된 이메일은 보내기 전에 막는다
        page.fill("#login-email", "이메일아님")
        page.click("#btn-login-send")
        page.wait_for_selector("#login-note:not([hidden])")
        assert "이메일" in page.inner_text("#login-note")
        assert len(SENT) == 0, "형식이 틀린 주소로 메일을 보냄"

        # 메일 보내기 → 코드 단계 등장
        page.fill("#login-email", "kim@school.kr")
        page.click("#btn-login-send")
        page.wait_for_selector("#login-code-step:not([hidden])")
        assert SENT and SENT[-1]["email"] == "kim@school.kr", SENT
        assert "kim@school.kr" in page.inner_text("#login-note")
        print("⑯ 로그인 메일 요청 → 코드 입력 단계 OK")

        # 틀린 코드
        page.fill("#login-code", "000000")
        page.click("#btn-login-verify")
        page.wait_for_function(
            "document.querySelector('#login-note').textContent.includes('올바르지 않')")
        assert page.evaluate("document.body.dataset.screen") == "login", "틀린 코드로 통과됨"
        print("⑰ 틀린 코드 거부 OK")

        # 맞는 코드 → 로그인 → 셋업 화면
        page.fill("#login-code", "123456")
        page.click("#btn-login-verify")
        page.wait_for_function("document.body.dataset.screen === 'setup'", timeout=15000)
        assert page.is_visible("#account-row"), "계정 표시줄이 없음"
        assert "kim@school.kr" in page.inner_text("#account-email")
        print("⑱ 코드 로그인 성공 → 셋업 진입 + 계정 표시 OK")

        # 새로고침해도 로그인 유지 (토큰 보관)
        page.reload()
        page.wait_for_function("document.body.dataset.screen === 'setup'", timeout=15000)
        print("⑲ 새로고침 후 로그인 유지 OK")

        # 실제 수업 한 턴 — 인증 헤더가 모든 API에 실리는지
        page.wait_for_selector("#sel-classroom option", state="attached")
        page.click("#btn-start")
        page.wait_for_function("document.body.dataset.screen === 'stage'", timeout=20000)
        page.fill("#teacher-input", "비는 두 수의 비교예요")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')", timeout=20000)
        assert page.evaluate("App.turn") >= 1, "턴이 진행되지 않음"
        print("⑳ 로그인 상태에서 수업 생성·턴 진행 OK")

        # 토큰이 깨지면 로그인 화면으로 되돌아간다
        page.evaluate("""() => {
          const t = JSON.parse(localStorage.getItem('cs_auth'));
          t.access_token = 'broken.token.value'; t.refresh_token = '';
          localStorage.setItem('cs_auth', JSON.stringify(t));
        }""")
        page.reload()
        page.wait_for_function("document.body.dataset.screen === 'login'", timeout=15000)
        print("㉑ 토큰 무효화 시 로그인 화면 복귀 OK")

        # 로그아웃하면 보관된 토큰이 지워진다
        page.evaluate("localStorage.setItem('cs_auth', JSON.stringify({access_token:'x'}))")
        page.evaluate("Auth.cfg = {required:true, url:'%s', anon_key:'%s'}" % (AUTH_URL, ANON))
        page.evaluate("Auth.save(null)")
        assert page.evaluate("localStorage.getItem('cs_auth')") is None
        print("㉒ 로그아웃 시 토큰 삭제 OK")

        assert not errors, f"콘솔 오류: {errors}"
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

auth_srv.shutdown()
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)
shutil.rmtree("reports/stage", ignore_errors=True)
print("CYCLE22 ALL PASS")
