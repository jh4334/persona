from _common import ROOT, CHROMIUM
"""Cycle 5 verification: transcript DOM cap, batched scroll, dirty-flag rendering."""
import subprocess, sys, time, urllib.request

PORT = 8761
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

        # ① 턴 진행 → 캔버스가 실제로 그려지는지 (dirty 플래그 회귀 확인)
        page.fill("#teacher-input", "오늘은 비와 비율을 배웁니다")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')")
        page.wait_for_timeout(300)
        blank = page.evaluate("""() => {
          const c = document.querySelector('#classroom');
          const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
          for (let i = 3; i < d.length; i += 4) if (d[i] !== 0) return false;
          return true;
        }""")
        assert not blank, "캔버스가 비어 있음 — draw 스킵 로직이 렌더링을 막음"
        print("① 턴 후 캔버스 렌더링 OK")

        # ② 대기 중 프레임 스킵이 실제로 일어나는지 (1초간 draw 횟수 측정)
        draws = page.evaluate("""async () => {
          App.bubbles = [];                      // 말풍선 수명(6초)을 기다리는 대신 비운다
          await new Promise(r => setTimeout(r, 100));
          let n = 0;
          const orig = Stage.drawRoom;
          Stage.drawRoom = function(g) { n++; return orig.call(Stage, g); };
          await new Promise(r => setTimeout(r, 1000));
          Stage.drawRoom = orig;
          return n;
        }""")
        assert draws <= 10, f"유휴 상태에서 초당 {draws}회 그림 — 스킵이 동작하지 않음"
        assert draws >= 1, "유휴 상태인데 한 번도 안 그림 — idle 애니메이션 멈춤"
        print(f"② 유휴 프레임 스킵 OK (초당 {draws}회)")

        # ③ 전사 로그 450줄 주입 → DOM 상한 + 접힘 안내
        counts = page.evaluate("""() => {
          for (let i = 0; i < 450; i++) UI.addLine('system', '', '부하 테스트 줄 ' + i);
          const box = document.querySelector('#transcript');
          return { total: box.childElementCount,
                   note: box.querySelectorAll('.trim-note').length };
        }""")
        assert counts["total"] <= 401, f"전사 DOM {counts['total']}줄 — 상한 미동작"
        assert counts["note"] == 1, f"접힘 안내가 {counts['note']}개"
        print(f"③ 전사 DOM 상한 OK (총 {counts['total']}줄, 안내 1개)")

        # ④ 스크롤이 최하단 유지되는지 (rAF 배치 후)
        page.wait_for_timeout(200)
        at_bottom = page.evaluate("""() => {
          const b = document.querySelector('#transcript');
          return b.scrollHeight - b.scrollTop - b.clientHeight < 4;
        }""")
        assert at_bottom, "배치 스크롤 후 최하단이 아님"
        print("④ 배치 스크롤 최하단 유지 OK")

        # ⑤ '새 수업' 재시작 후에도 무대가 정상 렌더링 (리스너 중복 가드 회귀 확인)
        page.on("dialog", lambda d: d.accept())
        page.fill("#teacher-input", "/종료")
        page.click("#btn-send")
        page.wait_for_selector("#report-body", state="visible", timeout=30000)
        page.click("#btn-restart")
        page.wait_for_function("document.body.dataset.screen === 'setup'")
        page.wait_for_selector("#sel-classroom option", state="attached")
        page.click("#btn-start")
        page.wait_for_function("document.body.dataset.screen === 'stage'")
        page.fill("#teacher-input", "두 번째 수업 시작")
        page.click("#btn-send")
        page.wait_for_function("document.querySelector('#busy').hasAttribute('hidden')")
        page.wait_for_timeout(300)
        blank2 = page.evaluate("""() => {
          const c = document.querySelector('#classroom');
          const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
          for (let i = 3; i < d.length; i += 4) if (d[i] !== 0) return false;
          return true;
        }""")
        assert not blank2, "재시작 후 캔버스가 비어 있음"
        print("⑤ 새 수업 재시작 후 렌더링 OK")

        assert not errors, f"JS 오류 발생: {errors}"
        browser.close()
    print("CYCLE5 ALL PASS")
finally:
    proc.terminate()
    proc.wait(timeout=5)
