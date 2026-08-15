from _common import ROOT, CHROMIUM
"""Cycle 4 verification: /종료 confirm dialog + input restore on failure."""
import subprocess, sys, time, socket, urllib.request

PORT = 8759
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
        page.goto(f"http://127.0.0.1:{PORT}/")
        page.wait_for_selector("#sel-classroom option", state="attached")
        page.select_option("#sel-backend", "mock")
        page.click("#btn-start")
        page.wait_for_function("document.body.dataset.screen === 'stage'")

        # 한 턴 진행
        page.fill("#teacher-input", "오늘은 비와 비율을 공부해요")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')")

        # ① /종료 → confirm 취소 → 수업 유지
        fired = {"n": 0}
        def dismiss(dialog):
            fired["n"] += 1
            dialog.dismiss()
        page.on("dialog", dismiss)
        page.fill("#teacher-input", "/종료")
        page.click("#btn-send")
        page.wait_for_timeout(800)
        assert fired["n"] == 1, f"confirm 다이얼로그가 발동하지 않음 (fired={fired['n']})"
        assert page.evaluate("document.body.dataset.screen") == "stage", "취소했는데 종료됨"
        print("① /종료 취소 → 수업 유지 OK")

        # ② /종료 → confirm 수락 → 리포트 화면
        page.remove_listener("dialog", dismiss)
        page.on("dialog", lambda d: d.accept())
        page.fill("#teacher-input", "/종료")
        page.click("#btn-send")
        page.wait_for_selector("#report-body", state="visible", timeout=30000)
        assert page.evaluate("document.body.dataset.screen") == "report", "수락했는데 리포트로 전환 안 됨"
        print("② /종료 수락 → 리포트 OK")

        # ③ 죽은 세션으로 전송 → 오류 시 입력 복원
        page2 = browser.new_page()
        page2.goto(f"http://127.0.0.1:{PORT}/")
        page2.wait_for_selector("#sel-classroom option", state="attached")
        page2.click("#btn-start")
        page2.wait_for_function("document.body.dataset.screen === 'stage'")
        page2.evaluate("App.sessionId = 'no-such-session'")
        page2.fill("#teacher-input", "이 내용은 남아야 한다")
        page2.click("#btn-send")
        page2.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')")
        val = page2.input_value("#teacher-input")
        assert val == "이 내용은 남아야 한다", f"입력 복원 실패: {val!r}"
        print("③ 전송 실패 시 입력 복원 OK")

        browser.close()
    print("CYCLE4 ALL PASS")
finally:
    proc.terminate()
    proc.wait(timeout=5)
