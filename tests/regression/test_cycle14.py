from _common import ROOT, CHROMIUM
"""Cycle 14 verification: timeout resync, offline notice, error codes."""
import subprocess, sys, time, urllib.request

PORT = 8767
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
        page.fill("#teacher-input", "첫 발화입니다")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')")

        # ① 타임아웃 시늉: fetch를 AbortError로 실패시키되 서버는 실제로 턴을 처리
        #    → resyncState가 상태를 서버 턴으로 맞추고 놓친 전사를 재생해야 한다
        turn_before = page.evaluate("App.turn")
        page.evaluate("""() => {
          const origFetch = window.fetch;
          window._origFetch = origFetch;
          let first = true;
          window.fetch = async (url, opts) => {
            if (first && String(url).includes('/turn')) {
              first = false;
              // 재현할 상황: "서버는 턴을 끝냈는데 클라이언트가 기다리다 포기했다".
              // 서버 처리가 끝난 것을 확인한 뒤 AbortError를 내야 경쟁 조건이 없다
              // (기다리지 않고 바로 거부하면 재동기화가 처리 전 상태를 읽어 불안정해진다).
              try { await origFetch(url, opts); } catch (e) {}
              throw new DOMException('aborted', 'AbortError');
            }
            return origFetch(url, opts);
          };
        }""")
        page.fill("#teacher-input", "타임아웃이 나는 발화")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')", timeout=15000)
        page.wait_for_timeout(1500)
        page.evaluate("window.fetch = window._origFetch")
        t = page.locator("#transcript").inner_text()
        assert "상태를 확인합니다" in t, "타임아웃 재동기화 안내 없음"
        turn_after = page.evaluate("App.turn")
        assert turn_after == turn_before + 1, f"재동기화 후 턴 불일치: {turn_before}→{turn_after}"
        assert "타임아웃이 나는 발화" in t, "놓친 전사(교사 발화)가 재생되지 않음"
        assert page.input_value("#teacher-input") == "", "서버가 처리한 입력이 입력창에 복원됨(중복 위험)"
        print("① 타임아웃 → 상태 재동기화 + 놓친 전사 재생 OK")

        # ② 서버가 처리하지 못한 진짜 네트워크 오류 → 입력 복원
        page.evaluate("""() => {
          const origFetch = window.fetch;
          window._origFetch = origFetch;
          let first = true;
          window.fetch = (url, opts) => {
            if (first && String(url).includes('/turn')) {
              first = false;
              return Promise.reject(new TypeError('Failed to fetch'));
            }
            return origFetch(url, opts);
          };
        }""")
        page.fill("#teacher-input", "전송 자체가 실패한 발화")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')", timeout=15000)
        page.evaluate("window.fetch = window._origFetch")
        assert page.input_value("#teacher-input") == "전송 자체가 실패한 발화", "네트워크 오류 시 입력 미복원"
        print("② 네트워크 오류 → 입력 복원 OK")

        # ③ 오프라인/온라인 이벤트 안내
        page.evaluate("window.dispatchEvent(new Event('offline'))")
        page.evaluate("window.dispatchEvent(new Event('online'))")
        t = page.locator("#transcript").inner_text()
        assert "인터넷 연결이 끊어졌습니다" in t and "복구되었습니다" in t, "오프라인 안내 없음"
        print("③ 오프라인/복구 안내 OK")

        assert not errors, f"JS 오류: {errors}"
        browser.close()
    print("CYCLE14 ALL PASS")
finally:
    proc.terminate()
    proc.wait(timeout=5)
