"""학생 에이전트 — 페르소나 + 현재 상태 + 자기 관점 전사 → 대사/행동."""

from __future__ import annotations

from ..personas import Student
from .backend import pack_payload
from .director import traits_of
from .state import StudentState

STUDENT_RULES = """너는 이 학생이다. 초등 6학년답게, 페르소나답게 짧게 말하거나 행동해라.
- 모르면 모르는 티를 내고, 틀린 개념은 틀리게 말해라(오개념 재현).
- 침묵/몸짓도 응답이다. 할 말이 없으면 utterance를 비우고 action만 써라.
- 어른스러운 정리나 모범답안을 만들지 마라. 한두 문장이면 충분하다.
- 네 관점 전사에서 '딴생각을 하느라 잘 못 들었다'로 표시된 부분은 실제로 듣지 못한 내용이다.
  그 내용을 알고 있는 것처럼 말하지 마라.
- 현재 상태 게이지(이해도·흥미·집중·정서)를 그대로 반영해라."""

STUDENT_SCHEMA = {
    "type": "object",
    "properties": {
        "utterance": {"type": "string", "description": "학생이 실제로 하는 말 (없으면 빈 문자열)"},
        "action": {"type": "string", "description": "겉으로 보이는 행동/몸짓 (없으면 빈 문자열)"},
    },
    "required": ["utterance", "action"],
    "additionalProperties": False,
}

GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "description": "모둠 안에서 오간 2~3개의 발화/행동 (시간순)",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "말한 학생 ID"},
                    "utterance": {"type": "string", "description": "말 (없으면 빈 문자열)"},
                    "action": {"type": "string", "description": "행동 (없으면 빈 문자열)"},
                },
                "required": ["id", "utterance", "action"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lines"],
    "additionalProperties": False,
}


def build_system(system_prefix: list[dict] | str, student: Student) -> list[dict] | str:
    """공용 캐시 프리픽스 뒤에 해당 학생 페르소나 전문을 붙인다."""
    role = (
        f"<너의_페르소나>\n{student.to_prompt_block()}\n</너의_페르소나>\n\n{STUDENT_RULES}"
    )
    if isinstance(system_prefix, str):
        return f"{system_prefix}\n\n{role}"
    return list(system_prefix) + [{"type": "text", "text": role}]


def speak(
    backend,
    *,
    system_prefix: list[dict] | str,
    student: Student,
    state: StudentState,
    cue: str,
    perspective: str,
    nominated: bool = False,
    minute: int = 0,
    phase: str = "전개",
    max_tokens: int = 1024,
) -> dict:
    """학생 1명의 발화/행동을 생성한다."""
    payload = {
        "id": student.id,
        "name": student.name,
        "achievement_level": student.achievement_level,
        "traits": traits_of(student),
        "interests": list(student.interests),
        "state": state.to_dict(),
        "cue": cue,
        "nominated": nominated,
        "minute": minute,
        "phase": phase,
    }
    text = (
        f"<내_관점_전사>\n{perspective or '(아직 기억나는 장면이 없다)'}\n</내_관점_전사>\n\n"
        f"{pack_payload(payload)}\n\n"
        f"감독 지시: {cue}\n"
        "지금 이 순간 네가 하는 말과 행동을 써라."
    )
    result = backend.complete_json(
        system=build_system(system_prefix, student),
        messages=[{"role": "user", "content": text}],
        schema=STUDENT_SCHEMA,
        max_tokens=max_tokens,
        model_role="actor",
    )
    return {
        "utterance": (result.get("utterance") or "").strip(),
        "action": (result.get("action") or "").strip(),
    }


def group_talk(
    backend,
    *,
    system_prefix: list[dict] | str,
    members: list[tuple[Student, StudentState]],
    instruction: str,
    perspective: str,
    minute: int = 0,
    phase: str = "모둠활동",
    max_tokens: int = 2048,
) -> list[dict]:
    """모둠 1개의 대화 1라운드(2~3발화)를 한 번의 호출로 생성한다."""
    if not members:
        return []

    blocks = "\n\n".join(
        f"<학생 id=\"{s.id}\">\n{s.to_prompt_block()}\n</학생>" for s, _ in members
    )
    role = (
        f"너는 아래 학생들이 모인 모둠의 대화를 그대로 옮겨 적는 기록자다.\n{blocks}\n\n"
        f"{STUDENT_RULES}\n"
        "- 각 학생은 자기 페르소나와 상태대로 말한다. 무임승차, 주도권 다툼, 침묵도 그대로 재현해라.\n"
        "- 모둠 대화는 2~3개의 발화/행동으로 끝낸다."
    )
    system = (
        f"{system_prefix}\n\n{role}"
        if isinstance(system_prefix, str)
        else list(system_prefix) + [{"type": "text", "text": role}]
    )

    payload = {
        "instruction": instruction,
        "minute": minute,
        "phase": phase,
        "group": [
            {
                "id": s.id,
                "name": s.name,
                "traits": traits_of(s),
                "state": st.to_dict(),
            }
            for s, st in members
        ],
    }
    text = (
        f"<모둠_지시>\n{instruction}\n</모둠_지시>\n\n"
        f"<교실_전사>\n{perspective or '(기록 없음)'}\n</교실_전사>\n\n"
        f"{pack_payload(payload)}\n\n"
        "이 모둠 안에서 실제로 오갈 법한 대화 2~3개를 시간순으로 써라."
    )
    result = backend.complete_json(
        system=system,
        messages=[{"role": "user", "content": text}],
        schema=GROUP_SCHEMA,
        max_tokens=max_tokens,
        model_role="actor",
    )
    valid_ids = {s.id for s, _ in members}
    lines = []
    for line in result.get("lines", [])[:3]:
        sid = line.get("id")
        if sid not in valid_ids:
            continue
        lines.append({
            "id": sid,
            "utterance": (line.get("utterance") or "").strip(),
            "action": (line.get("action") or "").strip(),
        })
    return lines
