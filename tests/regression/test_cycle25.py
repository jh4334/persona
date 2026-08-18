from _common import ROOT, CHROMIUM
"""Cycle 25 verification: 수업 기록 저장·열람 (전사·리포트 클라우드 저장)."""
import json, os, shutil, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)

from classroom_sim.web.reports import DiskReports, ReportError, ReportLibrary, SupabaseReports

TMP = Path(ROOT) / ".reports_test25"
shutil.rmtree(TMP, ignore_errors=True)

# ---------------------------------------------------------------------------
# ① 디스크 저장소 — 사용자별 격리
# ---------------------------------------------------------------------------
d = DiskReports(TMP)
now = time.time()
d.save({"id": "r1", "user_id": "uA", "class_name": "A반", "lesson_title": "비와 비율",
        "turns": 7, "minutes": 20, "created_at": now}, "# 리포트 A", [{"actor": "teacher"}], "base1")
d.save({"id": "r2", "user_id": "uB", "class_name": "B반", "created_at": now + 1}, "# 리포트 B", [], "base2")

assert [r["id"] for r in d.list("uA")] == ["r1"]
assert [r["id"] for r in d.list("uB")] == ["r2"]
assert d.get("uB", "r1") is None, "남의 기록이 보임"
assert d.delete("uB", "r1") is False, "남의 기록을 지움"
got = d.get("uA", "r1")
assert got["markdown"] == "# 리포트 A" and got["transcript"] == [{"actor": "teacher"}]
assert got["turns"] == 7 and got["class_name"] == "A반"
# 기존 파일 배치는 그대로 (md·transcript.json) + meta 하나가 늘었다
for suffix in (".md", ".transcript.json", ".meta.json"):
    assert (TMP / f"base1{suffix}").is_file(), suffix
print("① 디스크 저장소 격리·열람·파일 배치 OK")

assert d.delete("uA", "r1") is True
assert not (TMP / "base1.md").exists() and not (TMP / "base1.meta.json").exists()
assert d.list("uA") == []
print("② 삭제 시 파일 3종 정리 OK")

# ---------------------------------------------------------------------------
# ③ Supabase 저장소 (가짜 PostgREST)
# ---------------------------------------------------------------------------
ROWS: list[dict] = []
FAIL = {"n": 0}


class PG(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj=None):
        blob = json.dumps(obj if obj is not None else []).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _uid(self):
        q = parse_qs(urlparse(self.path).query)
        return q.get("user_id", ["eq."])[0].split(".", 1)[1]

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
        rows = [r for r in ROWS if r["user_id"] == self._uid()]
        if "id" in q:
            rid = q["id"][0].split(".", 1)[1]
            rows = [r for r in rows if r["id"] == rid]
        rows.sort(key=lambda r: r["created_at_epoch"], reverse=True)
        self._send(200, rows)

    def do_POST(self):
        if self._boom():
            return
        n = int(self.headers.get("Content-Length") or 0)
        ROWS.append(json.loads(self.rfile.read(n)))
        self._send(201)

    def do_DELETE(self):
        if self._boom():
            return
        q = parse_qs(urlparse(self.path).query)
        rid, uid = q["id"][0].split(".", 1)[1], self._uid()
        hit = [r for r in ROWS if r["id"] == rid and r["user_id"] == uid]
        for r in hit:
            ROWS.remove(r)
        self._send(200, hit)


pg = ThreadingHTTPServer(("127.0.0.1", 0), PG)
threading.Thread(target=pg.serve_forever, daemon=True).start()
PG_URL = f"http://127.0.0.1:{pg.server_address[1]}"

os.environ["SUPABASE_URL"] = PG_URL
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "k"
lib = ReportLibrary(TMP)
assert lib.name == "disk+supabase", lib.name

rid = lib.save({"user_id": "uA", "session_id": "s1", "class_name": "A반",
                "lesson_title": "비와 비율", "turns": 7, "minutes": 20},
               "# 원격 리포트", [{"actor": "teacher", "text": "안녕"}], "remote1")
assert len(ROWS) == 1 and ROWS[0]["user_id"] == "uA" and ROWS[0]["turns"] == 7
assert (TMP / "remote1.md").is_file(), "원격에 저장했다고 디스크를 건너뜀"
assert [r["id"] for r in lib.list("uA")] == [rid]
assert lib.list("uB") == [], "남의 기록이 보임"
one = lib.get("uA", rid)
assert one["markdown"] == "# 원격 리포트" and one["transcript"][0]["text"] == "안녕"
print("③ Supabase 저장·목록·열람 OK (디스크에도 함께 남음)")

