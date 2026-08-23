import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from classroom_sim.web import mcp


CLASSROOM = {
    "class_name": "테스트 학급",
    "students": [
        {"id": "S01", "name": "김하늘"},
        {"id": "S02", "name": "이준서"},
    ],
}


class MemoryStore:
    name = "memory"

    def __init__(self):
        self.rows = {}
        self.fail_next = False

    def save(self, sid, payload, token=None):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("save failed")
        self.rows[sid] = copy.deepcopy(payload)

    def load_one(self, sid, token=None):
        return copy.deepcopy(self.rows.get(sid))

    def delete(self, sid, token=None):
        self.rows.pop(sid, None)


class Library:
    def resolve(self, user_id, classroom_id, token=None):
        return None, copy.deepcopy(CLASSROOM)


class Reports:
    def __init__(self):
        self.saved = []

    def save(self, meta, markdown, transcript, base, token=None):
        self.saved.append((copy.deepcopy(meta), markdown, copy.deepcopy(transcript)))
        return "report-1"


class Incidents:
    pass


class McpPersistenceTest(unittest.TestCase):
    def make_server(self, store, reports=None):
        return mcp.McpServer(Library(), reports or Reports(), Incidents(), store)

    def test_fresh_instance_continues_and_ends_session(self):
        store = MemoryStore()
        reports = Reports()
        started = self.make_server(store, reports).start_session(
            {"classroom_id": "mine", "lesson_text": "분수 수업"}, "teacher-a", "jwt-a")
        sid = started["session_id"]
        self.assertTrue(sid.startswith("mcp_"))

        turn = self.make_server(store, reports).record_turn({
            "session_id": sid,
            "teacher_input": "분수를 비교해 봅시다.",
            "minute": 5,
            "phase": "전개",
            "state_updates": {"S01": {"comprehension": 70}},
            "events": [{"student_id": "S01", "utterance": "분모부터 볼게요."}],
        }, "teacher-a", "jwt-a")
        self.assertEqual(turn["turn"], 1)

        state = self.make_server(store, reports).get_state(
            {"session_id": sid}, "teacher-a", "jwt-a")
        self.assertEqual(state["turn"], 1)
        self.assertEqual(state["minute"], 5)
        self.assertEqual(state["states"][0]["comprehension"], 70)

        first = self.make_server(store, reports).end_session(
            {"session_id": sid}, "teacher-a", "jwt-a")
        self.assertIn("report_template", first)
        finished = self.make_server(store, reports).end_session(
            {"session_id": sid, "report_markdown": "# 수업 기록"},
            "teacher-a", "jwt-a")
        self.assertTrue(finished["saved"])
        self.assertNotIn(sid, store.rows)
        self.assertEqual(len(reports.saved), 1)

    def test_snapshot_owner_is_checked_after_load(self):
        store = MemoryStore()
        sid = self.make_server(store).start_session(
            {"classroom_id": "mine", "lesson_text": "수업"}, "teacher-a", "jwt-a",
        )["session_id"]
        with self.assertRaises(mcp.RpcError):
            self.make_server(store).get_state({"session_id": sid}, "teacher-b", "jwt-b")

    def test_failed_turn_save_rolls_back_memory_state(self):
        store = MemoryStore()
        server = self.make_server(store)
        sid = server.start_session(
            {"classroom_id": "mine", "lesson_text": "수업"}, "teacher-a", "jwt-a",
        )["session_id"]
        before = copy.deepcopy(store.rows[sid])
        store.fail_next = True

        with self.assertRaises(mcp.RpcError):
            server.record_turn({
                "session_id": sid,
                "teacher_input": "실패해야 하는 턴",
                "minute": 5,
                "state_updates": {"S01": {"comprehension": 75}},
            }, "teacher-a", "jwt-a")

        self.assertEqual(store.rows[sid], before)
        state = server.get_state({"session_id": sid}, "teacher-a", "jwt-a")
        self.assertEqual(state["turn"], 0)
        self.assertEqual(state["minute"], 0)


if __name__ == "__main__":
    unittest.main()
