from _common import ROOT, CHROMIUM
"""Cycle 23 verification: 내 학급 만들기 (사용자별 저장 + 샘플 분리).

Supabase 저장소는 가짜 PostgREST로, 브라우저 흐름은 Playwright로 검증한다.
"""
import json, os, shutil, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)

from classroom_sim.personas import loads_classroom, parse_classroom
from classroom_sim.web.classrooms import ClassroomError, ClassroomLibrary, DiskClassrooms

CLS = {"class_name": "행복초 5학년 2반", "grade": "초등학교 5학년",
       "students": [{"id": "S01", "name": "김하늘", "achievement_level": "상"},
                    {"id": "S02", "name": "박서준", "achievement_level": "중"}]}
TEXT = json.dumps(CLS, ensure_ascii=False)

# ---------------------------------------------------------------------------
# ① 파싱 분리 — 파일·문자열·딕셔너리가 같은 규칙으로 검증된다
# ---------------------------------------------------------------------------
c = parse_classroom(CLS, "내 학급")
assert c.class_name == "행복초 5학년 2반" and len(c.students) == 2
for label, payload, expect in [
    ("id 누락", {"students": [{"name": "x"}]}, "id가 없습니다"),
    ("name 누락", {"students": [{"id": "S1"}]}, "name(이름)이 없습니다"),
    ("id 중복", {"students": [{"id": "S1", "name": "a"}, {"id": "s1", "name": "b"}]}, "중복"),
    ("students 없음", {"class_name": "x"}, '"students" 목록'),
    ("빈 목록", {"students": []}, "비어 있습니다"),
]:
    try:
        parse_classroom(payload, "내 학급")
    except ValueError as e:
        assert expect in str(e), f"{label}: {e}"
    else:
        raise AssertionError(f"{label}이 통과됨")
try:
    loads_classroom('{"students": [', "내 학급")
except ValueError as e:
    assert "문법 오류" in str(e) and "행" in str(e), e
print("① 문자열·딕셔너리 검증이 파일과 동일 OK (6종)")

# ---------------------------------------------------------------------------
# ② 디스크 저장소 — 사용자별 격리
# ---------------------------------------------------------------------------
tmp = Path(ROOT) / ".classrooms_test23"
shutil.rmtree(tmp, ignore_errors=True)
d = DiskClassrooms(tmp)
d.create("userA", CLS, "cid-1")
d.create("userB", {**CLS, "class_name": "B의 학급"}, "cid-2")
assert [x["class_name"] for x in d.list("userA")] == ["행복초 5학년 2반"]
assert [x["class_name"] for x in d.list("userB")] == ["B의 학급"]
assert d.get("userB", "cid-1") is None, "남의 학급이 보임"
assert d.delete("userB", "cid-1") is False, "남의 학급을 지움"
assert d.get("userA", "cid-1")["class_name"] == "행복초 5학년 2반"
# 사용자 id가 경로가 되지 않는다
d.create("../../etc", CLS, "cid-3")
assert not (tmp.parent / "etc").exists(), "사용자 id로 경로 탈출"
print("② 디스크 저장소 사용자별 격리·경로 탈출 방어 OK")

# ---------------------------------------------------------------------------
# ③ 서가 — 샘플은 읽기 전용, 내 학급은 위에
# ---------------------------------------------------------------------------
lib = ClassroomLibrary(Path(ROOT), tmp)
rows = lib.list("userA")
assert rows[0]["mine"] is True and rows[0]["class_name"] == "행복초 5학년 2반"
assert any(r["id"] == "sample:class_6_3" and r["mine"] is False for r in rows), rows
try:
    lib.delete("userA", "sample:class_6_3")
except ClassroomError as e:
    assert "샘플" in str(e), e
else:
    raise AssertionError("샘플이 지워짐")
# 경로 탈출 — 샘플 id로 저장소 밖을 읽으려는 시도
for evil in ["sample:../../etc/passwd", "sample:../lessons/ratio_and_rate"]:
    try:
        lib.resolve("userA", evil)
    except (ClassroomError, ValueError):
        pass
    else:
        raise AssertionError(f"경로 탈출 통과: {evil}")
