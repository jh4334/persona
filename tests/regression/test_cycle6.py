from _common import ROOT, CHROMIUM
"""Cycle 6 verification: autocomplete, local help, typo precheck."""
import subprocess, sys, time, urllib.request

PORT = 8763
proc = subprocess.Popen(
    [sys.executable, "-m", "classroom_sim.web", "--port", str(PORT)],
    cwd=f"{ROOT}", env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin:/usr/local/bin"},
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
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
        page.wait_for_selector("#sel-classroom option", state="attached")
        page.click("#btn-start")
        page.wait_for_function("document.body.dataset.screen === 'stage'")

        # ① '@' 입력 → 12명 후보, '@김' → 필터링
        page.click("#teacher-input")
        page.type("#teacher-input", "@")
        page.wait_for_selector("#autocomplete:not([hidden])")
        n_all = page.locator("#autocomplete .ac-item").count()
        assert n_all == 12, f"@ 후보 {n_all}명 (12 기대)"
        page.type("#teacher-input", "김")
        page.wait_for_timeout(100)
        names = page.locator("#autocomplete .ac-item").all_text_contents()
        assert names == ["김하늘"], f"'@김' 필터 결과: {names}"
        print("① @ 자동완성 필터 OK")

        # ② 클릭으로 선택 → 입력창에 '@김하늘 '
        page.locator("#autocomplete .ac-item").first.dispatch_event("mousedown")
        val = page.input_value("#teacher-input")
        assert val == "@김하늘 ", f"선택 결과: {val!r}"
        assert page.evaluate("document.querySelector('#autocomplete').hidden"), "선택 후 목록이 안 닫힘"
        print("② 클릭 선택·닫힘 OK")

        # ③ 키보드: ↓ 두 번 + Enter → 2번째 학생, Enter가 전송되지 않아야 함
        page.fill("#teacher-input", "")
        page.type("#teacher-input", "@")
        page.wait_for_selector("#autocomplete:not([hidden])")
        turn_before = page.evaluate("App.turn")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        val = page.input_value("#teacher-input")
        assert val == "@이준서 ", f"키보드 선택 결과: {val!r}"
        assert page.evaluate("App.turn") == turn_before, "자동완성 Enter가 전송을 일으킴"
        print("③ 키보드 탐색·Enter 선택 OK")

        # ④ /도움말 → 서버 왕복 없이 즉시, 턴 수 불변
        page.fill("#teacher-input", "/도움말")
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)
        body = page.locator("#transcript").inner_text()
        assert "/판서" in body and "/돌발" in body, "도움말 내용 누락"
        assert page.evaluate("App.turn") == turn_before, "도움말이 턴을 소모함"
        assert page.input_value("#teacher-input") == "", "도움말 후 입력창이 안 비워짐"
        print("④ /도움말 로컬 처리 OK")

        # ⑤ 도움말 버튼도 동일
        page.click("#cmd-bar button[data-cmd='help']")
        page.wait_for_timeout(100)
        assert page.locator("#transcript").inner_text().count("/판서") >= 2, "도움말 버튼 미동작"
        print("⑤ 도움말 버튼 OK")

        # ⑥ 오타 명령 /판사 → 로컬 안내 + 입력 유지 + 서버 미호출
        page.fill("#teacher-input", "/판사 3:5")
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)
        assert "알 수 없는 명령" in page.locator("#transcript").inner_text()
        assert page.input_value("#teacher-input") == "/판사 3:5", "오타 입력이 지워짐"
        assert page.evaluate("App.turn") == turn_before, "오타가 턴을 소모함"
        print("⑥ 오타 명령 사전 차단 OK")

        # ⑦ 없는 학생 @홍길동 → 로컬 안내 + 반 명단 표시
        page.fill("#teacher-input", "@홍길동 대답해볼까")
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)
        t = page.locator("#transcript").inner_text()
        assert "찾을 수 없습니다" in t and "김하늘" in t, "없는 학생 안내 누락"
        print("⑦ 없는 학생 사전 차단 OK")

        # ⑧ 정상 지목은 그대로 전송됨
        page.fill("#teacher-input", "@김하늘 비와 비율의 차이는?")
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')")
        assert page.evaluate("App.turn") == turn_before + 1, "정상 지목이 전송되지 않음"
        print("⑧ 정상 지목 전송 OK")

        assert not errors, f"JS 오류: {errors}"
        browser.close()
    print("CYCLE6 ALL PASS")
finally:
    proc.terminate()
    proc.wait(timeout=5)
