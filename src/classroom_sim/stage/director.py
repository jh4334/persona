"""무대 감독(Director).

교사 행동 1건을 받아 ① 장면 해석 ② 전원 상태 갱신 ③ 이번 턴에 겉으로 드러나는
반응을 할 학생 0~3명 선정을 한 번의 호출로 처리한다. 턴당 호출을 억제하는 핵심.
"""

from __future__ import annotations

from ..personas import Student
from .backend import pack_payload
from .state import StudentState

DIRECTOR_SYSTEM = """당신은 초등 교실 시뮬레이션의 '무대 감독'입니다.
교사의 행동 한 건을 받아, 학급 전원의 상태를 갱신하고 이번 장면에서 겉으로 드러나는
반응을 할 학생을 고릅니다.

반드시 지킬 것:
- 학생 반응을 미화하지 말 것. 이해 못 하는 학생은 계속 못 하고, 집중 잃은 학생은 딴짓을 한다.
- 게이지는 페르소나 속성의 함수로 움직인다(주의집중 짧은 학생은 설명이 길어지면 먼저 흐트러짐,
  발표불안 학생은 지목 시 불안).
- 이해도는 한 번의 설명으로 급등하지 않는다. 결손이 있는 학생은 개별 지도 없이는 회복되지 않는다.
- 흥미는 관심사와 연결되거나 활동형 국면으로 바뀔 때 오르고, 같은 형태가 반복되면 내려간다.
- 집중은 시간이 지날수록 떨어진다. 활동 전환·지목·돌발 상황은 일시적으로 회복시킨다.
- speakers는 0~3명. 교사가 특정 학생을 지목했다면 그 학생은 반드시 포함한다.
  침묵이나 딴짓도 '겉으로 드러나는 반응'이므로 speakers에 넣을 수 있다.
- cue는 그 학생이 지금 어떤 상태에서 무엇을 하려는지 한두 문장으로 적는다(대사는 쓰지 않는다).
- narration은 교실 전체 분위기를 한두 문장으로 적는다. 과장하지 않는다.
- 게이지는 0~100 정수, minute_delta는 이번 행동에 실제로 걸릴 만한 분 수를 쓴다."""

_UPDATE_ITEM = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "학생 ID"},
        "comprehension": {"type": "integer", "description": "갱신된 이해도 0~100"},
        "interest": {"type": "integer", "description": "갱신된 흥미 0~100"},
        "focus": {"type": "integer", "description": "갱신된 집중 0~100"},
        "emotion": {"type": "string", "description": "평온|들뜸|위축|불안|지루함|몰입 등"},
        "visible_action": {"type": "string", "description": "겉으로 보이는 모습(짧게, 없으면 빈 문자열)"},
    },
    "required": ["id", "comprehension", "interest", "focus", "emotion", "visible_action"],
    "additionalProperties": False,
}

_SPEAKER_ITEM = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "이번 턴에 반응할 학생 ID"},
        "cue": {"type": "string", "description": "그 학생에게 주는 연기 지시(대사 아님)"},
    },
    "required": ["id", "cue"],
    "additionalProperties": False,
}

DIRECTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "minute_delta": {"type": "integer", "description": "이번 턴에 흐른 수업 시간(분)"},
        "phase": {"type": "string", "description": "도입|전개|활동|모둠활동|정리|종료"},
        "updates": {"type": "array", "items": _UPDATE_ITEM, "description": "전원의 갱신된 상태"},
        "speakers": {"type": "array", "items": _SPEAKER_ITEM, "description": "0~3명"},
        "narration": {"type": "string", "description": "교실 전체 분위기 서술"},
    },
    "required": ["minute_delta", "phase", "updates", "speakers", "narration"],
    "additionalProperties": False,
}


def traits_of(student: Student) -> list[str]:
    """감독에게 줄 '핵심 특성 3줄'."""
    attrs: list[str] = []
    for group in ("cognitive", "motivation", "behavior_social", "study_habits", "language"):
        for key, value in (getattr(student, group, {}) or {}).items():
            if any(k in key for k in ("주의집중", "자기효능감", "수업참여", "시험불안", "처리속도",
                                      "학습동기", "작업기억", "도움요청", "한국어숙달도")):
                attrs.append(f"{key}: {value}")
    line3 = " / ".join(attrs[:3]) if attrs else (student.notes or "특기사항 없음")
    return [
        f"성취수준 {student.achievement_level} · 사전지식: {student.prior_knowledge or '정보 없음'}",
        f"성격: {student.personality or '정보 없음'} · 학습스타일: {student.learning_style or '정보 없음'}",
        line3,
    ]


def student_payload(student: Student, state: StudentState) -> dict:
    """감독 프롬프트에 넣을 학생 1명 요약."""
    return {
        "id": student.id,
        "name": student.name,
        "achievement_level": student.achievement_level,
        "traits": traits_of(student),
        "interests": list(student.interests),
        "state": state.to_dict(),
    }


def build_user_message(
    *,
    action: dict,
    students: list[dict],
    recent_transcript: str,
    turn: int,
    minute: int,
    phase: str,
    groups: list[list[str]] | None = None,
) -> dict:
    """감독 호출용 user 메시지."""
    payload = {
        "turn": turn,
        "minute": minute,
        "phase": phase,
        "action": action,
        "groups": groups or [],
        "students": students,
    }
    text = (
        "아래는 지금 무대의 상태와 교사가 방금 한 행동입니다.\n"
        "학급 전원의 상태를 갱신하고, 이번 장면에서 반응할 학생을 고르세요.\n\n"
        f"{pack_payload(payload)}\n\n"
        f"<최근_전사>\n{recent_transcript or '(아직 기록 없음)'}\n</최근_전사>"
    )
    return {"role": "user", "content": text}


def direct(
    backend,
    *,
    system: list[dict] | str,
    action: dict,
    students: list[dict],
    recent_transcript: str,
    turn: int,
    minute: int,
    phase: str,
    groups: list[list[str]] | None = None,
    max_tokens: int = 4096,
) -> dict:
    """감독 1회 호출."""
    message = build_user_message(
        action=action,
        students=students,
        recent_transcript=recent_transcript,
        turn=turn,
        minute=minute,
        phase=phase,
        groups=groups,
    )
    return backend.complete_json(
        system=system,
        messages=[message],
        schema=DIRECTOR_SCHEMA,
        max_tokens=max_tokens,
        model_role="director",
    )
