from _common import ROOT, CHROMIUM
"""Cycle 7 verification: engine survives malformed director/student LLM output."""
import sys
sys.path.insert(0, f"{ROOT}/src")

from classroom_sim.personas import load_classroom
from classroom_sim.stage.backend import make_backend
from classroom_sim.stage.session import StageSession, _safe_int

classroom = load_classroom(f"{ROOT}/personas/class_6_3.json")
lesson = open(f"{ROOT}/lessons/ratio_and_rate.md", encoding="utf-8").read()


def fresh():
    return StageSession(classroom, lesson, make_backend("mock"), seed=1)


# ── _safe_int 자체 ──
assert _safe_int("3분", 1) == 3
assert _safe_int(None, 7) == 7
assert _safe_int([], 7) == 7
assert _safe_int("높음", 5) == 5
assert _safe_int(4.9, 1) == 4
print("① _safe_int OK")

# ── 감독이 온갖 쓰레기를 돌려줘도 turn()이 죽지 않아야 한다 ──
GARBAGE = [
    ["not", "a", "dict"],                                    # dict가 아님
    {"minute_delta": "3분", "phase": "Introduction"},        # 문자열 분, 없는 국면
    {"minute_delta": None, "updates": {"S01": "high"}},      # None, updates가 dict
    {"minute_delta": 99999, "updates": [["S01"], "junk", {"id": "S01", "comprehension": "높음"}]},
    {"speakers": "S01,S02", "narration": {"text": "?"}},     # speakers가 문자열, narration이 dict
    {"speakers": [{"id": "NOPE"}, "S01", {"id": "S01", "cue": ["말해봐"]}], "updates": [{"id": "S01", "emotion": "기쁨" * 40, "visible_action": "x" * 500}]},
]

for i, garbage in enumerate(GARBAGE):
    sess = fresh()
    minute0, phase0 = sess.state.minute, sess.state.phase
    sess._call_director = lambda action, g=garbage: g
    r = sess.turn("여러분 안녕하세요")
    assert r is not None and not r.ended, f"case {i}: 턴이 비정상 종료"
    st = sess.state.students["S01"]
    assert 0 <= st.comprehension <= 100 and 0 <= st.focus <= 100, f"case {i}: 게이지 범위 이탈"
    assert sess.state.minute - minute0 <= 15, f"case {i}: 시간이 {sess.state.minute - minute0}분 점프"
    assert sess.state.phase in ("도입", "전개", "활동", "모둠활동", "정리", "종료"), \
        f"case {i}: 국면 오염 {sess.state.phase!r}"
    assert len(st.emotion) <= 12 and len(st.visible_action) <= 80, f"case {i}: 표시 문자열 미절단"
print(f"② 감독 쓰레기 출력 {len(GARBAGE)}종 방어 OK")

# ── 학생 발화가 dict가 아니어도 침묵 처리 ──
sess = fresh()
sess._call_director = lambda a: {"minute_delta": 1, "speakers": [{"id": "S01"}]}
import classroom_sim.stage.session as sessmod
orig_speak = sessmod.student_agent.speak
sessmod.student_agent.speak = lambda *a, **k: "그냥 문자열"
try:
    r = sess.turn("발화 형식 오류 테스트")
    kinds = [(e.actor, e.kind) for e in r.events]
    assert ("S01", "student_action") in kinds, f"침묵 폴백 없음: {kinds}"
finally:
    sessmod.student_agent.speak = orig_speak
print("③ 학생 발화 비정상 형식 → 침묵 폴백 OK")

# ── /시간 30분은 15분 상한의 예외로 실제 반영 ──
sess = fresh()
r = sess.turn("/시간 30분")
assert sess.state.minute >= 30, f"/시간 30분 미반영: {sess.state.minute}"
print("④ /시간 대량 건너뛰기 예외 OK")

# ── 정상 mock 흐름 회귀 없음 ──
sess = fresh()
r = sess.turn("오늘은 비와 비율을 배웁니다")
assert any(e.kind.startswith("student") for e in r.events), "정상 턴에서 학생 반응 없음"
r2 = sess.turn("@김하늘 비가 뭐였지?")
assert any(e.actor == "S01" for e in r2.events), "지목 학생이 반응하지 않음"
print("⑤ 정상 흐름 회귀 없음 OK")

print("CYCLE7 ALL PASS")
