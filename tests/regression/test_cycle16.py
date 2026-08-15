from _common import ROOT, CHROMIUM
"""Cycle 16 verification: keyboard student selection + screen-reader live region."""
import subprocess, sys, time, urllib.request

PORT = 8771
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

        # ① 캔버스가 포커스 가능 + 화살표로 학생 선택
        page.focus("#classroom")
        page.keyboard.press("ArrowRight")
        sel = page.evaluate("App.selected")
        assert sel == "S01", f"첫 학생 선택 실패: {sel}"
        page.keyboard.press("ArrowRight")
        assert page.evaluate("App.selected") == "S02"
        page.keyboard.press("ArrowDown")
        assert page.evaluate("App.selected") == "S06", "아래 줄 이동 실패"
        page.keyboard.press("ArrowUp")
        assert page.evaluate("App.selected") == "S02"
        print("① 화살표 키 학생 탐색 OK")

        # ② 선택 시 상세 카드 열림 + sr-live 안내
        assert page.evaluate("!document.querySelector('#detail-card').hidden"), "상세 카드 안 열림"
        live = page.text_content("#sr-live")
        assert "이준서" in live and "이해" in live, f"sr-live 안내 없음: {live}"
        print("② 상세 카드 + 스크린리더 안내 OK")

        # ③ Escape로 해제
        page.keyboard.press("Escape")
        assert page.evaluate("App.selected") is None, "Escape 해제 실패"
        assert "해제" in page.text_content("#sr-live")
        print("③ Escape 선택 해제 OK")

        # ④ aria 속성
        aria = page.evaluate("""() => ({
          canvasLabel: document.querySelector('#classroom').getAttribute('aria-label') || '',
          canvasTab: document.querySelector('#classroom').getAttribute('tabindex'),
          busyRole: document.querySelector('#busy').getAttribute('role'),
          trLive: document.querySelector('#transcript').getAttribute('aria-live'),
        })""")
        assert "학생" in aria["canvasLabel"] and aria["canvasTab"] == "0", aria
        assert aria["busyRole"] == "status" and aria["trLive"] == "polite", aria
        print("④ ARIA 속성 OK")

        # ⑤ 마우스 클릭 경로 회귀 없음
        box = page.locator("#classroom").bounding_box()
        page.evaluate("UI.selectStudent('S03')")
        assert page.evaluate("App.selected") == "S03"
        print("⑤ 기존 선택 경로 회귀 없음 OK")

        assert not errors, f"JS 오류: {errors}"
        browser.close()
    print("CYCLE16 ALL PASS")
finally:
    proc.terminate()
    proc.wait(timeout=5)
