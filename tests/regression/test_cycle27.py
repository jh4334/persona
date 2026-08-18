from _common import ROOT
"""Cycle 27 verification: MCP 서버 — ChatGPT가 직접 무대를 진행한다.

핵심은 심판이다. 모델이 자유롭게 연기하되 서버가 게이지 급변·페르소나 붕괴·
발언 쏠림·시간 역행을 잡아내고 교정 지시를 돌려주는지 본다. 이것이 없으면
커스텀 GPT와 다를 게 없다.
"""
import base64, hashlib, hmac, importlib, json, os, shutil, sys, time

sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)

from classroom_sim.web import mcp_rules as R

# ---------------------------------------------------------------------------
# 1부: 심판 규칙 (프로토콜 없이)
# ---------------------------------------------------------------------------

prev = {"S01": {"comprehension": 60, "interest": 60, "focus": 70, "emotion": "평온", "visible_action": ""}}

fixed, notes = R.judge_gauges(prev, {"S01": {"comprehension": 100}})
assert fixed["S01"]["comprehension"] == 85, fixed        # 60 + 25
assert notes and "25점" in notes[0], notes
fixed, notes = R.judge_gauges(prev, {"S01": {"comprehension": 0}})
assert fixed["S01"]["comprehension"] == 35, fixed        # 60 - 25
fixed, notes = R.judge_gauges(prev, {"S01": {"comprehension": 70}})
assert fixed["S01"]["comprehension"] == 70 and not notes, (fixed, notes)
fixed, notes = R.judge_gauges(prev, {"S01": {"comprehension": 999}})
assert fixed["S01"]["comprehension"] == 85, "범위 밖 값이 새어 나감"
fixed, notes = R.judge_gauges(prev, {"S01": {"comprehension": "이상한값"}})
assert fixed["S01"]["comprehension"] == 60, "형이 틀린 값에 기존치가 안 남음"
fixed, notes = R.judge_gauges(prev, {"S99": {"comprehension": 90}})
assert fixed["S01"] == prev["S01"] and "S99" in notes[0], notes
fixed, _ = R.judge_gauges(prev, {})
assert fixed["S01"] == prev["S01"], "안 보낸 학생의 값이 바뀜"
print("① 게이지 심판(급변·범위·형·미지 학생·부분 갱신) OK")

t, n = R.judge_time(20, 10, "say")
assert t == 20 and "되돌아갔" in n[0], (t, n)
t, n = R.judge_time(20, 60, "say")
assert t == 35 and "15분" in n[0], (t, n)
t, n = R.judge_time(20, 60, "time_skip")
assert t == 60 and not n, (t, n)          # 시간 건너뛰기는 40분까지 허용
t, n = R.judge_time(20, 100, "time_skip")
assert t == 60, (t, n)
t, n = R.judge_time(20, 25, "say")
assert t == 25 and not n
print("② 시간 심판(역행·상한·건너뛰기 예외) OK")

p, n = R.judge_phase("전개", "활동")
assert p == "활동" and not n
p, n = R.judge_phase("전개", "쉬는시간")
assert p == "전개" and "쓰지 않는 국면" in n[0], n
p, n = R.judge_phase("전개", None)
assert p == "전개" and not n
print("③ 국면 화이트리스트 OK")

personas = {
    "S01": {"name": "강도윤", "achievement_level": "중",
            "cognitive": {"주의집중_지속시간": "5~15분"}},
    "S02": {"name": "최민준", "achievement_level": "하", "cognitive": {}},
}
before = {"S01": {"comprehension": 60, "focus": 70}, "S02": {"comprehension": 40}}
after = {"S01": {"comprehension": 60, "focus": 85}, "S02": {"comprehension": 60}}
notes = R.judge_persona(personas, before, after, minute=30)
assert any("주의집중" in x and "강도윤" in x for x in notes), notes
assert any("성취 수준" in x and "최민준" in x for x in notes), notes
assert not R.judge_persona(personas, before, {"S01": {"focus": 85}, "S02": {"comprehension": 45}}, minute=8)
print("④ 페르소나 개연성 심판 OK")

roster = ["S01", "S02", "S03"]
notes = R.judge_equity([["S01"]] * 8, roster)
assert any("쏠렸" in x for x in notes) and any("한 번도" in x for x in notes), notes
assert not R.judge_equity([["S01"], ["S02"]], roster), "표본이 적은데 지적함"
assert not R.judge_equity([["S01"], ["S02"], ["S03"]] * 3, roster), "고른데 지적함"
print("⑤ 발언 형평성 심판 OK")

