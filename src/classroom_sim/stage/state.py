"""교실 무대의 상태 모델.

계약서(docs/specs/stage_contract.md)의 StudentState / TurnEvent / TurnResult 와
엔진 내부에서만 쓰는 ClassState 를 정의한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 수업 국면 (감독이 자유롭게 쓸 수 있으나 표시/검증용 기본 목록)
PHASES: tuple[str, ...] = ("도입", "전개", "활동", "모둠활동", "정리", "종료")


def clamp(value: float, low: int = 0, high: int = 100) -> int:
    """게이지 값을 0~100 정수로 자른다."""
    return max(low, min(high, int(round(value))))


@dataclass
class StudentState:
    comprehension: int = 60   # 이해도 0~100
    interest: int = 60        # 흥미 0~100
    focus: int = 70           # 집중 0~100
    emotion: str = "평온"      # 평온|들뜸|위축|불안|지루함|몰입 등 자유
    visible_action: str = ""  # 현재 겉으로 보이는 모습 (짧은 서술)

    def to_dict(self) -> dict:
        return {
            "comprehension": self.comprehension,
            "interest": self.interest,
            "focus": self.focus,
            "emotion": self.emotion,
            "visible_action": self.visible_action,
        }


@dataclass
class TurnEvent:
    actor: str      # "교사" | 학생 id (예: "S04") | "무대"
    kind: str       # teacher_say|teacher_action|student_say|student_action|narration|system
    content: str    # 발화 내용 또는 행동/서술

    def to_dict(self) -> dict:
        return {"actor": self.actor, "kind": self.kind, "content": self.content}


@dataclass
class TurnResult:
    turn: int
    events: list[TurnEvent]              # 이번 턴에 새로 발생한 이벤트 (표시용)
    states: dict[str, StudentState]      # 학생 id → 최신 상태 (전체)
    minute: int                          # 수업 경과 분
    phase: str                           # 도입|전개|활동|모둠활동|정리|종료 등
    ended: bool = False
    report_markdown: str | None = None   # /종료 시 사후 리포트


@dataclass
class ClassState:
    """엔진 내부용 학급 전체 상태."""

    turn: int = 0
    minute: int = 0
    phase: str = "도입"
    ended: bool = False
    students: dict[str, StudentState] = field(default_factory=dict)
    # 모둠 편성 — [["S01","S02"], ["S03","S04"]]
    groups: list[list[str]] = field(default_factory=list)
    # 지금까지 발생한 돌발 상황 카드 이름
    incidents: list[str] = field(default_factory=list)

    def group_of(self, student_id: str) -> list[str]:
        """해당 학생이 속한 모둠(없으면 빈 리스트)."""
        for g in self.groups:
            if student_id in g:
                return g
        return []

    def focus_map(self) -> dict[str, int]:
        """현재 시점의 학생별 집중도 스냅샷."""
        return {sid: st.focus for sid, st in self.students.items()}