# ④ 원격이 죽어도 디스크로 계속 간다
FAIL["n"] = 1
rid2 = lib.save({"user_id": "uA", "class_name": "B반"}, "# 장애 중 리포트", [], "remote2")
assert (TMP / "remote2.md").is_file(), "원격 실패가 디스크 저장까지 막음"
assert len(ROWS) == 1, "실패했는데 원격에 들어감"
FAIL["n"] = 1
assert [r["id"] for r in lib.list("uA")] == [rid2, rid], "원격 조회 실패 시 디스크로 대체되지 않음"
FAIL["n"] = 1
assert lib.get("uA", rid2)["markdown"] == "# 장애 중 리포트"
print("④ 원격 장애 시 디스크 폴백 OK")

try:
    lib.get("uA", "없는id")
except ReportError:
    pass
else:
    raise AssertionError("없는 기록이 열림")
lib.delete("uA", rid)
assert ROWS == [] and not (TMP / "remote1.md").exists()
print("⑤ 없는 기록 오류·삭제 시 양쪽 정리 OK")

pg.shutdown()
for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
    os.environ.pop(k, None)
shutil.rmtree(TMP, ignore_errors=True)

# ---------------------------------------------------------------------------
# ⑥ API — 수업 종료 → 기록 생성 → 목록·열람·삭제
# ---------------------------------------------------------------------------
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)
import importlib
from fastapi.testclient import TestClient
from classroom_sim.web import server
importlib.reload(server)
c = TestClient(server.app)

BODY = {"classroom_id": "sample:class_6_3",
        "lesson_path": "lessons/ratio_and_rate.md", "backend": "mock"}
assert c.get("/api/reports").json() == []
sid = c.post("/api/sessions", json=BODY).json()["session_id"]
c.post(f"/api/sessions/{sid}/turn", json={"input": "비를 배워 봅시다"})
c.post(f"/api/sessions/{sid}/turn", json={"input": "@김하늘 어떻게 생각해요?"})
end = c.post(f"/api/sessions/{sid}/turn", json={"input": "/종료"}).json()
assert end["report_saved_path"].startswith("reports/stage/"), end["report_saved_path"]
assert end["report_id"], end
print("⑥ 종료 시 기록 id 반환 OK")

rows = c.get("/api/reports").json()
assert len(rows) == 1 and rows[0]["id"] == end["report_id"], rows
assert rows[0]["class_name"] == "가상초등학교 6학년 3반"
assert "비와 비율" in rows[0]["lesson_title"], rows[0]["lesson_title"]
assert rows[0]["turns"] >= 2 and rows[0]["created_at"] > 0, rows[0]
assert "markdown" not in rows[0], "목록에 본문까지 실려 옴"
print("⑦ 목록 요약(학급·단원·턴·시각) OK")

one = c.get(f"/api/reports/{end['report_id']}").json()
assert len(one["markdown"]) > 100 and len(one["transcript"]) >= 3, (len(one["markdown"]), len(one["transcript"]))
assert c.get("/api/reports/없는id").status_code == 404
print("⑧ 열람(본문·전사) OK")

# 서버를 재시작해도 기록은 남는다
importlib.reload(server)
c2 = TestClient(server.app)
assert len(c2.get("/api/reports").json()) == 1, "재시작 후 기록 유실"
assert c2.delete(f"/api/reports/{end['report_id']}").status_code == 200
assert c2.get("/api/reports").json() == []
assert c2.delete(f"/api/reports/{end['report_id']}").status_code == 404
print("⑨ 재시작 후 유지·삭제 OK")

# ---------------------------------------------------------------------------
# ⑩ 로그인 시 사용자별 격리
# ---------------------------------------------------------------------------
import base64, hashlib, hmac

SECRET = "test-secret-0123456789"


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def tok(sub):
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = b64(json.dumps({"sub": sub, "aud": "authenticated",
                        "exp": int(time.time() + 3600), "email": sub + "@s.kr"}).encode())
    return f"{h}.{p}.{b64(hmac.new(SECRET.encode(), f'{h}.{p}'.encode(), hashlib.sha256).digest())}"


