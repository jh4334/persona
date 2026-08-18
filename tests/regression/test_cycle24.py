from _common import ROOT, CHROMIUM
"""Cycle 24 verification: 학급 만들기 폼 (JSON 없이 학급을 만든다)."""
import json, os, shutil, subprocess, sys, time, urllib.request

sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)

# ① 속성 카탈로그 API
from fastapi.testclient import TestClient
from classroom_sim.web import server

d = TestClient(server.app).get("/api/dimensions").json()
assert d["version"] and len(d["groups"]) == 9, d.get("version")
total = sum(len(g["dimensions"]) for g in d["groups"])
assert total == 102, total
g0 = d["groups"][0]
assert g0["key"] and g0["label"] and g0["dimensions"][0]["key"], g0
print(f"① /api/dimensions OK (9그룹 {total}속성)")

PORT = 8775
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
        page = browser.new_page(viewport={"width": 900, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{PORT}/")
        page.wait_for_function("document.body.dataset.screen === 'setup'")
        page.wait_for_selector("#sel-classroom option", state="attached")

        page.click("#btn-cls-add")
        page.wait_for_selector("#cls-editor:not([hidden])")

        # ② 기본 탭은 폼이고, 학생 1명이 준비돼 있다
        assert page.get_attribute("#tab-form", "aria-selected") == "true"
        assert page.is_hidden("#cls-pane-json"), "JSON 탭이 기본으로 열려 있음"
        page.wait_for_selector(".bd-card")
        assert page.inner_text("#bd-count").strip() == "1명", page.inner_text("#bd-count")
        print("② 폼 탭 기본·학생 1명 준비 OK")

        # ③ 학급 이름 없이 저장하면 폼에서 바로 막는다 (서버까지 가지 않는다)
        page.click("#btn-cls-save")
        page.wait_for_selector("#cls-error:not([hidden])")
        assert "학급 이름" in page.inner_text("#cls-error")
        page.fill("#bd-class-name", "행복초 5학년 2반")
        page.fill("#bd-grade", "초등학교 5학년")
        page.click("#btn-cls-save")
        page.wait_for_function(
            "document.querySelector('#cls-error').textContent.includes('이름을 입력')")
        assert "1번 학생" in page.inner_text("#cls-error"), page.inner_text("#cls-error")
        print("③ 학급 이름·학생 이름 누락을 폼에서 사전 차단 OK")

        # ④ 학생 정보 입력 — 접힌 머리글에 즉시 반영
        page.fill('.bd-card.open input[data-k="name"]', "김하늘")
        page.select_option('.bd-card.open select[data-k="achievement_level"]', "상")
        page.fill('.bd-card.open input[data-k="interests"]', "축구, 게임")
        page.fill('.bd-card.open input[data-k="personality"]', "활발하고 質問이 많음")
        page.wait_for_function(
            "document.querySelector('.bd-name').textContent.includes('김하늘')")
        assert "상" in page.inner_text(".bd-lv")
        print("④ 학생 입력·머리글 즉시 반영 OK")

        # ⑤ 속성 그룹 — 접혀 있고, 채우면 개수가 머리글에 보인다
        groups = page.locator(".bd-group")
        assert groups.count() == 9, groups.count()
        assert page.evaluate("[...document.querySelectorAll('.bd-group')].every(g => !g.open)"), \
            "속성 그룹이 처음부터 펼쳐져 있음"
        page.click(".bd-group:first-child > summary")
        page.wait_for_selector(".bd-group[open] .bd-attr")
        first = page.locator(".bd-group[open] .bd-attr select").first
        first.select_option(index=2)
        page.wait_for_function(
            "!!document.querySelector('.bd-group[open] > summary b')")
        print("⑤ 속성 그룹 9개 접힘·선택 시 개수 표시 OK")

        # ⑥ 학생 복제·삭제
        page.click('button[data-act="copy"][data-i="0"]')
        page.wait_for_function("document.querySelector('#bd-count').textContent === '2명'")
        assert "(사본)" in page.inner_text("#bd-students")
        page.click('.bd-card.open button[data-act="del"]')
        page.wait_for_function("document.querySelector('#bd-count').textContent === '1명'")
        print("⑥ 학생 복제·삭제 OK")

        # ⑦ 인원 한 번에 만들기
        page.click("#btn-bd-quick")
        page.wait_for_selector("#bd-quick-panel:not([hidden])")
        for lv, n in [("상", 2), ("중상", 3), ("중", 4), ("중하", 2), ("하", 1)]:
            page.fill(f"#q-{lv}", str(n))
        page.click("#btn-bd-quick-go")
        page.wait_for_function("document.querySelector('#bd-count').textContent === '12명'")
        levels = page.evaluate("Builder.students.map(s => s.achievement_level)")
        assert levels.count("상") == 2 and levels.count("중") == 4 and levels.count("하") == 1, levels
        assert page.is_hidden("#bd-quick-panel")
        print("⑦ 성취 수준별 인원 일괄 생성 OK (12명)")

        # ⑧ 폼 → JSON 변환이 서버 스키마와 맞는지
        built = page.evaluate("Builder.toJSON()")
        assert built["class_name"] == "행복초 5학년 2반" and built["grade"] == "초등학교 5학년"
        assert len(built["students"]) == 12
        ids = [s["id"] for s in built["students"]]
        assert len(set(ids)) == 12, ids
        assert all(s["name"] for s in built["students"])
        assert "description" not in built, "빈 설명이 그대로 들어감"
        print("⑧ 폼 → 학급 JSON 변환 OK")

        # ⑨ 저장 → 목록에 들어가고 바로 선택된다
        page.click("#btn-cls-save")
        page.wait_for_selector("#cls-editor", state="hidden")
        assert page.evaluate(
            "document.querySelector('#sel-classroom').selectedOptions[0].textContent"
        ).startswith("행복초 5학년 2반"), "만든 학급이 선택되지 않음"
        assert "12명" in page.evaluate(
            "document.querySelector('#sel-classroom').selectedOptions[0].textContent")
        print("⑨ 폼으로 만든 학급 저장·자동 선택 OK")

        # ⑩ 그 학급으로 수업이 실제로 돌아간다
        page.click("#btn-start")
        page.wait_for_function("document.body.dataset.screen === 'stage'", timeout=20000)
        assert page.evaluate("App.students.length") == 12
        page.fill("#teacher-input", "비를 배워 봅시다")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')", timeout=20000)
        assert page.evaluate("App.turn") >= 1
        print("⑩ 폼으로 만든 학급으로 수업 진행 OK")

        # ⑪ 편집기를 닫으면 입력이 남지 않는다
        page.goto(f"http://127.0.0.1:{PORT}/")
        page.wait_for_selector("#sel-classroom option", state="attached")
        page.click("#btn-cls-add")
        page.fill("#bd-class-name", "지울 학급")
        page.click("#btn-cls-cancel")
        page.wait_for_selector("#cls-editor", state="hidden")
        page.click("#btn-cls-add")
        page.wait_for_selector("#cls-editor:not([hidden])")
        assert page.input_value("#bd-class-name") == "", "취소한 입력이 남아 있음"
        assert page.inner_text("#bd-count").strip() == "1명"
        print("⑪ 취소 시 폼 초기화 OK")

        # ⑫ 탭을 오가도 각자 내용이 유지된다
        page.fill("#bd-class-name", "탭 시험")
        page.click("#tab-json")
        page.wait_for_selector("#cls-pane-json:not([hidden])")
        page.fill("#cls-json", '{"class_name":"JSON 학급","students":[{"id":"S1","name":"홍길동"}]}')
        page.click("#tab-form")
        page.wait_for_selector("#cls-pane-form:not([hidden])")
        assert page.input_value("#bd-class-name") == "탭 시험"
        page.click("#tab-json")
        assert "JSON 학급" in page.input_value("#cls-json")
        page.click("#btn-cls-save")        # JSON 탭이 열려 있으면 JSON이 저장된다
        page.wait_for_selector("#cls-editor", state="hidden")
        assert page.evaluate(
            "document.querySelector('#sel-classroom').selectedOptions[0].textContent"
        ).startswith("JSON 학급"), "열린 탭의 내용이 저장되지 않음"
        print("⑫ 탭 전환 시 내용 유지·열린 탭 기준 저장 OK")

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
shutil.rmtree("reports/stage", ignore_errors=True)
print("CYCLE24 ALL PASS")
