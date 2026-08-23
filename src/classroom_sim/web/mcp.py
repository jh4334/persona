"""MCP 서버 — ChatGPT가 직접 교실 무대를 진행한다.

`docs/specs/v0.6_chatgpt_app.md`의 설계를 구현하되, 기획서의 "버셀 + TypeScript
별도 서버" 대신 **이 FastAPI 서버에 엔드포인트 하나를 더한다.** 인증·학급
저장소·수업 기록·규칙이 전부 여기 이미 있어서, 따로 만들면 그대로 복제하는
셈이기 때문이다.

역할 분리는 기획서 그대로다. 로컬 웹판에서는 우리가 LLM을 호출하지만,
여기서는 **ChatGPT가 주체**이고 서버는 "규칙과 기억"만 맡는다. 서버는 LLM을
전혀 호출하지 않으므로 운영비가 0이다.

    ChatGPT (사용자 구독)          우리 서버
    ─────────────────────          ─────────────────
    무대 감독 + 학생 배우     →     심판: 게이지 급변·페르소나 붕괴·발언 쏠림 교정
    장면을 지어낸다           →     기억: 학급·상태·전사·리포트 보관

도구 7종은 기획서 표를 따른다. 프로토콜은 JSON-RPC 2.0 (MCP streamable HTTP).

    POST /mcp   initialize | tools/list | tools/call | notifications/*

인증은 웹판과 같은 Bearer 토큰을 쓴다 (`AUTH_REQUIRED`가 켜져 있으면 필수).
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from .mcp_rules import (judge_equity, judge_gauges, judge_persona,
                        judge_phase, judge_time)

log = logging.getLogger("classroom_sim.web")

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "보이는 교실 (classroom-stage)", "version": "0.6"}

MAX_MCP_SESSIONS = 50
MCP_TTL = 6 * 3600

# ChatGPT에게 매 세션 시작 시 건네는 연기 지침. 커스텀 GPT에서 검증된 문구를
# 그대로 옮겼다 — 특히 "미화 금지"가 없으면 모든 학생이 착하고 유능해진다.
ACTING_GUIDE = """당신은 이 교실의 무대 감독이자 모든 학생을 연기하는 배우입니다.

원칙
1. 페르소나에 충실하게. 이해도가 낮은 학생은 실제로 못 알아듣고, 발표불안이
   높은 학생은 지목당하면 말이 짧아지거나 침묵합니다.
2. 미화하지 마세요. 모든 학생이 열심히 참여하는 교실은 현실이 아닙니다.
   딴짓·무기력·눈치 보기·무임승차가 자연스럽게 일어나야 합니다.
3. 교사의 한 마디에 12명이 전부 반응하지 않습니다. 한 턴에 1~3명만 겉으로
   드러나게 하고, 나머지는 게이지 변화로만 표현하세요.
4. 지목당한 학생은 반드시 반응합니다 (침묵도 반응입니다).
5. 게이지는 근거가 있을 때만 움직입니다. 한 턴에 크게 바뀌지 않습니다.

진행 방법
- 교사가 한 마디 할 때마다 장면을 만들고, 그 결과를 record_turn 으로 보고하세요.
- record_turn 응답에 교정 지시가 오면 **다음 턴에 반드시 반영**하세요.
  서버는 게이지 급변, 페르소나와 어긋나는 변화, 발언 쏠림을 감시합니다.
- 교사가 '/상태'라고 하면 get_state 로 게이지 표를 보여 주세요.
- 수업이 끝나면 end_session 으로 통계를 받아 리포트를 완성하세요.