os.environ.update({"SUPABASE_URL": "http://127.0.0.1:1", "SUPABASE_ANON_KEY": "a",
                   "SUPABASE_JWT_SECRET": SECRET, "AUTH_REQUIRED": "1"})
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)
importlib.reload(server)
c3 = TestClient(server.app)
HA, HB = {"Authorization": f"Bearer {tok('tA')}"}, {"Authorization": f"Bearer {tok('tB')}"}

sid = c3.post("/api/sessions", json=BODY, headers=HA).json()["session_id"]
c3.post(f"/api/sessions/{sid}/turn", json={"input": "안녕하세요"}, headers=HA)
rid = c3.post(f"/api/sessions/{sid}/turn", json={"input": "/종료"}, headers=HA).json()["report_id"]

assert [r["id"] for r in c3.get("/api/reports", headers=HA).json()] == [rid]
assert c3.get("/api/reports", headers=HB).json() == [], "남의 기록이 보임"
assert c3.get(f"/api/reports/{rid}", headers=HB).status_code == 404
assert c3.delete(f"/api/reports/{rid}", headers=HB).status_code == 404
assert c3.get("/api/reports").status_code == 401
print("⑩ 로그인 시 사용자별 기록 격리 OK")

for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET", "AUTH_REQUIRED"):
    os.environ.pop(k, None)

# ---------------------------------------------------------------------------
# ⑪ 브라우저 — 수업 종료 → 목록에 나타남 → 다시 열기 → 삭제
# ---------------------------------------------------------------------------
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)

PORT = 8777
proc = subprocess.Popen(
    [sys.executable, "-m", "classroom_sim.web", "--port", str(PORT)],
    cwd=ROOT, env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin:/usr/local/bin"},
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
        page.on("dialog", lambda d: d.accept())

        page.goto(f"http://127.0.0.1:{PORT}/")
        page.wait_for_function("document.body.dataset.screen === 'setup'")
        page.wait_for_selector("#sel-classroom option", state="attached")
        assert page.is_hidden("#past-box"), "기록이 없는데 목록이 보임"

        page.click("#btn-start")
        page.wait_for_function("document.body.dataset.screen === 'stage'", timeout=20000)
        page.fill("#teacher-input", "비를 배워 봅시다")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')", timeout=20000)
        page.fill("#teacher-input", "/종료")
        page.click("#btn-send")
        page.wait_for_function("document.body.dataset.screen === 'report'", timeout=30000)
        print("⑪ 브라우저: 수업 종료 → 리포트 OK")

        # 처음 화면으로 → 지난 기록 목록에 나타난다
        page.click("#btn-restart")
        page.wait_for_function("document.body.dataset.screen === 'setup'", timeout=15000)
        page.wait_for_selector("#past-box:not([hidden])", timeout=10000)
        assert page.inner_text("#past-count").strip() == "1"
        page.click("#past-box > summary")          # 접혀 있으면 글자를 읽을 수 없다
        page.wait_for_selector(".past-title", state="visible")
        assert "가상초등학교 6학년 3반" in page.inner_text(".past-title")
        assert "비와 비율" in page.inner_text(".past-sub")
        print("⑫ 브라우저: 지난 기록 목록 표시 OK")

        # 다시 열면 리포트 화면이 그대로 뜬다
        page.click(".past-open")
        page.wait_for_function("document.body.dataset.screen === 'report'", timeout=10000)
        body = page.inner_text("#report-body")
        assert len(body) > 100, len(body)
        assert "지난 수업 기록" in body, "지난 기록 표시가 없음"
        print("⑬ 브라우저: 지난 기록 다시 열기 OK")

        # 끝난 수업이라 서버에 물어보지 않고도 전사를 내려받을 수 있다
        assert page.evaluate("App.sessionId") is None
        assert page.evaluate("(App.pastTranscript || []).length") >= 2
        print("⑭ 브라우저: 지난 기록의 전사 보유 OK")

        # 삭제
        page.click("#btn-restart")
        page.wait_for_selector("#past-box:not([hidden])", timeout=15000)
        page.click("#past-box > summary")
        page.click(".past-del")
        page.wait_for_selector("#past-box[hidden]", state="attached", timeout=10000)
        assert page.evaluate("App.past.length") == 0
        print("⑮ 브라우저: 기록 삭제 OK")

        assert not errors, f"콘솔 오류: {errors}"
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

for d_ in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d_}", ignore_errors=True)
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)
print("CYCLE25 ALL PASS")