print("③ 샘플 읽기 전용·내 학급 우선·경로 탈출 방어 OK")

made = lib.create("userA", TEXT)
assert made["mine"] and made["count"] == 2
assert lib.resolve("userA", made["id"])[0].class_name == "행복초 5학년 2반"
try:
    lib.resolve("userB", made["id"])
except ClassroomError:
    pass
else:
    raise AssertionError("남의 학급으로 수업을 시작할 수 있음")
try:
    lib.create("userA", json.dumps({"students": [{"id": "S%d" % i, "name": "학생%d" % i} for i in range(41)]}))
except ClassroomError as e:
    assert "40명" in str(e), e
else:
    raise AssertionError("41명 학급이 통과됨")
print("④ 서가 생성·소유권·인원 상한 OK")

# ---------------------------------------------------------------------------
# ⑤ Supabase 저장소 (가짜 PostgREST)
# ---------------------------------------------------------------------------
ROWS: list[dict] = []


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

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        uid = self._uid()
        rows = [r for r in ROWS if r["user_id"] == uid]
        if "id" in q:
            cid = q["id"][0].split(".", 1)[1]
            rows = [r for r in rows if r["id"] == cid]
        self._send(200, [{"id": r["id"], "data": r["data"]} for r in rows])

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        ROWS.append(json.loads(self.rfile.read(n)))
        self._send(201)

    def do_DELETE(self):
        q = parse_qs(urlparse(self.path).query)
        cid, uid = q["id"][0].split(".", 1)[1], self._uid()
        hit = [r for r in ROWS if r["id"] == cid and r["user_id"] == uid]
        for r in hit:
            ROWS.remove(r)
        self._send(200, hit)


pg = ThreadingHTTPServer(("127.0.0.1", 0), PG)
threading.Thread(target=pg.serve_forever, daemon=True).start()
PG_URL = f"http://127.0.0.1:{pg.server_address[1]}"

os.environ["SUPABASE_URL"] = PG_URL
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "k"
lib2 = ClassroomLibrary(Path(ROOT), tmp)
assert lib2.name == "supabase", lib2.name
made2 = lib2.create("uA", TEXT)
assert len(ROWS) == 1 and ROWS[0]["user_id"] == "uA"
assert ROWS[0]["name"] == "행복초 5학년 2반" and ROWS[0]["student_count"] == 2
assert [r["class_name"] for r in lib2.list("uA") if r["mine"]] == ["행복초 5학년 2반"]
assert [r for r in lib2.list("uB") if r["mine"]] == [], "남의 학급이 보임"
assert lib2.resolve("uA", made2["id"])[0].class_name == "행복초 5학년 2반"
try:
    lib2.resolve("uB", made2["id"])
except ClassroomError:
    pass
else:
    raise AssertionError("남의 학급이 열림")
lib2.delete("uA", made2["id"])
assert ROWS == []
print("⑤ Supabase 저장소 CRUD·소유권 OK")

pg.shutdown()
for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
    os.environ.pop(k, None)

# ---------------------------------------------------------------------------
# ⑥ API — 만들기·목록·수업 시작·재시작 복구·삭제
# ---------------------------------------------------------------------------
shutil.rmtree(f"{ROOT}/.classrooms", ignore_errors=True)
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)
import importlib
from fastapi.testclient import TestClient
from classroom_sim.web import server
importlib.reload(server)
client = TestClient(server.app)

r = client.post("/api/classrooms", json={"json_text": TEXT})
assert r.status_code == 201, r.text
cid = r.json()["id"]
rows = client.get("/api/classrooms").json()
assert rows[0]["id"] == cid and rows[0]["mine"] is True
assert any(x["id"] == "sample:class_6_3" for x in rows)
print("⑥ 학급 생성 API·목록 OK")

r = client.post("/api/sessions", json={"classroom_id": cid,
                                       "lesson_path": "lessons/ratio_and_rate.md", "backend": "mock"})
