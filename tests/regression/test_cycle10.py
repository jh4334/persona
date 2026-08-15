from _common import ROOT, CHROMIUM
"""Cycle 10 verification: backend notes, mock notice, first-run intro (once only)."""
import subprocess, sys, time, urllib.request

PORT = 8765
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

        # ① 백엔드 설명이 선택에 따라 바뀜
        note = page.text_content("#backend-note")
        assert "연습 모드" in note, f"mock 설명 없음: {note}"
        page.select_option("#sel-backend", "codex")
        assert "codex login" in page.text_content("#backend-note")
        page.select_option("#sel-backend", "anthropic")
        assert "ANTHROPIC_API_KEY" in page.text_content("#backend-note")
        page.select_option("#sel-backend", "mock")
        print("① 백엔드 설명 전환 OK")

        # ② 첫 수업: mock 안내 + 처음 안내 3줄
        page.click("#btn-start")
        page.wait_for_function("document.body.dataset.screen === 'stage'")
        t = page.locator("#transcript").inner_text()
        assert "연습 모드(mock)" in t, "mock 수업 시작 안내 없음"
        assert "처음이신가요?" in t, "첫 실행 안내 없음"
        print("② mock 안내 + 첫 실행 안내 OK")

        # ③ 두 번째 수업에서는 첫 실행 안내가 반복되지 않음 (localStorage 유지)
        page.on("dialog", lambda d: d.accept())
        page.fill("#teacher-input", "/종료")
        page.click("#btn-send")
        page.wait_for_selector("#report-body", state="visible", timeout=30000)
        page.click("#btn-restart")
        page.wait_for_function("document.body.dataset.screen === 'setup'")
        page.wait_for_selector("#sel-classroom option", state="attached")
        page.click("#btn-start")
        page.wait_for_function("document.body.dataset.screen === 'stage'")
        t2 = page.locator("#transcript").inner_text()
        assert "처음이신가요?" not in t2, "첫 실행 안내가 반복됨"
        assert "연습 모드(mock)" in t2, "mock 안내는 매번 나와야 함"
        print("③ 첫 실행 안내 1회 제한 OK")

        assert not errors, f"JS 오류: {errors}"
        browser.close()
    print("CYCLE10 ALL PASS")
finally:
    proc.terminate()
    proc.wait(timeout=5)
