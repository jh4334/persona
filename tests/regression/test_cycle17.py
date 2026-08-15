from _common import ROOT, CHROMIUM
"""Cycle 17 verification: per-student utterance history in detail card."""
import subprocess, sys, time, urllib.request

PORT = 8773
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

        # 김하늘을 지목해 발화를 만든다
        page.fill("#teacher-input", "@김하늘 비와 비율의 차이가 뭘까?")
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')")

        # ① 카드 열고 '오늘 발언' 펼치기 → 발화 표시
        page.evaluate("UI.selectStudent('S01')")
        page.click("#dc-history summary")
        page.wait_for_function(
            "document.querySelector('#dc-history-body').textContent.indexOf('여는 중') === -1")
        body = page.text_content("#dc-history-body")
        assert "[" in body and "분]" in body, f"발언 기록 없음: {body}"
        assert "여는 중" not in body
        print("① 발언 모아보기 표시 OK:", body.strip()[:50], "...")

        # ② 학생 전환 시 접히고, 이전 학생 기록이 남지 않는다
        page.evaluate("UI.selectStudent('S07')")
        assert page.evaluate("!document.querySelector('#dc-history').open"), "학생 전환 시 접힘 실패"
        assert "저요" not in page.text_content("#dc-history-body"), "이전 학생 기록이 본문에 남음"
        page.click("#dc-history summary")
        page.wait_for_function(
            "document.querySelector('#dc-history-body').textContent.indexOf('여는 중') === -1")
        body = page.text_content("#dc-history-body")
        assert "저요" not in body, f"다른 학생 발언이 섞임: {body}"
        assert ("아직 발언이 없습니다" in body) or ("분]" in body), body
        print("② 학생 전환 시 격리 OK")

        # ③ 새 턴이 지나면 다시 열 때 갱신 (캐시 무효화)
        page.evaluate("UI.selectStudent('S01')")
        page.click("#dc-history summary")
        page.wait_for_function(
            "document.querySelector('#dc-history-body').textContent.indexOf('분]') !== -1")
        before = page.text_content("#dc-history-body")
        page.fill("#teacher-input", "@김하늘 좋아, 예를 하나 들어볼래?")
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')")
        page.wait_for_timeout(600)
        after = page.text_content("#dc-history-body")
        assert len(after) > len(before), "턴 이후 발언 기록 미갱신"
        print("③ 턴 경과 시 자동 갱신 OK")

        assert not errors, f"JS 오류: {errors}"
        browser.close()
    print("CYCLE17 ALL PASS")
finally:
    proc.terminate()
    proc.wait(timeout=5)