assert r.status_code == 200, r.text
sid = r.json()["session_id"]
assert r.json()["class_name"] == "행복초 5학년 2반"
assert [s["name"] for s in r.json()["students"]] == ["김하늘", "박서준"]
client.post(f"/api/sessions/{sid}/turn", json={"input": "비를 배워 봅시다"})

importlib.reload(server)
assert sid in server.SESSIONS, "내 학급으로 만든 수업이 재시작 후 복구되지 않음"
assert server.SESSIONS[sid].classroom.class_name == "행복초 5학년 2반"
print("⑦ 내 학급으로 수업 시작·재시작 복구 OK")

# 수업 중에 학급을 지워도 진행 중이던 수업은 시작할 때의 학생들로 이어진다
cx = TestClient(server.app)
assert cx.delete(f"/api/classrooms/{cid}").status_code == 200
importlib.reload(server)
assert sid in server.SESSIONS, "학급을 지웠다고 진행 중이던 수업까지 사라짐"
assert [s.name for s in server.SESSIONS[sid].classroom.students] == ["김하늘", "박서준"]
r = TestClient(server.app).post(f"/api/sessions/{sid}/turn", json={"input": "이어서"})
assert r.status_code == 200, r.text
# 다시 만들어 뒤 검사를 이어간다
cid = cx.post("/api/classrooms", json={"json_text": TEXT}).json()["id"]
print("⑦-2 학급 삭제 후에도 진행 중 수업 유지 OK")

# 옛 클라이언트(classroom_path)도 계속 동작
c2 = TestClient(server.app)
r = c2.post("/api/sessions", json={"classroom_path": "personas/class_6_3.json",
                                   "lesson_path": "lessons/ratio_and_rate.md", "backend": "mock"})
assert r.status_code == 200 and r.json()["class_name"] == "가상초등학교 6학년 3반", r.text
assert c2.post("/api/sessions", json={"lesson_path": "lessons/ratio_and_rate.md",
                                      "backend": "mock"}).status_code == 400
print("⑧ 옛 classroom_path 호환·학급 미선택 400 OK")

bad = c2.post("/api/classrooms", json={"json_text": '{"students":[{"id":"S1"}]}'})
assert bad.status_code == 400 and "name(이름)이 없습니다" in bad.json()["detail"], bad.text
big = c2.post("/api/classrooms", json={"json_text": "x" * (600 * 1024)})
assert big.status_code == 400 and "512KB" in big.json()["detail"], big.text
print("⑨ 형식 오류·용량 초과 한국어 안내 OK")

assert c2.delete(f"/api/classrooms/{cid}").status_code == 200
assert not any(x["id"] == cid for x in c2.get("/api/classrooms").json())
assert c2.delete("/api/classrooms/sample:class_6_3").status_code == 404
assert c2.delete(f"/api/classrooms/{cid}").status_code == 404
print("⑩ 삭제·샘플 삭제 거부 OK")

# ---------------------------------------------------------------------------
# ⑪ 로그인 상태에서 사용자끼리 학급이 섞이지 않는다
# ---------------------------------------------------------------------------
import base64, hashlib, hmac

SECRET = "test-secret-0123456789"


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def tok(sub):
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = b64(json.dumps({"sub": sub, "aud": "authenticated", "exp": int(time.time() + 3600),
                        "email": sub + "@school.kr"}).encode())
    return f"{h}.{p}.{b64(hmac.new(SECRET.encode(), f'{h}.{p}'.encode(), hashlib.sha256).digest())}"


os.environ.update({"SUPABASE_URL": "http://127.0.0.1:1", "SUPABASE_ANON_KEY": "a",
                   "SUPABASE_JWT_SECRET": SECRET, "AUTH_REQUIRED": "1"})
shutil.rmtree(f"{ROOT}/.classrooms", ignore_errors=True)
importlib.reload(server)
c3 = TestClient(server.app)
HA, HB = {"Authorization": f"Bearer {tok('teacherA')}"}, {"Authorization": f"Bearer {tok('teacherB')}"}

