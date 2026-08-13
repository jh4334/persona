"""수업 분석 — 교사 행동 자체를 되돌아보는 성찰 리포트.

결정적 통계(발화 수, 형평성, 지목 분포, 질문 수)는 전사만으로 계산하고,
발문 수준 분류와 개선 제안만 백엔드 1회 호출로 받는다(mock은 고정 문구).
"""

from __future__ import annotations

from ..personas import Classroom
from .backend import pack_payload

TEACHER_KINDS = ("teacher_say", "teacher_action")
STUDENT_KINDS = ("student_say", "student_action")

ANALYSIS_SYSTEM = """당신은 수업 컨설턴트입니다. 교사의 발화 목록을 보고
(1) 발문 수준을 사실확인/절차/원리로 분류해 분포를 요약하고,
(2) 다음 수업에서 바로 실행할 수 있는 개선 제안을 3가지 제시합니다.
마크다운 불릿으로 간결하게 쓰세요. 학생을 평가하지 말고 교사 행동만 다루세요."""


def _stats(transcript_json: list[dict], classroom: Classroom) -> dict:
    ids = [s.id for s in classroom.students]
    names = {s.id: s.name for s in classroom.students}

    teacher_says: list[str] = []
    teacher_actions = 0
    student_say = 0
    student_action = 0
    per_student = {sid: 0 for sid in ids}
    nominate = {sid: 0 for sid in ids}
    individual = {sid: 0 for sid in ids}

    for e in transcript_json:
        kind = e.get("kind")
        actor = e.get("actor")
        content = e.get("content", "") or ""
        meta = e.get("meta") or {}
        if kind == "teacher_say":
            teacher_says.append(content)
        elif kind == "teacher_action":
            teacher_actions += 1
        elif kind == "student_say":
            student_say += 1
            if actor in per_student:
                per_student[actor] += 1
        elif kind == "student_action":
            student_action += 1
            if actor in per_student:
                per_student[actor] += 1

        target = meta.get("target")
        if target in nominate:
            if meta.get("action") == "nominate":
                nominate[target] += 1
            elif meta.get("action") in ("rounds", "praise", "warn"):
                individual[target] += 1

    questions = sum(1 for t in teacher_says if "?" in t)
    silent = [names[sid] for sid in ids if per_student[sid] == 0]

    return {
        "names": names,
        "ids": ids,
        "teacher_says": teacher_says,
        "teacher_say_count": len(teacher_says),
        "teacher_action_count": teacher_actions,
        "student_say_count": student_say,
        "student_action_count": student_action,
        "per_student": per_student,
        "nominate": nominate,
        "individual": individual,
        "questions": questions,
        "silent": silent,
    }


def _llm_section(backend, stats: dict, system=None) -> str:
    if backend is None:
        return "_(백엔드가 없어 발문 분석을 생략했습니다.)_"
    payload = {
        "task": "analysis",
        "teacher_utterances": stats["teacher_says"][:80],
        "question_count": stats["questions"],
        "silent_students": stats["silent"],
    }
    text = (
        "다음은 한 차시 수업에서 교사가 한 발화 목록입니다. 발문 수준을 분류하고 개선점을 제안하세요.\n\n"
        + pack_payload(payload)
    )
    try:
        return backend.complete_text(
            system=system or ANALYSIS_SYSTEM,
            messages=[{"role": "user", "content": text}],
            max_tokens=2048,
            model_role="actor",
        ).strip()
    except Exception as e:  # noqa: BLE001 — 분석 실패가 리포트 전체를 막지 않도록
        return f"_(발문 분석 생성 실패: {e})_"


def analyze(transcript_json: list[dict], classroom: Classroom, backend=None, *, system=None) -> str:
    """전사 + 학급 → 수업 성찰 리포트(마크다운)."""
    s = _stats(transcript_json, classroom)
    names = s["names"]
    total_student = s["student_say_count"] + s["student_action_count"]

    lines: list[str] = []
    lines.append("## 수업 분석 (교사 행동 성찰)")
    lines.append("")
    lines.append("### 발화 분포")
    lines.append("")
    lines.append(f"- 교사 발화: **{s['teacher_say_count']}회** (판서·자료 제시 등 행동 {s['teacher_action_count']}회)")
    lines.append(
        f"- 학생 반응: **{total_student}회** "
        f"(발화 {s['student_say_count']}회 / 행동·침묵 {s['student_action_count']}회)"
    )
    if s["teacher_say_count"]:
        ratio = total_student / s["teacher_say_count"]
        lines.append(f"- 교사 발화 1회당 학생 반응: **{ratio:.2f}회**")
    lines.append(f"- 물음표가 포함된 교사 발화(질문): **{s['questions']}회**")
    lines.append("")

    lines.append("### 학생별 발언 기회 형평성")
    lines.append("")
    lines.append("| 학생 | 성취수준 | 발언·행동 | 지목 | 개별 지도 |")
    lines.append("|---|---|---|---|---|")
    for student in classroom.students:
        sid = student.id
        lines.append(
            f"| {names[sid]} | {student.achievement_level} | {s['per_student'][sid]} "
            f"| {s['nominate'][sid]} | {s['individual'][sid]} |"
        )
    lines.append("")
    if s["silent"]:
        lines.append(f"- ⚠️ **발언 0회 학생**: {', '.join(s['silent'])} ({len(s['silent'])}명)")
    else:
        lines.append("- 모든 학생이 최소 1회 이상 반응했습니다.")

    nominated_total = sum(s["nominate"].values())
    if nominated_total:
        top = sorted(s["nominate"].items(), key=lambda kv: -kv[1])
        top_names = [f"{names[k]} {v}회" for k, v in top if v]
        lines.append(f"- 지목 분포({nominated_total}회): {', '.join(top_names)}")
        if top[0][1] >= max(2, nominated_total * 0.5):
            lines.append(f"- ⚠️ 지목이 **{names[top[0][0]]}**에게 몰려 있습니다.")
    else:
        lines.append("- 이름을 불러 지목한 사례가 없습니다(전체 발화 위주의 수업).")
    lines.append("")

    lines.append("### 발문 수준과 개선 제안")
    lines.append("")
    lines.append(_llm_section(backend, s, system=system))
    lines.append("")
    return "\n".join(lines)
