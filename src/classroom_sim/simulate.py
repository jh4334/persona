"""Claude API를 이용한 학생별 반응 시뮬레이션.

- 수업 자료(학습단원)는 system 프롬프트에 넣고 prompt caching으로 학생 수만큼 재사용
- 학생별 결과는 structured outputs(JSON schema)로 받아 파싱 없이 바로 사용
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import anthropic

from .personas import Classroom, Student

MODEL = "claude-opus-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# 학생 1명의 예상 반응 스키마
STUDENT_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "comprehension": {
            "type": "integer",
            "enum": [1, 2, 3, 4, 5],
            "description": "이 수업에 대한 예상 이해도 (1=거의 이해 못함, 5=완전 이해)",
        },
        "engagement": {
            "type": "integer",
            "enum": [1, 2, 3, 4, 5],
            "description": "예상 흥미/참여도 (1=매우 낮음, 5=매우 높음)",
        },
        "predicted_reaction": {
            "type": "string",
            "description": "수업 흐름 단계별로 이 학생이 보일 것으로 예상되는 행동과 반응 (3~5문장)",
        },
        "voice_sample": {
            "type": "string",
            "description": "이 학생이 수업 중 실제로 할 법한 말 한두 마디 (학생 말투 그대로)",
        },
        "likely_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "이 학생이 할 법한 질문 목록",
        },
        "misconceptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "이 학생이 가질 가능성이 높은 오개념",
        },
        "difficulties": {
            "type": "array",
            "items": {"type": "string"},
            "description": "이 학생이 어려움을 겪을 것으로 예상되는 지점",
        },
        "teaching_strategies": {
            "type": "array",
            "items": {"type": "string"},
            "description": "이 학생을 위한 구체적인 맞춤 지도 전략",
        },
    },
    "required": [
        "comprehension",
        "engagement",
        "predicted_reaction",
        "voice_sample",
        "likely_questions",
        "misconceptions",
        "difficulties",
        "teaching_strategies",
    ],
    "additionalProperties": False,
}


@dataclass
class StudentResult:
    student: Student
    comprehension: int
    engagement: int
    predicted_reaction: str
    voice_sample: str
    likely_questions: list[str] = field(default_factory=list)
    misconceptions: list[str] = field(default_factory=list)
    difficulties: list[str] = field(default_factory=list)
    teaching_strategies: list[str] = field(default_factory=list)
    error: str | None = None


def _build_system(classroom: Classroom, lesson_text: str) -> list[dict]:
    role = (
        "당신은 교육 시뮬레이션 전문가입니다. 주어진 학생 페르소나의 관점에서, "
        "해당 학생이 아래 수업(학습단원)에 어떻게 반응할지 현실적으로 예측합니다.\n"
        "- 페르소나에 명시된 성취 수준, 사전 지식, 학습 스타일, 성격, 흥미를 일관되게 반영하세요.\n"
        "- 낙관적으로 미화하지 말고, 실제 교실에서 관찰될 법한 반응을 예측하세요.\n"
        "- 오개념과 난점은 이 단원의 내용에 근거해 구체적으로 쓰세요.\n"
        "- 지도 전략은 교사가 다음 수업에서 바로 실행할 수 있을 만큼 구체적으로 쓰세요.\n"
        f"\n대상 학급: {classroom.class_name} ({classroom.grade})"
    )
    return [
        {"type": "text", "text": role},
        {
            "type": "text",
            "text": f"<수업_자료>\n{lesson_text}\n</수업_자료>",
            # 수업 자료는 모든 학생 요청에서 동일 → 캐시로 비용 절감
            "cache_control": {"type": "ephemeral"},
        },
    ]


def _simulate_one(
    client: anthropic.Anthropic,
    system: list[dict],
    student: Student,
) -> StudentResult:
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4096,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=system,
            output_config={
                "format": {"type": "json_schema", "schema": STUDENT_RESULT_SCHEMA}
            },
            messages=[
                {
                    "role": "user",
                    "content": (
                        "다음 학생이 위 수업에 어떻게 반응할지 예측해 주세요.\n\n"
                        f"<학생_페르소나>\n{student.to_prompt_block()}\n</학생_페르소나>"
                    ),
                }
            ],
        )
        if response.stop_reason == "refusal":
            return StudentResult(
                student=student, comprehension=0, engagement=0,
                predicted_reaction="", voice_sample="",
                error="요청이 안전상의 이유로 거부되었습니다 (refusal).",
            )
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        return StudentResult(student=student, **data)
    except Exception as e:  # noqa: BLE001 — 학생 1명 실패가 전체를 멈추지 않도록
        return StudentResult(
            student=student, comprehension=0, engagement=0,
            predicted_reaction="", voice_sample="", error=str(e),
        )


def simulate_classroom(
    classroom: Classroom,
    lesson_text: str,
    max_workers: int = 4,
    on_progress=None,
) -> list[StudentResult]:
    """학급 전체 학생에 대해 시뮬레이션을 실행한다."""
    client = anthropic.Anthropic()
    system = _build_system(classroom, lesson_text)

    results: dict[str, StudentResult] = {}

    def run(student: Student) -> None:
        results[student.id] = _simulate_one(client, system, student)
        if on_progress:
            on_progress(results[student.id])

    # 첫 요청으로 캐시를 먼저 쓰고, 나머지는 병렬 실행(캐시 읽기)
    run(classroom.students[0])
    rest = classroom.students[1:]
    if rest:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            list(pool.map(run, rest))

    return [results[s.id] for s in classroom.students]


def synthesize_class_insights(
    classroom: Classroom,
    lesson_text: str,
    results: list[StudentResult],
) -> str:
    """학생별 결과를 종합해 학급 수준의 수업 설계 제안을 생성한다."""
    client = anthropic.Anthropic()
    ok = [r for r in results if not r.error]
    summary_lines = []
    for r in ok:
        summary_lines.append(
            f"- {r.student.name}({r.student.achievement_level}): "
            f"이해도 {r.comprehension}/5, 흥미 {r.engagement}/5. "
            f"난점: {'; '.join(r.difficulties[:2]) or '없음'}. "
            f"오개념: {'; '.join(r.misconceptions[:2]) or '없음'}"
        )
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4096,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        system=(
            "당신은 초등 수업 설계 컨설턴트입니다. 학생별 반응 시뮬레이션 결과를 종합해 "
            "교사가 수업을 어떻게 조정하면 좋을지 제안합니다. 마크다운으로, "
            "(1) 학급 전체 경향 요약, (2) 공통 오개념 대응 방안, (3) 수준별 지도 전략, "
            "(4) 수업 흐름 조정 제안 순으로 간결하게 작성하세요."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"<수업_자료>\n{lesson_text}\n</수업_자료>\n\n"
                    f"<학생별_시뮬레이션_요약>\n" + "\n".join(summary_lines) + "\n</학생별_시뮬레이션_요약>"
                ),
            }
        ],
    )
    if response.stop_reason == "refusal":
        return "_(종합 분석 생성이 거부되었습니다.)_"
    return next((b.text for b in response.content if b.type == "text"), "")
