"""개발용 가짜 무대 세션 (FakeSession).

엔진(`src/classroom_sim/stage/`)이 아직 없거나 미완성일 때 프론트엔드를 끝까지
개발·테스트하기 위한 하드코딩 구현이다. `docs/specs/stage_contract.md`의
StageSession 시그니처, state_snapshot JSON 형태, TurnResult 직렬화 형태를
그대로 흉내낸다.

- LLM을 전혀 호출하지 않는다 (결정적 난수 = seed 고정 시 항상 같은 결과).
- 교사 입력 1회당 2~3개의 가짜 학생 이벤트와 게이지 변화를 돌려준다.

환경변수 `CLASSROOM_SIM_FAKE=1` 일 때 server.py가 엔진 대신 이것을 사용한다.
엔진이 완성되면 이 파일은 개발용으로만 남는다.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from ..personas import Classroom, Student

# ---------------------------------------------------------------------------
# 계약서(stage/state.py)와 동일한 데이터 모델 — dataclasses.asdict로 직렬화된다.
# ---------------------------------------------------------------------------


@dataclass
class StudentState:
    comprehension: int = 60  # 이해도 0~100
    interest: int = 60  # 흥미 0~100
    focus: int = 70  # 집중 0~100
    emotion: str = "평온"  # 평온|들뜸|위축|불안|지루함|몰입 등
    visible_action: str = ""  # 현재 겉으로 보이는 모습


@dataclass
class TurnEvent:
    actor: str  # "교사" | 학생 id | "무대"
    kind: str  # teacher_say|teacher_action|student_say|student_action|narration|system
    content: str


@dataclass
class TurnResult:
    turn: int
    events: list[TurnEvent] = field(default_factory=list)
    states: dict[str, StudentState] = field(default_factory=dict)
    minute: int = 0
    phase: str = "도입"
    ended: bool = False
    report_markdown: str | None = None


# ---------------------------------------------------------------------------
# 가짜 대사 템플릿
# ---------------------------------------------------------------------------

_SAY_HIGH = [
    "선생님, 그럼 3 대 5랑 5 대 3은 다른 거죠?",
    "이거 비율로 바꾸면 0.6 맞나요?",
    "기준량이 뒤에 오는 수라는 거 이해했어요!",
    "다른 방법으로 풀어도 돼요?",
]
_SAY_MID = [
    "음... 조금 알 것 같기도 하고요.",
    "선생님 한 번만 더 설명해 주세요.",
    "적는 거 다 못 했어요, 잠깐만요.",
    "아 그거 아까 배운 거랑 비슷한 거네요.",
]
_SAY_LOW = [
    "(작은 목소리로) 잘 모르겠어요...",
    "저는 어차피 못할 것 같은데요.",
    "……",
    "어디 하는 거예요? 지금 몇 쪽이에요?",
]
_ACTIONS = [
    "창밖을 봄",
    "샤프를 돌리고 있음",
    "공책에 필기를 옮겨 적음",
    "손을 번쩍 듦",
    "옆 친구에게 속삭임",
    "책상에 엎드릴 듯 몸을 기울임",
    "고개를 갸웃함",
    "칠판을 뚫어져라 봄",
]
_EMOTIONS = ["평온", "들뜸", "위축", "불안", "지루함", "몰입"]

_INCIDENT_CARDS = {
    "친구갈등": "뒷자리 두 학생이 지우개 때문에 다투기 시작한다.",
    "기기고장": "TV 화면이 갑자기 꺼지고 자료가 보이지 않는다.",
    "방송소음": "교내 방송이 울려 설명이 끊긴다.",
    "조퇴요청": "한 학생이 배가 아프다며 보건실에 가고 싶어 한다.",
    "벌레소동": "창문으로 벌이 들어와 몇몇 학생이 소리를 지른다.",
    "복도소란": "옆 반이 이동수업을 나가며 복도가 시끄러워진다.",
}

_PHASES = ["도입", "전개", "활동", "정리"]


def _clamp(v: int) -> int:
    return max(0, min(100, v))


class FakeSession:
    """StageSession과 동일한 외부 인터페이스를 갖는 가짜 세션."""

    def __init__(
        self,
        classroom: Classroom,
        lesson_text: str,
        backend=None,
        seed: int | None = None,
    ) -> None:
        self.classroom = classroom
        self.lesson_text = lesson_text
        self.backend = backend
        self.rng = random.Random(seed if seed is not None else 20240613)
        self.turn_no = 0
        self.minute = 0
        self.phase = "도입"
        self.ended = False
        self.states: dict[str, StudentState] = {}
        self.transcript: list[dict] = []
        self.groups: dict[str, int] = {}  # 학생 id → 모둠 번호
        for s in classroom.students:
            base = {"상": 82, "중상": 72, "중": 62, "하": 45}.get(s.achievement_level, 60)
            self.states[s.id] = StudentState(
                comprehension=_clamp(base + self.rng.randint(-4, 4)),
                interest=_clamp(60 + self.rng.randint(-12, 12)),
                focus=_clamp(72 + self.rng.randint(-10, 10)),
                emotion="평온",
                visible_action="자리에 앉아 교사를 봄",
            )

    # -- 내부 도우미 ---------------------------------------------------------

    def _student(self, key: str) -> Student | None:
        key = key.strip()
        for s in self.classroom.students:
            if s.id.lower() == key.lower() or s.name == key:
                return s
        for s in self.classroom.students:  # 부분 일치 (예: "지우")
            if key and key in s.name:
                return s
        return None

    def _say_for(self, s: Student) -> str:
        if s.achievement_level in ("상", "중상"):
            pool = _SAY_HIGH
        elif s.achievement_level == "하":
            pool = _SAY_LOW
        else:
            pool = _SAY_MID
        return self.rng.choice(pool)

    def _log(self, actor: str, kind: str, content: str) -> TurnEvent:
        ev = TurnEvent(actor=actor, kind=kind, content=content)
        self.transcript.append(
            {
                "turn": self.turn_no,
                "minute": self.minute,
                "phase": self.phase,
                "actor": actor,
                "kind": kind,
                "content": content,
            }
        )
        return ev

    def _drift(self, exclude: set[str] | None = None) -> None:
        """시간 경과에 따른 전원 게이지 자연 변화."""
        exclude = exclude or set()
        for sid, st in self.states.items():
            if sid in exclude:
                continue
            st.focus = _clamp(st.focus + self.rng.randint(-6, 3))
            st.interest = _clamp(st.interest + self.rng.randint(-4, 3))
            st.comprehension = _clamp(st.comprehension + self.rng.randint(-2, 3))
            if st.focus < 35:
                st.emotion = self.rng.choice(["지루함", "지루함", "위축"])
                st.visible_action = self.rng.choice(
                    ["책상에 엎드릴 듯 몸을 기울임", "창밖을 봄", "샤프를 돌리고 있음"]
                )
            elif st.interest > 75 and st.comprehension > 65:
                st.emotion = self.rng.choice(["몰입", "들뜸"])
                st.visible_action = self.rng.choice(["손을 번쩍 듦", "칠판을 뚫어져라 봄"])

    def _react(self, count: int, forced: list[Student] | None = None) -> list[TurnEvent]:
        """이번 턴에 겉으로 드러나는 반응을 하는 학생 2~3명을 뽑아 이벤트 생성.

        forced(지목당한 학생)는 반드시 포함되고 반드시 발화한다.
        """
        events: list[TurnEvent] = []
        forced = list(forced or [])
        chosen: list[Student] = list(forced)
        pool = [s for s in self.classroom.students if s not in chosen]
        self.rng.shuffle(pool)
        chosen += pool[: max(0, count - len(chosen))]
        for s in chosen:
            st = self.states[s.id]
            if s in forced or self.rng.random() < 0.72:
                events.append(self._log(s.id, "student_say", self._say_for(s)))
                st.interest = _clamp(st.interest + self.rng.randint(2, 10))
                st.focus = _clamp(st.focus + self.rng.randint(3, 12))
                if s not in forced:  # 지목당한 학생의 정서(불안 등)는 유지
                    st.emotion = self.rng.choice(["몰입", "들뜸", "평온"])
                st.visible_action = "발표하듯 말함"
            else:
                act = self.rng.choice(_ACTIONS)
                events.append(self._log(s.id, "student_action", f"({act})"))
                st.visible_action = act
                st.emotion = self.rng.choice(_EMOTIONS)
        return events

    def _result(self, events: list[TurnEvent], report: str | None = None) -> TurnResult:
        return TurnResult(
            turn=self.turn_no,
            events=events,
            states={k: StudentState(**vars(v)) for k, v in self.states.items()},
            minute=self.minute,
            phase=self.phase,
            ended=self.ended,
            report_markdown=report,
        )

    def _advance_phase(self) -> None:
        if self.ended:
            return
        if self.minute >= 32:
            self.phase = "정리"
        elif self.minute >= 12 and self.phase == "도입":
            self.phase = "전개"

    # -- 계약 API ------------------------------------------------------------

    def turn(self, teacher_input: str) -> TurnResult:
        text = (teacher_input or "").strip()
        if self.ended:
            self.turn_no += 1
            return self._result([self._log("무대", "system", "이미 종료된 수업입니다.")])

        self.turn_no += 1
        events: list[TurnEvent] = []

        # /상태 — LLM 호출 0회, 상태표만 반환
        if text.startswith("/상태"):
            rows = ", ".join(
                f"{s.name} 이해{self.states[s.id].comprehension}"
                f"/흥미{self.states[s.id].interest}/집중{self.states[s.id].focus}"
                for s in self.classroom.students
            )
            events.append(self._log("무대", "system", f"[상태] {rows}"))
            return self._result(events)

        # /종료
        if text.startswith("/종료"):
            return self._end_turn()

        if text.startswith("/"):
            cmd, _, arg = text.partition(" ")
            arg = arg.strip()
            events += self._command(cmd, arg)
        elif text.startswith("@"):
            target, _, said = text[1:].partition(" ")
            s = self._student(target)
            events.append(self._log("교사", "teacher_say", text))
            if s is None:
                events.append(
                    self._log("무대", "system", f"'{target}' 학생을 찾을 수 없습니다.")
                )
            else:
                st = self.states[s.id]
                st.emotion = "불안" if "발표" in (s.personality or "") else "들뜸"
                events += self._react(2, forced=[s])
            self.minute += 1
        else:
            if not text:
                return self._result(
                    [self._log("무대", "system", "입력이 비어 있습니다.")]
                )
            events.append(self._log("교사", "teacher_say", text))
            events += self._react(self.rng.randint(2, 3))
            self.minute += 2

        self._drift()
        self._advance_phase()
        return self._result(events)

    def _command(self, cmd: str, arg: str) -> list[TurnEvent]:
        ev: list[TurnEvent] = []
        if cmd == "/판서":
            ev.append(self._log("교사", "teacher_action", f"판서: {arg}"))
            ev.append(self._log("무대", "narration", "학생들이 공책에 옮겨 적는다."))
            ev += self._react(2)
            self.minute += 2
        elif cmd == "/활동":
            self.phase = "활동"
            ev.append(self._log("교사", "teacher_action", f"활동 지시: {arg}"))
            ev.append(self._log("무대", "narration", "교실이 잠시 웅성거린다."))
            ev += self._react(3)
            for st in self.states.values():
                st.interest = _clamp(st.interest + self.rng.randint(4, 14))
                st.focus = _clamp(st.focus + self.rng.randint(2, 10))
            self.minute += 3
        elif cmd == "/모둠":
            ev += self._make_groups(arg)
            self.minute += 2
        elif cmd == "/모둠활동":
            self.phase = "모둠활동"
            if not self.groups:
                self._make_groups("4인")
            ev.append(self._log("교사", "teacher_action", f"모둠 활동: {arg}"))
            for g in sorted(set(self.groups.values())):
                members = [s for s in self.classroom.students if self.groups.get(s.id) == g]
                for s in members[: self.rng.randint(2, 3)]:
                    ev.append(
                        self._log(s.id, "student_say", f"({g}모둠) {self._say_for(s)}")
                    )
            self.minute += 4
        elif cmd == "/순회":
            name, _, extra = arg.partition(" ")
            s = self._student(name)
            if s is None:
                ev.append(self._log("무대", "system", f"'{name}' 학생을 찾을 수 없습니다."))
            else:
                ev.append(
                    self._log("교사", "teacher_action", f"{s.name} 옆에 앉아 살펴본다. {extra}".strip())
                )
                ev.append(self._log(s.id, "student_say", self._say_for(s)))
                st = self.states[s.id]
                st.comprehension = _clamp(st.comprehension + self.rng.randint(5, 15))
                st.emotion = "평온"
                st.visible_action = "교사와 1:1로 이야기함"
            self.minute += 3
        elif cmd in ("/칭찬", "/주의"):
            name, _, extra = arg.partition(" ")
            s = self._student(name)
            if s is None:
                ev.append(self._log("무대", "system", f"'{name}' 학생을 찾을 수 없습니다."))
            else:
                ev.append(self._log("교사", "teacher_say", f"{cmd[1:]}: {s.name} {extra}".strip()))
                st = self.states[s.id]
                if cmd == "/칭찬":
                    st.interest = _clamp(st.interest + 12)
                    st.emotion = "들뜸"
                    st.visible_action = "쑥스럽게 웃음"
                    ev.append(self._log(s.id, "student_action", "(입꼬리가 올라간다)"))
                else:
                    st.focus = _clamp(st.focus + 15)
                    st.emotion = "위축"
                    st.visible_action = "자세를 바로 함"
                    ev.append(self._log(s.id, "student_action", "(고개를 숙인다)"))
            self.minute += 1
        elif cmd == "/시간":
            m = re.search(r"(\d+)", arg)
            add = int(m.group(1)) if m else 5
            self.minute += add
            ev.append(self._log("무대", "narration", f"{add}분이 흐른다. 활동이 마무리된다."))
            ev += self._react(2)
            self._drift()
        elif cmd == "/돌발":
            name = arg.strip() or self.rng.choice(list(_INCIDENT_CARDS))
            desc = _INCIDENT_CARDS.get(name)
            if desc is None:
                name = self.rng.choice(list(_INCIDENT_CARDS))
                desc = _INCIDENT_CARDS[name]
            ev.append(self._log("무대", "narration", f"[돌발: {name}] {desc}"))
            ev += self._react(2)
            for st in self.states.values():
                st.focus = _clamp(st.focus - self.rng.randint(5, 20))
            self.minute += 2
        else:
            ev.append(
                self._log(
                    "무대",
                    "system",
                    f"알 수 없는 명령 '{cmd}'. 사용 가능: /판서 /활동 /모둠 /모둠활동 "
                    "/순회 /칭찬 /주의 /시간 /돌발 /상태 /종료",
                )
            )
        return ev

    def _make_groups(self, arg: str) -> list[TurnEvent]:
        self.groups = {}
        if "/" in arg or "," in arg and not arg.endswith("인"):
            for gi, chunk in enumerate(arg.split("/"), start=1):
                for key in chunk.split(","):
                    s = self._student(key)
                    if s:
                        self.groups[s.id] = gi
        if not self.groups:
            m = re.search(r"(\d+)", arg)
            size = int(m.group(1)) if m else 4
            size = max(2, min(6, size))
            ids = [s.id for s in self.classroom.students]
            for i, sid in enumerate(ids):
                self.groups[sid] = i // size + 1
        parts = []
        for g in sorted(set(self.groups.values())):
            names = [
                f"{s.name}({s.id})"
                for s in self.classroom.students
                if self.groups.get(s.id) == g
            ]
            parts.append(f"{g}모둠: {', '.join(names)}")
        return [self._log("무대", "system", "모둠 편성 완료 — " + " | ".join(parts))]

    def _end_turn(self) -> TurnResult:
        self.ended = True
        self.phase = "종료"
        events = [self._log("교사", "teacher_say", "/종료")]
        events.append(self._log("무대", "narration", "수업을 마칩니다. 인사하고 정리한다."))
        report = self._report()
        return self._result(events, report=report)

    def _report(self) -> str:
        avg = lambda k: round(  # noqa: E731
            sum(getattr(s, k) for s in self.states.values()) / max(1, len(self.states))
        )
        teacher_says = sum(1 for t in self.transcript if t["kind"] == "teacher_say")
        student_says = sum(1 for t in self.transcript if t["kind"] == "student_say")
        questions = sum(
            1 for t in self.transcript if t["kind"] == "teacher_say" and "?" in t["content"]
        )
        counts: dict[str, int] = {}
        for t in self.transcript:
            if t["kind"] in ("student_say", "student_action"):
                counts[t["actor"]] = counts.get(t["actor"], 0) + 1
        name_of = {s.id: s.name for s in self.classroom.students}
        rows = "\n".join(
            f"| {s.name} | {self.states[s.id].comprehension} | "
            f"{self.states[s.id].interest} | {self.states[s.id].focus} | "
            f"{self.states[s.id].emotion} | {counts.get(s.id, 0)} |"
            for s in self.classroom.students
        )
        silent = [name_of[s.id] for s in self.classroom.students if counts.get(s.id, 0) == 0]
        return f"""# 수업 사후 리포트 — {self.classroom.class_name}

