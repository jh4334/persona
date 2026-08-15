"""StageSession — 교실 무대의 턴 루프 오케스트레이션.

교사 입력 파싱 → 감독 1회 호출 → 상태 반영 → 선정된 학생만 순차 발화 →
전사 기록 → TurnResult 반환. `/상태`는 LLM을 호출하지 않는다.
"""

from __future__ import annotations

import random
import re
from datetime import datetime

from ..personas import Classroom, Student
from . import analysis, director, incidents, student_agent
from .backend import pack_payload
from .state import PHASES, ClassState, StudentState, TurnEvent, TurnResult, clamp
from .transcript import Transcript, TranscriptEntry

# 전사가 이 길이를 넘으면 앞부분을 요약으로 접는다.
FOLD_THRESHOLD = 30
FOLD_KEEP = 20

def _safe_int(value, fallback: int) -> int:
    """감독(LLM) 출력의 숫자 필드를 안전하게 정수로 바꾼다. '3분' 같은 문자열도 허용."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        m = re.search(r"-?\d+", str(value)) if value is not None else None
        return int(m.group()) if m else fallback


_HELP = (
    "사용 가능한 입력:\n"
    "  (일반 텍스트)          전체 발화\n"
    "  @이름 텍스트           특정 학생 지목 (@S04 도 가능)\n"
    "  /판서 텍스트           판서·자료 제시\n"
    "  /활동 지시문           활동 국면 전환\n"
    "  /모둠 4인 | /모둠 S01,S04/S02,S05   모둠 편성\n"
    "  /모둠활동 지시문       모둠 내 대화 1라운드\n"
    "  /순회 이름 [말걸기]    1:1 순회 지도\n"
    "  /칭찬 이름 [텍스트]    개별 피드백\n"
    "  /주의 이름 [텍스트]    개별 피드백\n"
    "  /시간 10분             시간 경과\n"
    "  /돌발 [카드명]         돌발 상황 (카드: " + ", ".join(incidents.names()) + ")\n"
    "  /상태                  게이지 표 (LLM 호출 없음)\n"
    "  /종료                  수업 종료 + 사후 리포트"
)


class StageSession:
    def __init__(
        self,
        classroom: Classroom,
        lesson_text: str,
        backend,
        seed: int | None = None,
    ) -> None:
        self.classroom = classroom
        self.lesson_text = lesson_text
        self.backend = backend
        self.rng = random.Random(20260813 if seed is None else seed)

        self.students: dict[str, Student] = {s.id: s for s in classroom.students}
        self.state = ClassState(students={s.id: StudentState() for s in classroom.students})
        self.transcript = Transcript(names={s.id: s.name for s in classroom.students})
        self._report: str | None = None
        self._system_prefix = self._build_system_prefix()

    # ------------------------------------------------------------------
    # 시스템 프롬프트 (프롬프트 캐싱 프리픽스)
    # ------------------------------------------------------------------

    def _build_system_prefix(self) -> list[dict]:
        head = (
            "당신은 초등 교실 실시간 수업 시뮬레이션의 구성원입니다. "
            f"대상 학급: {self.classroom.class_name} ({self.classroom.grade}, "
            f"학생 {len(self.classroom.students)}명).\n"
            "이것은 가상 페르소나 기반 시뮬레이션이며 실제 학생을 예측하는 것이 아닙니다."
        )
        roster = "\n\n".join(s.to_prompt_block() for s in self.classroom.students)
        corpus = (
            f"<학급_페르소나>\n{roster}\n</학급_페르소나>\n\n"
            f"<수업_자료>\n{self.lesson_text}\n</수업_자료>"
        )
        block: dict = {"type": "text", "text": corpus}
        # anthropic 백엔드에서만 캐시 지시자를 붙인다(학급+수업자료는 매 호출 동일).
        if getattr(self.backend, "supports_cache", False):
            block["cache_control"] = {"type": "ephemeral"}
        return [{"type": "text", "text": head}, block]

    def _director_system(self) -> list[dict]:
        return list(self._system_prefix) + [{"type": "text", "text": director.DIRECTOR_SYSTEM}]

    # ------------------------------------------------------------------
    # 스냅샷 — 서버 재시작 후에도 수업을 이어갈 수 있게 상태 전체를 내보내고/되살린다
    # ------------------------------------------------------------------

    def dump_state(self) -> dict:
        return {
            "state": {
                "turn": self.state.turn,
                "minute": self.state.minute,
                "phase": self.state.phase,
                "ended": self.state.ended,
                "groups": [list(g) for g in self.state.groups],
                "incidents": list(self.state.incidents),
                "students": {sid: st.to_dict() for sid, st in self.state.students.items()},
            },
            "transcript": self.transcript.to_json(),
            "report": self._report,
        }

    def load_state(self, snap: dict) -> None:
        """dump_state() 결과를 되살린다. 값은 감독 출력과 같은 기준으로 방어한다."""
        s = snap.get("state") or {}
        self.state.turn = max(0, _safe_int(s.get("turn"), 0))
        self.state.minute = max(0, _safe_int(s.get("minute"), 0))
        phase = str(s.get("phase") or "")
        if phase in PHASES:
            self.state.phase = phase
        self.state.ended = bool(s.get("ended"))
        self.state.groups = [
            [str(x) for x in g] for g in (s.get("groups") or []) if isinstance(g, list)
        ]
        self.state.incidents = [str(x) for x in (s.get("incidents") or [])]
        for sid, d in (s.get("students") or {}).items():
            st = self.state.students.get(sid)
            if st is None or not isinstance(d, dict):
                continue
            st.comprehension = clamp(_safe_int(d.get("comprehension"), st.comprehension))
            st.interest = clamp(_safe_int(d.get("interest"), st.interest))
            st.focus = clamp(_safe_int(d.get("focus"), st.focus))
            st.emotion = str(d.get("emotion") or st.emotion)[:12]
            st.visible_action = str(d.get("visible_action") or "")[:80]
        rows = snap.get("transcript")
        if isinstance(rows, list):
            self.transcript.entries = [
                TranscriptEntry.from_dict(d) for d in rows if isinstance(d, dict)
            ]
        rep = snap.get("report")
        self._report = rep if isinstance(rep, str) else None

    # ------------------------------------------------------------------
    # 입력 파싱
    # ------------------------------------------------------------------

    def _resolve(self, token: str) -> str | None:
        """이름 또는 ID를 학생 ID로 해석한다."""
        key = (token or "").strip().strip(",")
        if not key:
            return None
        upper = key.upper()
        if upper in self.students:
            return upper
        for sid, s in self.students.items():
            if s.name == key:
                return sid
        for sid, s in self.students.items():
            if s.name.startswith(key) or key.startswith(s.name):
                return sid
        return None

    def _parse(self, raw: str) -> dict:
        text = (raw or "").strip()
        if not text:
            return {"kind": "noop", "message": "입력이 비어 있습니다.\n\n" + _HELP}

        if text.startswith("@"):
            head, _, rest = text[1:].partition(" ")
            sid = self._resolve(head)
            if not sid:
                return {"kind": "error", "message": f"'{head}' 학생을 찾을 수 없습니다."}
            return {"kind": "nominate", "target": sid, "text": rest.strip()}

        if not text.startswith("/"):
            return {"kind": "teacher_say", "text": text}

        cmd, _, rest = text[1:].partition(" ")
        rest = rest.strip()
        cmd = cmd.strip()

        if cmd == "상태":
            return {"kind": "status"}
        if cmd == "종료":
            return {"kind": "end"}
        if cmd == "도움말":
            return {"kind": "error", "message": _HELP}
        if cmd == "판서":
            if not rest:
                return {"kind": "error", "message": "판서 내용을 함께 적어 주세요. 예: /판서 3 : 5 → 3/5 = 0.6"}
            return {"kind": "board", "text": rest}
        if cmd == "활동":
            if not rest:
                return {"kind": "error", "message": "활동 지시문을 함께 적어 주세요."}
            return {"kind": "activity", "text": rest}
        if cmd == "모둠":
            return self._parse_group_form(rest)
        if cmd == "모둠활동":
            return {"kind": "group_work", "text": rest or "모둠별로 과제를 해결해 보세요."}
        if cmd in ("순회", "칭찬", "주의"):
            kind = {"순회": "rounds", "칭찬": "praise", "주의": "warn"}[cmd]
            name, _, tail = rest.partition(" ")
            sid = self._resolve(name)
            if not sid:
                return {"kind": "error", "message": f"'{name or '(이름 없음)'}' 학생을 찾을 수 없습니다."}
            return {"kind": kind, "target": sid, "text": tail.strip()}
        if cmd == "시간":
            m = re.search(r"(\d+)", rest)
            if not m:
                return {"kind": "error", "message": "시간을 분 단위로 적어 주세요. 예: /시간 10분"}
            return {"kind": "time_skip", "minutes": max(1, int(m.group(1))), "text": rest}
        if cmd == "돌발":
            try:
                card = incidents.draw(rest or None, rng=self.rng)
            except KeyError as e:
                return {"kind": "error", "message": str(e)}
            return {"kind": "incident", "incident": card.name, "text": card.description}

        return {"kind": "error", "message": f"알 수 없는 명령입니다: /{cmd}\n\n{_HELP}"}

    def _parse_group_form(self, rest: str) -> dict:
        if not rest:
            return {"kind": "error", "message": "모둠 편성 방식을 적어 주세요. 예: /모둠 4인 또는 /모둠 S01,S04/S02,S05"}
        if "/" in rest or "," in rest:
            groups: list[list[str]] = []
            for chunk in rest.split("/"):
                members = []
                for token in chunk.split(","):
                    sid = self._resolve(token)
                    if not sid:
                        return {"kind": "error", "message": f"'{token.strip()}' 학생을 찾을 수 없습니다."}
                    members.append(sid)
                if members:
                    groups.append(members)
            if not groups:
                return {"kind": "error", "message": "모둠 구성을 해석하지 못했습니다."}
            return {"kind": "group_form", "groups": groups, "text": rest}
        m = re.search(r"(\d+)", rest)
        if not m:
            return {"kind": "error", "message": "모둠 인원을 숫자로 적어 주세요. 예: /모둠 4인"}
        return {"kind": "group_form", "size": max(2, int(m.group(1))), "text": rest}

    def _auto_groups(self, size: int) -> list[list[str]]:
        ids = [s.id for s in self.classroom.students]
        groups = [ids[i:i + size] for i in range(0, len(ids), size)]
        if len(groups) > 1 and len(groups[-1]) == 1:  # 1인 모둠은 앞 모둠에 붙인다
            groups[-2].extend(groups.pop())
        return groups

    # ------------------------------------------------------------------
    # 턴 루프
    # ------------------------------------------------------------------

    def turn(self, teacher_input: str) -> TurnResult:
        if self.state.ended:
            return self._result([TurnEvent("무대", "system", "수업이 이미 종료되었습니다.")], ended=True)

        action = self._parse(teacher_input)
        kind = action["kind"]

        if kind in ("error", "noop"):
            return self._result([TurnEvent("무대", "system", action.get("message", _HELP))])
        if kind == "status":
            return self._result([TurnEvent("무대", "system", self.status_table())])
        if kind == "end":
            report = self.end()
            return TurnResult(
                turn=self.state.turn,
                events=[TurnEvent("무대", "system", "수업을 종료했습니다. 사후 리포트를 생성했습니다.")],
                states=dict(self.state.students),
                minute=self.state.minute,
                phase=self.state.phase,
                ended=True,
                report_markdown=report,
            )

        self.state.turn += 1
        events: list[TurnEvent] = []

        # 모둠 편성은 상태(그룹)를 먼저 확정한다.
        if kind == "group_form":
            groups = action.get("groups") or self._auto_groups(int(action.get("size", 4)))
            self.state.groups = groups
            action["groups"] = groups
        elif kind == "group_work" and not self.state.groups:
            self.state.groups = self._auto_groups(4)
            events.append(TurnEvent("무대", "system", "모둠이 편성되어 있지 않아 4인 모둠으로 자동 편성했습니다."))

        events.extend(self._record_teacher_action(action))

        # ---- 감독 1회 호출 ----
        result = self._call_director(action)
        if not isinstance(result, dict):
            events.append(TurnEvent("무대", "system", "감독 호출에 실패해 이번 턴은 상태를 유지합니다."))
            return self._result(events)

        # 감독 출력은 LLM 산출물이므로 형·범위를 모두 방어한다.
        # 시간은 /시간 명령 외에는 한 턴에 크게 흐를 이유가 없다.
        cap = max(15, _safe_int(action.get("minutes"), 0)) if kind == "time_skip" else 15
        self.state.minute += min(cap, max(0, _safe_int(result.get("minute_delta", 1), 1)))
        phase = str(result.get("phase") or "").strip()
        if phase in PHASES:
            self.state.phase = phase
        self._apply_updates(result.get("updates"))

        narration = str(result.get("narration") or "").strip()
        if narration:
            events.append(TurnEvent("무대", "narration", narration))
            self._record("무대", "narration", narration)

        # ---- 선정된 학생만 순차 발화 (학생 수가 적어 병렬 불필요) ----
        if kind == "group_work":
            events.extend(self._run_group_talk(action.get("text", "")))
        else:
            speakers = result.get("speakers")
            events.extend(self._run_speakers(speakers if isinstance(speakers, list) else [], action))

        self._maybe_fold()
        return self._result(events)

    # -- 감독 --

    def _call_director(self, action: dict) -> dict | None:
        payload_students = [
            director.student_payload(self.students[sid], st)
            for sid, st in self.state.students.items()
        ]
        try:
            return director.direct(
                self.backend,
                system=self._director_system(),
                action=self._director_action(action),
                students=payload_students,
                recent_transcript=self.transcript.render(self.transcript.recent(12)),
                turn=self.state.turn,
                minute=self.state.minute,
                phase=self.state.phase,
                groups=self.state.groups,
            )
        except Exception:  # noqa: BLE001 — 한 턴의 실패가 세션을 끝내지 않도록
            return None

    @staticmethod
    def _director_action(action: dict) -> dict:
        out = {"kind": action["kind"], "text": action.get("text", "")}
        for key in ("target", "minutes", "incident", "groups"):
            if key in action:
                out[key] = action[key]
        return out

    def _apply_updates(self, updates) -> None:
        if not isinstance(updates, list):
            return
        for u in updates:
            if not isinstance(u, dict):
                continue
            st = self.state.students.get(u.get("id"))
            if st is None:
                continue
            st.comprehension = clamp(_safe_int(u.get("comprehension", st.comprehension), st.comprehension))
            st.interest = clamp(_safe_int(u.get("interest", st.interest), st.interest))
            st.focus = clamp(_safe_int(u.get("focus", st.focus), st.focus))
            emotion = str(u.get("emotion") or "").strip()
            if emotion:
                st.emotion = emotion[:12]          # 상태표·캔버스 표시가 깨지지 않게 자른다
            st.visible_action = str(u.get("visible_action") or "").strip()[:80]

    # -- 교사 행동 기록 --

    def _record(self, actor: str, kind: str, content: str, meta: dict | None = None) -> None:
        self.transcript.add(
            turn=self.state.turn,
            minute=self.state.minute,
            actor=actor,
            kind=kind,
            content=content,
            focus_map=self.state.focus_map(),
            meta=meta,
        )

    def _record_teacher_action(self, action: dict) -> list[TurnEvent]:
        kind = action["kind"]
        text = action.get("text", "")
        target = action.get("target")
        name = self.students[target].name if target else ""
        events: list[TurnEvent] = []

        def emit(actor: str, ekind: str, content: str, meta: dict | None = None) -> None:
            events.append(TurnEvent(actor, ekind, content))
            self._record(actor, ekind, content, meta)

        if kind == "teacher_say":
            emit("교사", "teacher_say", text)
        elif kind == "nominate":
            said = f"{name}, {text}" if text else f"{name}, 말해 볼까?"
            emit("교사", "teacher_say", said, {"target": target, "action": "nominate"})
        elif kind == "board":
            emit("교사", "teacher_action", f"칠판에 적는다 — {text}")
        elif kind == "activity":
            emit("교사", "teacher_action", f"활동을 지시한다 — {text}")
            emit("교사", "teacher_say", text)
        elif kind == "group_form":
            desc = " / ".join(
                "·".join(self.students[m].name for m in g) for g in action.get("groups", [])
            )
            emit("교사", "teacher_action", f"모둠을 편성한다 — {desc}")
        elif kind == "group_work":
            emit("교사", "teacher_action", f"모둠 활동을 지시한다 — {text}")
            emit("교사", "teacher_say", text)
        elif kind == "rounds":
            emit("교사", "teacher_action", f"{name}의 자리로 가서 공책을 들여다본다",
                 {"target": target, "action": "rounds"})
            if text:
                emit("교사", "teacher_say", f"{name}, {text}", {"target": target, "action": "rounds"})
        elif kind == "praise":
            emit("교사", "teacher_say", f"{name}, {text or '아주 잘했어요.'}",
                 {"target": target, "action": "praise"})
        elif kind == "warn":
            emit("교사", "teacher_say", f"{name}, {text or '지금은 수업에 집중하자.'}",
                 {"target": target, "action": "warn"})
        elif kind == "time_skip":
            emit("교사", "teacher_action", f"{action.get('minutes', 5)}분간 활동 시간을 준다")
        elif kind == "incident":
            self.state.incidents.append(action.get("incident", ""))
            emit("무대", "narration", f"[돌발: {action.get('incident','')}] {text}")
        return events

    # -- 학생 발화 --

    def _run_speakers(self, speakers: list[dict], action: dict) -> list[TurnEvent]:
        events: list[TurnEvent] = []
        seen: set[str] = set()
        for spec in speakers[:3]:
            if not isinstance(spec, dict):
                continue
            sid = spec.get("id")
            if sid not in self.students or sid in seen:
                continue
            seen.add(sid)
            student = self.students[sid]
            st = self.state.students[sid]
            try:
                spoken = student_agent.speak(
                    self.backend,
                    system_prefix=self._system_prefix,
                    student=student,
                    state=st,
                    cue=str(spec.get("cue") or "그 학생답게 반응해라."),
                    perspective=self.transcript.perspective_for(sid),
                    nominated=(action.get("target") == sid),
                    minute=self.state.minute,
                    phase=self.state.phase,
                )
            except Exception as e:  # noqa: BLE001
                events.append(TurnEvent("무대", "system", f"{student.name} 발화 생성 실패: {e}"))
                continue
            events.extend(self._emit_student(sid, spoken))
        return events

    def _emit_student(self, sid: str, spoken: dict) -> list[TurnEvent]:
        events: list[TurnEvent] = []
        if not isinstance(spoken, dict):
            spoken = {}
        utterance = str(spoken.get("utterance") or "").strip()
        act = str(spoken.get("action") or "").strip()
        if utterance:
            events.append(TurnEvent(sid, "student_say", utterance))
            self._record(sid, "student_say", utterance)
        if act:
            events.append(TurnEvent(sid, "student_action", act))
            self._record(sid, "student_action", act)
        if not utterance and not act:
            silent = "……(아무 말도 하지 않는다)"
            events.append(TurnEvent(sid, "student_action", silent))
            self._record(sid, "student_action", silent)
        return events

    def _run_group_talk(self, instruction: str) -> list[TurnEvent]:
        events: list[TurnEvent] = []
        for group in self.state.groups:
            members = [(self.students[m], self.state.students[m]) for m in group if m in self.students]
            if not members:
                continue
            label = "·".join(s.name for s, _ in members)
            try:
                lines = student_agent.group_talk(
                    self.backend,
                    system_prefix=self._system_prefix,
                    members=members,
                    instruction=instruction,
                    perspective=self.transcript.render(self.transcript.recent(8)),
                    minute=self.state.minute,
                    phase=self.state.phase,
                )
            except Exception as e:  # noqa: BLE001
                events.append(TurnEvent("무대", "system", f"[{label}] 모둠 대화 생성 실패: {e}"))
                continue
            events.append(TurnEvent("무대", "narration", f"[{label} 모둠]"))
            self._record("무대", "narration", f"[{label} 모둠] 대화가 오간다")
            for line in lines:
                events.extend(self._emit_student(line["id"], line))
        return events

    # -- 전사 접기 --

    def _maybe_fold(self) -> None:
        if len(self.transcript) <= FOLD_THRESHOLD:
            return
        cut = len(self.transcript) - FOLD_KEEP
        head = self.transcript.entries[:cut]
        raw = self.transcript.render(head)
        try:
            summary = self.backend.complete_text(
                system="수업 전사의 앞부분을 3~5문장으로 요약하세요. 교사가 다룬 내용과 "
                       "학생 반응의 흐름만 남기고 세부 대사는 생략하세요.",
                messages=[{"role": "user", "content": pack_payload({"task": "summary", "text": raw})}],
                max_tokens=1024,
                model_role="director",
            ).strip()
        except Exception:  # noqa: BLE001 — 요약 실패 시 단순 절단
            summary = raw[:400] + " …(이하 생략)"
        self.transcript.fold(cut, summary or raw[:400])

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------

    def _result(self, events: list[TurnEvent], *, ended: bool = False) -> TurnResult:
        return TurnResult(
            turn=self.state.turn,
            events=events,
            states=dict(self.state.students),
            minute=self.state.minute,
            phase=self.state.phase,
            ended=ended or self.state.ended,
        )

    def state_snapshot(self) -> dict:
        return {
            "turn": self.state.turn,
            "minute": self.state.minute,
            "phase": self.state.phase,
            "ended": self.state.ended,
            "class_name": self.classroom.class_name,
            "students": [
                {
                    "id": s.id,
                    "name": s.name,
                    "achievement_level": s.achievement_level,
                    **self.state.students[s.id].to_dict(),
                }
                for s in self.classroom.students
            ],
        }

    def transcript_json(self) -> list[dict]:
        return self.transcript.to_json()

    def status_table(self) -> str:
        """게이지 표 (LLM 호출 없음)."""
        rows = [
            f"[{self.state.minute}분 · {self.state.phase} · {self.state.turn}턴] 학생 상태",
            "이름       수준  이해 흥미 집중  정서    모습",
        ]
        for s in self.classroom.students:
            st = self.state.students[s.id]
            rows.append(
                f"{s.name:<9} {s.achievement_level:<4} "
                f"{st.comprehension:>4} {st.interest:>4} {st.focus:>4}  "
                f"{st.emotion:<6}  {st.visible_action}"
            )
        if self.state.groups:
            rows.append("모둠: " + " / ".join(
                "·".join(self.students[m].name for m in g) for g in self.state.groups
            ))
        return "\n".join(rows)

    # ------------------------------------------------------------------
    # 종료 리포트
    # ------------------------------------------------------------------

    def lesson_title(self) -> str:
        first = (self.lesson_text or "").strip().splitlines()
        return first[0].lstrip("# ").strip() if first else "제목 없음"

    def end(self) -> str:
        if self.state.ended and self._report:
            return self._report

        self.state.ended = True
        self.state.phase = "종료"
        self._record("무대", "system", "수업 종료")

        lines: list[str] = []
        lines.append("# 교실 무대 수업 기록 리포트")
        lines.append("")
        lines.append(f"- **학급**: {self.classroom.class_name} ({self.classroom.grade}, "
                     f"{len(self.classroom.students)}명)")
        lines.append(f"- **학습단원**: {self.lesson_title()}")
        lines.append(f"- **진행**: {self.state.turn}턴 / 수업 경과 {self.state.minute}분")
        if self.state.incidents:
            lines.append(f"- **돌발 상황**: {', '.join(self.state.incidents)}")
        lines.append(f"- **생성 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        lines.append(
            "> ⚠️ 이 리포트는 AI가 가상 페르소나를 기반으로 진행한 **수업 시뮬레이션** 기록입니다. "
            "실제 학생의 반응을 보장하지 않으며, 평가·선발 목적으로 사용할 수 없습니다."
        )
        lines.append("")

        lines.append("## 학생별 최종 상태")
        lines.append("")
        lines.append("| 학생 | 성취수준 | 이해도 | 흥미 | 집중 | 정서 | 마지막 모습 |")
        lines.append("|---|---|---|---|---|---|---|")
        for s in self.classroom.students:
            st = self.state.students[s.id]
            lines.append(
                f"| {s.name} | {s.achievement_level} | {st.comprehension} | {st.interest} "
                f"| {st.focus} | {st.emotion} | {st.visible_action or '—'} |"
            )
        lines.append("")

        low_c = [s.name for s in self.classroom.students if self.state.students[s.id].comprehension < 45]
        low_f = [s.name for s in self.classroom.students if self.state.students[s.id].focus < 40]
        if low_c:
            lines.append(f"- 이해도 우려 학생: **{', '.join(low_c)}**")
        if low_f:
            lines.append(f"- 수업 종료 시점 집중이 낮은 학생: **{', '.join(low_f)}**")
        if low_c or low_f:
            lines.append("")

        lines.append(analysis.analyze(self.transcript_json(), self.classroom, self.backend))
        lines.append("")

        lines.append("## 수업 전사")
        lines.append("")
        lines.append("```")
        lines.append(self.transcript.render())
        lines.append("```")
        lines.append("")

        self._report = "\n".join(lines)
        return self._report