이것은 시뮬레이션입니다. 실제 학생의 반응을 예측하거나 평가하는 데 쓸 수 없습니다."""


class RpcError(Exception):
    def __init__(self, code: int, message: str, data=None) -> None:
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


# ---------------------------------------------------------------------------
# 세션 (ChatGPT가 진행 중인 수업)
# ---------------------------------------------------------------------------


class McpSession:
    """서버가 기억하는 것 전부 — 상태·전사·발언 기록.

    로컬 웹판의 StageSession과 달리 LLM을 부르지 않는다. ChatGPT가 만든 장면을
    받아 적고 검사할 뿐이다.
    """

    def __init__(self, sid: str, user_id: str | None, classroom: dict, lesson: str) -> None:
        self.id = sid
        self.user_id = user_id
        self.classroom = classroom
        self.lesson = lesson
        self.turn = 0
        self.minute = 0
        self.phase = "도입"
        self.ended = False
        self.created_at = time.time()
        self.last_used = time.time()
        self.transcript: list[dict] = []
        self.speak_log: list[list[str]] = []      # 턴별로 드러난 학생 id
        self.incidents: list[str] = []
        self.personas = {s["id"]: s for s in classroom.get("students", [])}
        self.states = {sid_: {"comprehension": 60, "interest": 60, "focus": 70,
                              "emotion": "평온", "visible_action": ""}
                       for sid_ in self.personas}

    @property
    def roster(self) -> list[str]:
        return list(self.personas)

    def touch(self) -> None:
        self.last_used = time.time()

    def record(self, actor: str, kind: str, content: str) -> None:
        self.transcript.append({"turn": self.turn, "actor": actor,
                                "kind": kind, "content": content})

    def dump_state(self) -> dict:
        return {
            "version": 1,
            "id": self.id,
            "user_id": self.user_id,
            "classroom": self.classroom,
            "lesson": self.lesson,
            "turn": self.turn,
            "minute": self.minute,
            "phase": self.phase,
            "ended": self.ended,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "transcript": self.transcript,
            "speak_log": self.speak_log,
            "incidents": self.incidents,
            "states": self.states,
        }

    def load_state(self, data: dict) -> None:
        self.turn = int(data.get("turn") or 0)
        self.minute = int(data.get("minute") or 0)
        self.phase = str(data.get("phase") or "도입")
        self.ended = bool(data.get("ended"))
        self.created_at = float(data.get("created_at") or time.time())
        self.last_used = float(data.get("last_used") or time.time())
        self.transcript = list(data.get("transcript") or [])
        self.speak_log = list(data.get("speak_log") or [])
        self.incidents = list(data.get("incidents") or [])
        states = data.get("states") or {}
        if not isinstance(states, dict) or set(states) != set(self.personas):
            raise ValueError("학생 상태가 학급 명단과 맞지 않습니다.")
        self.states = {sid: dict(states[sid]) for sid in self.personas}

    @classmethod
    def from_state(cls, sid: str, user_id: str | None, data: dict) -> "McpSession":
        if data.get("version") != 1 or data.get("id") != sid:
            raise ValueError("지원하지 않는 MCP 수업 상태입니다.")
        if data.get("user_id") != user_id:
            raise ValueError("수업 주인이 일치하지 않습니다.")
        classroom = data.get("classroom")
        lesson = data.get("lesson")
        if not isinstance(classroom, dict) or not isinstance(lesson, str):
            raise ValueError("MCP 수업 상태가 올바르지 않습니다.")
        session = cls(sid, user_id, classroom, lesson[:200000])
        session.load_state(data)
        return session

    def state_table(self) -> list[dict]:
        return [{
            "id": sid,
            "name": self.personas[sid].get("name", sid),
            **self.states[sid],
        } for sid in self.roster]

    def stats(self) -> dict:
        """수업 분석용 통계 — 서버가 세어야 믿을 수 있는 것들."""
        counts: dict[str, int] = {sid: 0 for sid in self.roster}
        for turn in self.speak_log:
            for sid in turn:
                counts[sid] = counts.get(sid, 0) + 1
        spoken = sum(counts.values()) or 1
        silent = [self.personas[s].get("name", s) for s in self.roster if not counts[s]]
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
        return {
            "turns": self.turn,
            "minutes": self.minute,
            "speak_counts": {self.personas[s].get("name", s): n for s, n in counts.items()},
            "speak_share_top3": [{"name": self.personas[s].get("name", s),
                                  "share": round(n / spoken, 2)} for s, n in top],
            "never_spoke": silent,
            "incidents": self.incidents,
            "final_gauges": {
                self.personas[s].get("name", s): {
                    "이해도": self.states[s]["comprehension"],
                    "흥미": self.states[s]["interest"],
                    "집중": self.states[s]["focus"],
                } for s in self.roster},
        }


# ---------------------------------------------------------------------------
# 도구 정의 (기획서의 7종)
# ---------------------------------------------------------------------------

_STR = {"type": "string"}
_NUM = {"type": "integer"}

TOOLS = [
    {
        "name": "list_classrooms",
        "description": "사용 가능한 학급 목록을 돌려준다. 수업을 시작하기 전에 먼저 부른다.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_classroom",
        "description": ("새 학급을 만든다. 학급 JSON에는 class_name과 students 배열이 필요하고, "
                        "학생마다 id·name이 있어야 한다. 형식이 틀리면 어디가 문제인지 알려 준다."),
        "inputSchema": {
            "type": "object",
            "properties": {"classroom_json": dict(_STR, description="학급 JSON 문자열")},
            "required": ["classroom_json"],
        },
    },
    {
        "name": "start_session",
        "description": ("수업을 시작한다. 학급 전체 페르소나와 초기 게이지, 그리고 연기 지침을 "
                        "돌려준다. 지침을 반드시 읽고 그대로 따를 것."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "classroom_id": dict(_STR, description="list_classrooms가 준 id"),
                "lesson_text": dict(_STR, description="수업안 (자유 형식 텍스트)"),
            },
            "required": ["classroom_id", "lesson_text"],
        },
    },
    {
        "name": "record_turn",
        "description": ("교사의 한 마디와, 당신이 연기한 결과를 보고한다. 서버가 검사해 "
                        "교정 지시를 돌려주면 **다음 턴에 반드시 반영**할 것. "
                        "게이지 급변·페르소나 붕괴·발언 쏠림을 감시한다."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": _STR,
                "teacher_input": dict(_STR, description="교사가 한 말 또는 행동"),
                "kind": dict(_STR, description="say|point|board|activity|group|round|praise|warn|time_skip",
                             **{"default": "say"}),
                "events": {
                    "type": "array",
                    "description": "이번 턴에 겉으로 드러난 장면 (학생 1~3명)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "student_id": _STR,
                            "utterance": dict(_STR, description="발화. 침묵이면 빈 문자열"),
                            "action": dict(_STR, description="겉으로 보이는 행동"),
                        },
                        "required": ["student_id"],
                    },
                },
                "state_updates": {
                    "type": "object",
                    "description": ("학생 id → {comprehension, interest, focus, emotion, "
                                    "visible_action}. 바뀐 학생만 넣어도 된다"),
                    "additionalProperties": True,
                },
                "minute": dict(_NUM, description="수업 시작 후 경과 분 (누적)"),
                "phase": dict(_STR, description="도입|전개|활동|모둠활동|정리|종료"),
            },
            "required": ["session_id", "teacher_input"],
        },
    },
    {
        "name": "get_state",
        "description": "현재 게이지 표와 진행 상황. 교사가 '/상태'를 물으면 이걸 보여 준다.",
        "inputSchema": {"type": "object", "properties": {"session_id": _STR},
                        "required": ["session_id"]},
    },
    {
        "name": "trigger_incident",
        "description": ("돌발 상황 카드를 뽑는다. 카드 내용을 장면으로 풀어내고 "
                        "그 결과를 record_turn으로 보고할 것."),
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": _STR,
                           "card": dict(_STR, description="카드 이름 (비우면 무작위, 중복 없이)")},
            "required": ["session_id"],
        },
    },
    {
        "name": "end_session",
        "description": ("수업을 마치고 통계(발언 형평성·지목 분포·최종 게이지)와 리포트 틀을 "
                        "받는다. 이 통계를 근거로 리포트를 완성한 뒤 report_markdown을 "
                        "함께 보내면 서버에 저장된다."),
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": _STR,
                           "report_markdown": dict(_STR, description="완성한 리포트 (2차 호출 시)")},
            "required": ["session_id"],
        },
    },
]

_TOOL_TITLES = {
    "list_classrooms": "학급 목록 보기",
    "create_classroom": "학급 만들기",
    "start_session": "수업 시작하기",
    "record_turn": "수업 장면 기록하기",
    "get_state": "수업 상태 보기",
    "trigger_incident": "돌발 상황 만들기",
    "end_session": "수업 마치기",
}
_READ_ONLY_TOOLS = {"list_classrooms", "get_state"}
_OAUTH_SCHEMES = [{"type": "oauth2", "scopes": ["openid", "email"]}]

for _tool in TOOLS:
    _read_only = _tool["name"] in _READ_ONLY_TOOLS
    _tool.update({
        "title": _TOOL_TITLES[_tool["name"]],
        "outputSchema": {"type": "object", "additionalProperties": True},
        "securitySchemes": _OAUTH_SCHEMES,
        "annotations": {
            "readOnlyHint": _read_only,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": _read_only,
        },
        "_meta": {"securitySchemes": _OAUTH_SCHEMES},
    })

REPORT_TEMPLATE = """아래 틀로 교사용 수업 리포트를 완성해 주세요. 통계는 서버가
센 실제 값이니 그대로 인용하고, 해석과 제안을 더하세요.