> **시뮬레이션 결과입니다.** 가상 페르소나 기반이며 실제 학생 예측·평가·선발에 사용할 수 없습니다.
> (개발용 FakeSession이 생성한 예시 리포트입니다.)

## 수업 개요
- 진행 턴 수: **{self.turn_no}턴**, 경과 시간: **{self.minute}분**
- 학급 평균 — 이해도 {avg('comprehension')} / 흥미 {avg('interest')} / 집중 {avg('focus')}

## 학생별 최종 상태

| 학생 | 이해도 | 흥미 | 집중 | 정서 | 반응 횟수 |
|---|---|---|---|---|---|
{rows}

## 수업 분석

- 교사 발화 **{teacher_says}회**, 학생 발화 **{student_says}회** (비율 1 : {round(student_says / max(1, teacher_says), 2)})
- 물음표가 포함된 교사 발화(발문 추정) **{questions}회**
- 발언 형평성: 한 번도 드러나지 않은 학생 **{len(silent)}명**{(' — ' + ', '.join(silent)) if silent else ''}

### 개선 제안
1. 설명이 12분을 넘어가면 집중이 낮은 학생부터 이탈합니다. 짧은 활동을 끼워 넣어 보세요.
2. 지목이 특정 학생에게 쏠리지 않도록, 반응이 없던 학생에게 짧은 확인 질문을 건네 보세요.
3. `/순회`로 개별 지도한 학생은 이해도가 뚜렷하게 올랐습니다. 활동 시간에 2~3명을 계획적으로 도세요.
"""

    def state_snapshot(self) -> dict:
        return {
            "turn": self.turn_no,
            "minute": self.minute,
            "phase": self.phase,
            "ended": self.ended,
            "class_name": self.classroom.class_name,
            "students": [
                {
                    "id": s.id,
                    "name": s.name,
                    "achievement_level": s.achievement_level,
                    "comprehension": self.states[s.id].comprehension,
                    "interest": self.states[s.id].interest,
                    "focus": self.states[s.id].focus,
                    "emotion": self.states[s.id].emotion,
                    "visible_action": self.states[s.id].visible_action,
                }
                for s in self.classroom.students
            ],
        }

    def transcript_json(self) -> list[dict]:
        return list(self.transcript)

    def end(self) -> str:
        if self.ended:
            return self._report()
        return self._end_turn().report_markdown or ""
