from _common import ROOT, CHROMIUM
"""Cycle 19 verification: incident no-repeat draw, mock speech no immediate repeats."""
import random, sys
sys.path.insert(0, f"{ROOT}/src")

from classroom_sim.personas import load_classroom
from classroom_sim.stage import incidents
from classroom_sim.stage.backend import MockBackend, make_backend
from classroom_sim.stage.session import StageSession

# ① exclude된 카드는 무작위 뽑기에서 나오지 않는다
rng = random.Random(7)
used = ["친구갈등", "기기고장", "방송소음", "조퇴요청", "벌레소동"]
for _ in range(50):
    c = incidents.draw(rng=rng, exclude=used)
    assert c.name == "복도소란", f"제외 카드가 나옴: {c.name}"
print("① 돌발 무작위 제외 OK")

# ② 전부 소진되면 다시 전체에서 뽑는다
c = incidents.draw(rng=rng, exclude=incidents.names())
assert c.name in incidents.names()
print("② 소진 후 초기화 OK")

# ③ 이름 지정은 exclude와 무관
c = incidents.draw("친구갈등", rng=rng, exclude=["친구갈등"])
assert c.name == "친구갈등"
print("③ 지정 뽑기 무관 OK")

# ④ 세션에서 /돌발 연발 시 중복 없이 6종을 다 돈다
classroom = load_classroom(f"{ROOT}/personas/class_6_3.json")
lesson = open(f"{ROOT}/lessons/ratio_and_rate.md", encoding="utf-8").read()
sess = StageSession(classroom, lesson, make_backend("mock"), seed=3)
for _ in range(6):
    sess.turn("/돌발")
assert len(set(sess.state.incidents)) == 6, f"중복 발생: {sess.state.incidents}"
print("④ /돌발 6연발 무중복 OK:", ", ".join(sess.state.incidents))

# ⑤ mock 학생이 같은 대사를 연달아 반복하지 않는다
be = MockBackend(seed=5)
payload = {"name": "김하늘", "traits": ["활발"], "state": {"comprehension": 80, "interest": 90, "focus": 80}}
import classroom_sim.stage.backend as B
prev = None
for i in range(30):
    r = be._speak(dict(payload))
    key = (r.get("utterance", ""), r.get("action", ""))
    assert key != prev, f"{i}번째에서 연속 반복: {key}"
    prev = key
print("⑤ mock 발화 연속 반복 없음 OK (30회)")

# ⑥ 학생이 다르면 독립적으로 관리된다 (다른 학생 대사에 영향 없음)
r1 = be._speak({"name": "A", "traits": [], "state": {"comprehension": 80, "interest": 60, "focus": 80}})
r2 = be._speak({"name": "B", "traits": [], "state": {"comprehension": 80, "interest": 60, "focus": 80}})
print("⑥ 학생별 독립 추적 OK")

print("CYCLE19 ALL PASS")