# {class_name} — 수업 리포트

## 1. 수업 개요
(단원, 진행 시간, 국면 흐름)

## 2. 학생별 관찰
(학생마다: 최종 게이지, 이번 수업에서 드러난 모습, 근거가 된 장면)

## 3. 발언 기회 분석
(누구에게 쏠렸는가, 한 번도 드러나지 않은 학생은 누구인가)

## 4. 다음 수업 제안
(개별 지도가 필요한 학생, 수업 설계에서 바꿀 점)

---
※ 시뮬레이션 결과이며 실제 학생의 예측·평가·선발에 사용할 수 없습니다."""


# ---------------------------------------------------------------------------
# 도구 구현
# ---------------------------------------------------------------------------


class McpServer:
    """도구 호출을 처리한다. 저장소·인증은 web/server.py의 것을 그대로 빌려 쓴다."""

    def __init__(self, library, reports, incidents_mod, store=None) -> None:
        self.library = library
        self.reports = reports
        self.incidents = incidents_mod
        self.store = store
        self.sessions: dict[str, McpSession] = {}

    # -- 살림 -------------------------------------------------------------
    def _evict(self) -> None:
        now = time.time()
        for sid in [s for s, r in self.sessions.items() if now - r.last_used > MCP_TTL]:
            self.sessions.pop(sid, None)
        while len(self.sessions) >= MAX_MCP_SESSIONS:
            oldest = min(self.sessions, key=lambda s: self.sessions[s].last_used)
            self.sessions.pop(oldest, None)

    def _persist(self, session: McpSession, token: str | None) -> None:
        if self.store is None:
            return
        if getattr(self.store, "name", "none") == "none":
            raise RpcError(-32603, "수업 상태 저장소가 설정되지 않았습니다.")
        try:
            self.store.save(session.id, {
                "meta": {
                    "kind": "mcp",
                    "user_id": session.user_id,
                    "class_name": session.classroom.get("class_name", ""),
                },
                "saved_at": time.time(),
                "snapshot": session.dump_state(),
            }, token=token)
        except RpcError:
            raise
        except Exception as exc:
            log.warning("mcp session persist failed: %s (%s)", session.id[:8], exc)
            raise RpcError(-32603, "수업 상태를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc

    def _restore(self, sid: str, user_id: str | None,
                 token: str | None) -> McpSession | None:
        if self.store is None:
            return None
        try:
            payload = self.store.load_one(sid, token=token)
        except Exception as exc:
            log.warning("mcp session restore failed: %s (%s)", sid[:8], exc)
            raise RpcError(-32603, "수업 상태를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc
        if not isinstance(payload, dict):
            return None
        meta = payload.get("meta") or {}
        saved_at = float(payload.get("saved_at") or 0)
        if meta.get("kind") != "mcp" or meta.get("user_id") != user_id:
            return None
        if time.time() - saved_at > MCP_TTL:
            try:
                self.store.delete(sid, token=token)
            except Exception:
                pass
            return None
        try:
            session = McpSession.from_state(sid, user_id, payload.get("snapshot") or {})
        except (TypeError, ValueError):
            return None
        self.sessions[sid] = session
        log.info("mcp session restored: %s turn=%d", sid[:8], session.turn)
        return session

    def _session(self, args: dict, user_id: str | None,
                 token: str | None) -> McpSession:
        sid = str(args.get("session_id") or "")
        s = self.sessions.get(sid) or self._restore(sid, user_id, token)
        if s is None:
            raise RpcError(-32602, "수업을 찾을 수 없습니다. start_session으로 새로 시작해 주세요.")
        if s.user_id != user_id:
            raise RpcError(-32602, "수업을 찾을 수 없습니다. start_session으로 새로 시작해 주세요.")
        if s.ended:
            raise RpcError(-32602, "이미 끝난 수업입니다.")
        s.touch()
        return s

    # -- 도구 -------------------------------------------------------------
    def list_classrooms(self, args, user_id, token) -> dict:
        rows = self.library.list(user_id, token)
        return {"classrooms": rows,
                "hint": "start_session에 이 id를 그대로 넘기세요." if rows
                        else "학급이 없습니다. create_classroom으로 먼저 만드세요."}

    def create_classroom(self, args, user_id, token) -> dict:
        from .classrooms import ClassroomError

        try:
            made = self.library.create(user_id, args.get("classroom_json") or "", token)
        except (ClassroomError, ValueError) as exc:
            raise RpcError(-32602, str(exc)) from exc
        return {"created": made,
                "note": "실제 학생의 실명·진단명·가정사를 넣지 마세요. 가상 페르소나만 사용합니다."}

    def start_session(self, args, user_id, token) -> dict:
        from .classrooms import ClassroomError

        lesson = (args.get("lesson_text") or "").strip()
        if not lesson:
            raise RpcError(-32602, "수업안 텍스트(lesson_text)가 필요합니다.")
        try:
            _, data = self.library.resolve(user_id, str(args.get("classroom_id") or ""), token)
        except (ClassroomError, ValueError) as exc:
            raise RpcError(-32602, str(exc)) from exc

        self._evict()
        sid = "mcp_" + uuid.uuid4().hex[:12]
        s = McpSession(sid, user_id, data, lesson[:200000])
        self.sessions[sid] = s
        try:
            self._persist(s, token)
        except RpcError:
            self.sessions.pop(sid, None)
            raise
        log.info("mcp session started: %s class=%s students=%d",
                 sid[:8], data.get("class_name", ""), len(s.roster))
        return {
            "session_id": sid,
            "class_name": data.get("class_name", ""),
            "students": [{"id": sid_, **{k: v for k, v in p.items() if k != "id"}}
                         for sid_, p in s.personas.items()],
            "initial_states": s.state_table(),
            "acting_guide": ACTING_GUIDE,
            "next": "교사의 첫 마디를 기다렸다가, 장면을 만들고 record_turn으로 보고하세요.",
        }

    def record_turn(self, args, user_id, token) -> dict:
        s = self._session(args, user_id, token)
        before = s.dump_state()
        teacher = (args.get("teacher_input") or "").strip()
        if not teacher:
            raise RpcError(-32602, "교사 입력(teacher_input)이 비어 있습니다.")
        kind = str(args.get("kind") or "say")

        s.turn += 1
        s.record("교사", "teacher_say", teacher[:2000])

        # ── 심판 ──────────────────────────────────────────────
        prev = {k: dict(v) for k, v in s.states.items()}
        claimed = args.get("state_updates")
        fixed, notes = judge_gauges(prev, claimed if isinstance(claimed, dict) else {})
        s.minute, tnotes = judge_time(s.minute, args.get("minute", s.minute), kind)
        s.phase, pnotes = judge_phase(s.phase, args.get("phase"))
        s.states = fixed

        spoke: list[str] = []
        for ev in (args.get("events") or [])[:8]:
            if not isinstance(ev, dict):
                continue
            sid_ = str(ev.get("student_id") or "")
            if sid_ not in s.personas:
                notes.append(f"이 학급에 없는 학생의 장면입니다: {sid_} — 기록하지 않았습니다.")
                continue
            spoke.append(sid_)
            if (ev.get("utterance") or "").strip():
                s.record(sid_, "student_say", str(ev["utterance"])[:1000])
            if (ev.get("action") or "").strip():
                s.record(sid_, "student_action", str(ev["action"])[:500])
        s.speak_log.append(spoke)

        notes += tnotes + pnotes
        notes += judge_persona(s.personas, prev, s.states, s.minute)
        notes += judge_equity(s.speak_log, s.roster)

        try:
            self._persist(s, token)
        except RpcError:
            s.load_state(before)
            raise

        return {
            "turn": s.turn,
            "minute": s.minute,
            "phase": s.phase,
            "states": s.state_table(),
            # 이 필드가 커스텀 GPT와의 결정적 차이다. 비어 있으면 잘 가고 있다는 뜻.
            "corrections": notes,
            "next": ("교정 지시를 다음 턴에 반영하세요." if notes
                     else "좋습니다. 교사의 다음 마디를 기다리세요."),
        }

    def get_state(self, args, user_id, token) -> dict:
        s = self._session(args, user_id, token)
        return {"turn": s.turn, "minute": s.minute, "phase": s.phase,
                "class_name": s.classroom.get("class_name", ""),
                "states": s.state_table(),
                "incidents_used": s.incidents,
                "note": "이 표는 교사만 봅니다. 학생은 자기 게이지를 모릅니다."}

    def trigger_incident(self, args, user_id, token) -> dict:
        s = self._session(args, user_id, token)
        before = s.dump_state()
        want = (args.get("card") or "").strip() or None
        try:
            card = self.incidents.draw(want, exclude=s.incidents)
        except KeyError as exc:
            raise RpcError(-32602, str(exc)) from exc
        s.incidents.append(card.name)
        s.record("무대", "narration", f"[돌발] {card.name}: {card.description}")
        try:
            self._persist(s, token)
        except RpcError:
            s.load_state(before)
            raise
        return {"card": card.name, "description": card.description,
                "next": "이 상황을 장면으로 풀어내고 record_turn으로 보고하세요."}

    def end_session(self, args, user_id, token) -> dict:
        sid = str(args.get("session_id") or "")
        s = self._session(args, user_id, token)
        report = (args.get("report_markdown") or "").strip()
        stats = s.stats()

        if not report:
            # 1차 호출 — 통계와 틀을 주고 리포트를 쓰게 한다
            s.touch()
            return {
                "stats": stats,
                "report_template": REPORT_TEMPLATE.format(
                    class_name=s.classroom.get("class_name", "학급")),
                "next": ("이 통계를 근거로 리포트를 완성한 뒤, end_session을 "
                         "report_markdown과 함께 한 번 더 부르면 저장됩니다."),
            }

        # 2차 호출 — 완성된 리포트를 보관한다
        s.ended = True
        try:
            self._persist(s, token)
        except RpcError:
            s.ended = False
            raise
        base = f"mcp_{time.strftime('%Y%m%d_%H%M%S')}_{sid[:8]}"
        rid = None
        try:
            rid = self.reports.save({
                "user_id": user_id or "", "session_id": sid,
                "class_name": s.classroom.get("class_name", ""),
                "lesson_title": (s.lesson.strip().splitlines() or ["수업"])[0].lstrip("# ")[:200],
                "turns": s.turn, "minutes": s.minute,
            }, report, s.transcript, base, token)
        except Exception:
            log.exception("mcp report save failed: %s", sid[:8])
        self.sessions.pop(sid, None)
        if self.store is not None:
            try:
                self.store.delete(sid, token=token)
            except Exception as exc:
                log.warning("mcp session delete failed: %s (%s)", sid[:8], exc)
        log.info("mcp session ended: %s turns=%d saved=%s", sid[:8], s.turn, bool(rid))
        return {"saved": bool(rid), "report_id": rid, "stats": stats,
                "next": "수업이 저장되었습니다. 웹 화면의 [지난 수업 기록]에서도 볼 수 있습니다."}

    # -- 디스패치 ---------------------------------------------------------
    HANDLERS = ("list_classrooms", "create_classroom", "start_session",
                "record_turn", "get_state", "trigger_incident", "end_session")

    def call(self, name: str, args: dict, user_id: str | None, token: str | None) -> dict:
        if name not in self.HANDLERS:
            raise RpcError(-32602, f"알 수 없는 도구입니다: {name}")
        return getattr(self, name)(args or {}, user_id, token)


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 (MCP streamable HTTP)
# ---------------------------------------------------------------------------


def _result(rid, payload) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": payload}


def _error(rid, code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": err}


def _content(payload: dict) -> dict:
    """도구 결과를 MCP content 규격으로 감싼다.

    구조화 데이터는 structuredContent로, 사람이(그리고 모델이) 읽을 텍스트는
    text로 함께 준다. 클라이언트마다 읽는 쪽이 달라 둘 다 채운다.
    """
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "structuredContent": payload,
        "isError": False,
    }


def handle(body: dict, server: McpServer, user_id: str | None, token: str | None):
    """JSON-RPC 요청 하나를 처리한다. 알림(id 없음)이면 None을 돌려준다."""
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        return _error(None, -32600, "jsonrpc 2.0 요청이 아닙니다.")
    method = body.get("method")
    rid = body.get("id")
    params = body.get("params") or {}

    # 알림 — 응답하지 않는다 (initialized, cancelled 등)
    if rid is None:
        return None

    if method == "initialize":
        return _result(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": ACTING_GUIDE,
        })
    if method == "ping":
        return _result(rid, {})
    if method == "tools/list":
        return _result(rid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            return _result(rid, _content(server.call(name, args, user_id, token)))
        except RpcError as exc:
            # 도구 오류는 프로토콜 오류가 아니라 "결과"로 돌려줘야 모델이 읽고 고친다
            return _result(rid, {
                "content": [{"type": "text", "text": exc.message}],
                "structuredContent": {"error": exc.message},
                "isError": True,
            })
        except Exception:
            log.exception("mcp tool failed: %s", name)
            return _error(rid, -32603, "도구 실행 중 서버 오류가 발생했습니다.")
    if method in ("resources/list", "prompts/list"):
        return _result(rid, {"resources": [], "prompts": []})
    return _error(rid, -32601, f"지원하지 않는 메서드입니다: {method}")
