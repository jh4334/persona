from _common import ROOT, CHROMIUM
"""Cycle 15 verification: export filenames, print button/stylesheet."""
import subprocess, sys, time, urllib.request

PORT = 8769
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
        page.fill("#teacher-input", "오늘 수업 시작")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')")
        page.on("dialog", lambda d: d.accept())
        page.fill("#teacher-input", "/종료")
        page.click("#btn-send")
        page.wait_for_selector("#report-body", state="visible", timeout=30000)

        # ① 리포트 md 다운로드 파일명: 학급명+날짜
        with page.expect_download() as dl:
            page.click("#btn-download-md")
        name = dl.value.suggested_filename
        assert name.startswith("리포트_") and name.endswith(".md"), name
        assert "가상초등학교" in name or "6학년" in name, f"학급명 없음: {name}"
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}", name), f"날짜 없음: {name}"
        print(f"① 리포트 파일명 OK: {name}")

        # ② 전사 JSON 파일명
        with page.expect_download() as dl:
            page.click("#btn-download")
        name = dl.value.suggested_filename
        assert name.startswith("전사_") and name.endswith(".json"), name
        print(f"② 전사 파일명 OK: {name}")

        # ③ 인쇄 버튼 존재 + 인쇄 미디어에서 리포트 본문만 보임
        assert page.locator("#btn-print").is_visible(), "인쇄 버튼 없음"
        page.emulate_media(media="print")
        vis = page.evaluate("""() => ({
          report: getComputedStyle(document.querySelector('#report-body')).display !== 'none',
          actions: getComputedStyle(document.querySelector('.report-actions')).display === 'none',
          stage: getComputedStyle(document.querySelector('#screen-stage')).display === 'none',
          mdBg: getComputedStyle(document.querySelector('.md')).backgroundColor,
          mdColor: getComputedStyle(document.querySelector('.md')).color,
        })""")
        assert vis["report"], "인쇄 시 리포트 본문이 숨겨짐"
        assert vis["actions"] and vis["stage"], "인쇄 시 버튼/무대가 함께 나옴"
        assert vis["mdBg"] in ("rgb(255, 255, 255)", "rgba(255, 255, 255, 1)"), vis["mdBg"]
        assert vis["mdColor"] == "rgb(0, 0, 0)", vis["mdColor"]
        page.emulate_media(media="screen")
        print("③ 인쇄 스타일 (흰 배경·본문만) OK")

        assert not errors, f"JS 오류: {errors}"
        browser.close()
    print("CYCLE15 ALL PASS")
finally:
    proc.terminate()
    proc.wait(timeout=5)