# ---------------------------------------------------------------------------
# 2부: JSON-RPC 프로토콜
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient
from classroom_sim.web import server
importlib.reload(server)
c = TestClient(server.app)

SEQ = [0]


def rpc(method, params=None, headers=None):
    SEQ[0] += 1
    return c.post("/mcp", json={"jsonrpc": "2.0", "id": SEQ[0], "method": method,
                                "params": params or {}}, headers=headers or {}).json()


def tool(name, args=None, headers=None):
    r = rpc("tools/call", {"name": name, "arguments": args or {}}, headers)
    return r["result"]


def data(name, args=None, headers=None):
    return tool(name, args, headers)["structuredContent"]


init = rpc("initialize")["result"]
assert init["protocolVersion"] and init["serverInfo"]["name"]
assert "미화하지 마세요" in init["instructions"], "연기 지침이 initialize에 없음"
assert rpc("ping")["result"] == {}
tools = rpc("tools/list")["result"]["tools"]
assert [t["name"] for t in tools] == ["list_classrooms", "create_classroom", "start_session",
                                      "record_turn", "get_state", "trigger_incident", "end_session"]
for t in tools:
    assert t["description"] and t["inputSchema"]["type"] == "object", t["name"]
assert rpc("없는메서드")["error"]["code"] == -32601
assert c.post("/mcp", content=b"{not json").status_code == 400
# 알림(id 없음)에는 응답 본문이 없다
assert c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
print("⑥ JSON-RPC 규약(initialize·tools/list·ping·오류·알림) OK")

# 도구 오류는 프로토콜 오류가 아니라 isError 결과로 — 모델이 읽고 고치게
bad = tool("start_session", {"classroom_id": "없는학급", "lesson_text": "x"})
assert bad["isError"] is True and "찾을 수 없" in bad["content"][0]["text"], bad
bad = tool("record_turn", {"session_id": "없는세션", "teacher_input": "x"})
assert bad["isError"] is True
assert "error" not in rpc("tools/call", {"name": "list_classrooms", "arguments": {}}), "정상 호출이 오류"
assert tool("없는도구")["isError"] is True
print("⑦ 도구 오류를 isError 결과로 전달 OK")

# ---------------------------------------------------------------------------
# 3부: 수업 한 판
# ---------------------------------------------------------------------------
s = data("start_session", {"classroom_id": "sample:class_6_3",
                           "lesson_text": "# 비와 비율\n두 수를 비교합니다."})
sid = s["session_id"]
ids = [x["id"] for x in s["students"]]
assert len(ids) == 12 and s["initial_states"][0]["comprehension"] == 60
assert "미화하지 마세요" in s["acting_guide"]
print("⑧ 수업 시작(페르소나·초기 게이지·지침) OK")

r = data("record_turn", {"session_id": sid, "teacher_input": "비란 두 수를 비교하는 거예요",
                         "events": [{"student_id": ids[0], "utterance": "3 대 5랑 5 대 3은 같아요?"}],
                         "state_updates": {ids[0]: {"interest": 70, "emotion": "몰입"}},
                         "minute": 3, "phase": "전개"})
assert r["corrections"] == [], r["corrections"]
assert r["turn"] == 1 and r["minute"] == 3 and r["phase"] == "전개"
got = [x for x in r["states"] if x["id"] == ids[0]][0]
assert got["interest"] == 70 and got["emotion"] == "몰입"
print("⑨ 정상 턴 — 교정 없음 OK")

r = data("record_turn", {"session_id": sid, "teacher_input": "계속합시다",
                         "events": [{"student_id": "S99", "utterance": "유령"}],
                         "state_updates": {ids[1]: {"comprehension": 100}},
                         "minute": 1, "phase": "쉬는시간"})
joined = " / ".join(r["corrections"])
assert "25점" in joined and "S99" in joined and "되돌아갔" in joined and "국면" in joined, joined
assert [x for x in r["states"] if x["id"] == ids[1]][0]["comprehension"] == 85
assert r["minute"] == 3 and r["phase"] == "전개", (r["minute"], r["phase"])
print("⑩ 한 턴에 네 가지 위반 동시 교정 OK")

