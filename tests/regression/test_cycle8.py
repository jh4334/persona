from _common import ROOT, CHROMIUM
"""Cycle 8 verification: classroom JSON validation messages + server-side report save."""
import json, shutil, sys, tempfile, os
sys.path.insert(0, f"{ROOT}/src")
os.chdir(f"{ROOT}")

from pathlib import Path
from classroom_sim.personas import load_classroom

tmp = Path(tempfile.mkdtemp())

def expect_error(payload, needle, label):
    f = tmp / "bad.json"
    f.write_text(payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
                 encoding="utf-8")
    try:
        load_classroom(f)
    except ValueError as e:
        assert needle in str(e), f"{label}: 메시지에 '{needle}' 없음 → {e}"
        return
    raise AssertionError(f"{label}: 오류가 나지 않음")

expect_error('{"students": [{"id": "S01",}]}', "JSON 문법 오류", "문법 오류")
expect_error({"class_name": "x"}, '"students" 목록', "students 누락")
expect_error({"students": [{"name": "김하늘"}]}, "id가 없습니다", "id 누락")
expect_error({"students": [{"id": "S01"}]}, "name(이름)이 없습니다", "이름 누락")
expect_error({"students": [{"id": "S01", "name": "가"}, {"id": "s01", "name": "나"}]},
             "중복", "id 중복(대소문자)")
expect_error({"students": [{"id": "S01", "name": "가", "interests": 5}]},
             "목록이어야", "interests 형식")
expect_error({"students": [{"id": "S01", "name": "가", "cognitive": "높음"}]},
             "형태여야", "속성 그룹 형식")
expect_error({"students": []}, "1명 이상", "빈 목록")
print("① 학급 JSON 한국어 검증 8종 OK")

# 문자열 interests는 관대하게 수용
f = tmp / "ok.json"
f.write_text(json.dumps({"students": [{"id": "S01", "name": "가", "interests": "코딩, 축구"}]},
                        ensure_ascii=False), encoding="utf-8")
c = load_classroom(f)
assert c.students[0].interests == ["코딩", "축구"], c.students[0].interests
print("② 문자열 interests 관대 수용 OK")

# 기존 샘플 학급은 그대로 로드
c = load_classroom("personas/class_6_3.json")
assert len(c.students) == 12
print("③ 샘플 학급 회귀 없음 OK")

# ── 서버: 종료 시 리포트가 reports/stage/에 저장되는지 ──
from fastapi.testclient import TestClient
from classroom_sim.web import server

client = TestClient(server.app)
r = client.post("/api/sessions", json={
    "classroom_path": "personas/class_6_3.json",
    "lesson_path": "lessons/ratio_and_rate.md",
    "backend": "mock",
})
assert r.status_code == 200, r.text
sid = r.json()["session_id"]
client.post(f"/api/sessions/{sid}/turn", json={"input": "오늘은 비를 배웁니다"})
r = client.post(f"/api/sessions/{sid}/turn", json={"input": "/종료"})
assert r.status_code == 200, r.text
saved = r.json().get("report_saved_path")
assert saved, "report_saved_path 없음"
p = Path(f"{ROOT}") / saved
assert p.is_file() and p.stat().st_size > 100, f"리포트 파일 미생성: {p}"
tj = p.with_suffix("").with_suffix(".transcript.json")
assert tj.is_file(), "전사 JSON 미생성"
json.loads(tj.read_text(encoding="utf-8"))
print(f"④ 서버 리포트 저장 OK → {saved}")

# 검증 오류가 API 400 메시지로 그대로 전달되는지
bad = Path("personas/_bad_test.json")
bad.write_text(json.dumps({"students": [{"name": "x"}]}, ensure_ascii=False), encoding="utf-8")
try:
    r = client.post("/api/sessions", json={
        "classroom_path": "personas/_bad_test.json",
        "lesson_path": "lessons/ratio_and_rate.md",
        "backend": "mock",
    })
    assert r.status_code == 400
    assert "id가 없습니다" in r.json()["detail"], r.json()["detail"]
finally:
    bad.unlink()
print("⑤ 검증 메시지 API 전달 OK")

shutil.rmtree(tmp)
print("CYCLE8 ALL PASS")