ca = c3.post("/api/classrooms", json={"json_text": TEXT}, headers=HA).json()["id"]
assert [x["id"] for x in c3.get("/api/classrooms", headers=HA).json() if x["mine"]] == [ca]
assert [x for x in c3.get("/api/classrooms", headers=HB).json() if x["mine"]] == [], "남의 학급이 보임"
assert c3.post("/api/sessions", json={"classroom_id": ca, "lesson_path": "lessons/ratio_and_rate.md",
                                      "backend": "mock"}, headers=HB).status_code == 400
assert c3.delete(f"/api/classrooms/{ca}", headers=HB).status_code == 404
assert c3.post("/api/classrooms", json={"json_text": TEXT}).status_code == 401
print("⑪ 로그인 시 사용자별 학급 격리 OK")

for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET", "AUTH_REQUIRED"):
    os.environ.pop(k, None)

# ---------------------------------------------------------------------------
# ⑫ 브라우저 — 만들기 → 선택 → 수업 → 삭제
# ---------------------------------------------------------------------------
shutil.rmtree(f"{ROOT}/.classrooms", ignore_errors=True)
shutil.rmtree(f"{ROOT}/.sessions", ignore_errors=True)

PORT = 8773
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
        page.goto(f"http://127.0.0.1:{PORT}/")
        page.wait_for_function("document.body.dataset.screen === 'setup'")
        page.wait_for_selector("#sel-classroom option", state="attached")

        # 샘플만 있을 때는 삭제 버튼이 없다
        assert page.is_hidden("#btn-cls-del"), "샘플인데 삭제 버튼이 보임"
        assert page.is_hidden("#cls-editor")

        page.click("#btn-cls-add")
        page.wait_for_selector("#cls-editor:not([hidden])")

        # 형식이 틀리면 어디가 문제인지 알려 준다
        page.fill("#cls-json", '{"students":[{"id":"S1"}]}')
        page.click("#btn-cls-save")
        page.wait_for_selector("#cls-error:not([hidden])")
        assert "name(이름)이 없습니다" in page.inner_text("#cls-error")
        print("⑫ 브라우저: 형식 오류 안내 OK")

        page.fill("#cls-json", TEXT)
        page.click("#btn-cls-save")
        page.wait_for_selector("#cls-editor", state="hidden")
        assert page.inner_text("#sel-classroom optgroup:first-child").strip() != ""
        assert page.evaluate(
            "document.querySelector('#sel-classroom').selectedOptions[0].textContent"
        ).startswith("행복초 5학년 2반"), "만든 학급이 자동 선택되지 않음"
        assert page.is_visible("#btn-cls-del"), "내 학급인데 삭제 버튼이 없음"
        assert page.evaluate(
            "[...document.querySelectorAll('#sel-classroom optgroup')].map(g => g.label)"
        ) == ["내 학급", "샘플 학급"]
        print("⑬ 브라우저: 학급 생성 → 자동 선택 → 묶음 표시 OK")

        page.click("#btn-start")
        page.wait_for_function("document.body.dataset.screen === 'stage'", timeout=20000)
        assert "행복초 5학년 2반" in page.inner_text("#tb-class")
        assert page.evaluate("App.students.length") == 2
        page.fill("#teacher-input", "비를 배워 봅시다")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')", timeout=20000)
        assert page.evaluate("App.turn") >= 1
        print("⑭ 브라우저: 내 학급으로 수업 진행 OK")

        # 삭제 — 확인 대화상자 수락
        page.goto(f"http://127.0.0.1:{PORT}/")
        page.wait_for_selector("#sel-classroom option", state="attached")
        page.on("dialog", lambda d: d.accept())
        page.click("#btn-cls-del")
        page.wait_for_function(
            "[...document.querySelectorAll('#sel-classroom optgroup')].every(g => g.label !== '내 학급')",
            timeout=10000)
        assert page.is_hidden("#btn-cls-del")
        print("⑮ 브라우저: 학급 삭제 OK")

        assert not errors, f"콘솔 오류: {errors}"
        browser.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

shutil.rmtree(tmp, ignore_errors=True)
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)
shutil.rmtree("reports/stage", ignore_errors=True)
print("CYCLE23 ALL PASS")