for i in range(8):
    r = data("record_turn", {"session_id": sid, "teacher_input": f"질문 {i}",
                             "events": [{"student_id": ids[0], "utterance": "저요!"}],
                             "minute": 5 + i})
assert any("쏠렸" in x for x in r["corrections"]), r["corrections"]
assert any("한 번도" in x for x in r["corrections"]), r["corrections"]
print("⑪ 발언 쏠림·소외 지적 OK")

used = set()
for _ in range(6):
    card = data("trigger_incident", {"session_id": sid})["card"]
    assert card not in used, f"돌발 카드 중복: {card}"
    used.add(card)
print("⑫ 돌발 카드 6종 무중복 OK")

st = data("get_state", {"session_id": sid})
assert st["turn"] == 10 and len(st["states"]) == 12 and len(st["incidents_used"]) == 6
print("⑬ 상태 조회 OK")

# 종료 1차 — 통계와 틀
e = data("end_session", {"session_id": sid})
stats = e["stats"]
assert stats["turns"] == 10
assert stats["speak_share_top3"][0]["share"] >= 0.8, stats["speak_share_top3"]
# 12명 중 실제로 드러난 건 ids[0] 하나뿐 — ⑩의 S99 장면은 반려됐다
assert len(stats["never_spoke"]) == 11, stats["never_spoke"]
assert len(stats["incidents"]) == 6
assert "리포트" in e["report_template"] and "시뮬레이션" in e["report_template"]
assert data("get_state", {"session_id": sid})["turn"] == 10, "1차 종료로 수업이 닫힘"
print("⑭ 종료 1차 — 통계·리포트 틀 OK")

# 종료 2차 — 리포트 저장
e2 = data("end_session", {"session_id": sid, "report_markdown": "# 수업 리포트\n내용입니다."})
assert e2["saved"] is True and e2["report_id"]
rows = c.get("/api/reports").json()
assert len(rows) == 1 and rows[0]["id"] == e2["report_id"], rows
one = c.get(f"/api/reports/{rows[0]['id']}").json()
assert one["markdown"] == "# 수업 리포트\n내용입니다."
assert len(one["transcript"]) > 10, len(one["transcript"])
assert tool("get_state", {"session_id": sid})["isError"] is True, "종료된 수업이 계속 열림"
print("⑮ 종료 2차 — 리포트 저장 + 웹 기록에 반영 OK")

# ---------------------------------------------------------------------------
# 4부: 인증·격리
# ---------------------------------------------------------------------------
SECRET = "test-secret-0123456789"


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def tok(sub):
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = b64(json.dumps({"sub": sub, "aud": "authenticated",
                        "exp": int(time.time() + 3600), "email": sub + "@s.kr"}).encode())
    return f"{h}.{p}.{b64(hmac.new(SECRET.encode(), f'{h}.{p}'.encode(), hashlib.sha256).digest())}"


os.environ.update({"SUPABASE_URL": "http://127.0.0.1:1", "SUPABASE_ANON_KEY": "a",
                   "SUPABASE_JWT_SECRET": SECRET, "AUTH_REQUIRED": "1"})
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)
importlib.reload(server)
c = TestClient(server.app)
HA = {"Authorization": f"Bearer {tok('tA')}"}
HB = {"Authorization": f"Bearer {tok('tB')}"}

assert c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
assert rpc("tools/list", headers=HA)["result"]["tools"], "로그인했는데 도구가 안 보임"
sA = data("start_session", {"classroom_id": "sample:class_6_3", "lesson_text": "수업"}, HA)["session_id"]
assert tool("get_state", {"session_id": sA}, HB)["isError"] is True, "남의 수업이 열림"
assert tool("record_turn", {"session_id": sA, "teacher_input": "가로채기"}, HB)["isError"] is True
assert data("get_state", {"session_id": sA}, HA)["turn"] == 0, "주인이 못 열음"
print("⑯ 로그인 필수·사용자별 수업 격리 OK")

for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET", "AUTH_REQUIRED"):
    os.environ.pop(k, None)
for d in (".sessions", ".classrooms"):
    shutil.rmtree(f"{ROOT}/{d}", ignore_errors=True)
shutil.rmtree(f"{ROOT}/reports/stage", ignore_errors=True)
print("CYCLE27 ALL PASS")
