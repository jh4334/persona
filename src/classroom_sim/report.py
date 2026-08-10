"""시뮬레이션 결과 → 마크다운 리포트 생성."""

from __future__ import annotations

from datetime import datetime

from .personas import Classroom
from .simulate import StudentResult

_BAR = {1: "█", 2: "██", 3: "███", 4: "████", 5: "█████"}


def _bar(v: int) -> str:
    return f"{_BAR.get(v, '')} {v}/5" if v else "—"


def build_report(
    classroom: Classroom,
    lesson_title: str,
    results: list[StudentResult],
    class_insights: str | None = None,
    generated_at: str | None = None,
) -> str:
    ok = [r for r in results if not r.error]
    failed = [r for r in results if r.error]

    lines: list[str] = []
    lines.append(f"# 수업 반응 시뮬레이션 리포트")
    lines.append("")
    lines.append(f"- **학급**: {classroom.class_name} ({classroom.grade}, {len(results)}명)")
    lines.append(f"- **학습단원**: {lesson_title}")
    if generated_at is None:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"- **생성 일시**: {generated_at}")
    lines.append("")
    lines.append(
        "> ⚠️ 이 리포트는 AI가 가상 페르소나를 기반으로 생성한 **예측 시뮬레이션**입니다. "
        "실제 학생의 반응을 보장하지 않으며, 수업 설계의 참고 자료로만 활용하세요."
    )
    lines.append("")

    # 요약 표
    lines.append("## 한눈에 보기")
    lines.append("")
    lines.append("| 학생 | 성취수준 | 예상 이해도 | 예상 흥미도 | 핵심 난점 |")
    lines.append("|---|---|---|---|---|")
    for r in ok:
        top_difficulty = r.difficulties[0] if r.difficulties else "—"
        lines.append(
            f"| {r.student.name} | {r.student.achievement_level} "
            f"| {_bar(r.comprehension)} | {_bar(r.engagement)} | {top_difficulty} |"
        )
    lines.append("")

    if ok:
        avg_c = sum(r.comprehension for r in ok) / len(ok)
        avg_e = sum(r.engagement for r in ok) / len(ok)
        low_c = [r.student.name for r in ok if r.comprehension <= 2]
        low_e = [r.student.name for r in ok if r.engagement <= 2]
        lines.append(f"- 학급 평균 예상 이해도: **{avg_c:.1f}/5**, 예상 흥미도: **{avg_e:.1f}/5**")
        if low_c:
            lines.append(f"- 이해도 우려 학생: **{', '.join(low_c)}**")
        if low_e:
            lines.append(f"- 흥미도 우려 학생: **{', '.join(low_e)}**")
        lines.append("")

    if class_insights:
        lines.append("## 학급 종합 분석 및 수업 조정 제안")
        lines.append("")
        lines.append(class_insights)
        lines.append("")

    # 학생별 상세
    lines.append("## 학생별 상세 예측")
    lines.append("")
    for r in ok:
        s = r.student
        lines.append(f"### {s.name} ({s.id}, 성취수준 {s.achievement_level})")
        lines.append("")
        lines.append(f"**예상 이해도** {_bar(r.comprehension)} · **예상 흥미도** {_bar(r.engagement)}")
        lines.append("")
        lines.append(f"**예상 반응**: {r.predicted_reaction}")
        lines.append("")
        if r.voice_sample:
            lines.append(f"> 💬 \"{r.voice_sample}\"")
            lines.append("")
        if r.likely_questions:
            lines.append("**예상 질문**")
            lines.extend(f"- {q}" for q in r.likely_questions)
            lines.append("")
        if r.misconceptions:
            lines.append("**예상 오개념**")
            lines.extend(f"- {m}" for m in r.misconceptions)
            lines.append("")
        if r.difficulties:
            lines.append("**예상 난점**")
            lines.extend(f"- {d}" for d in r.difficulties)
            lines.append("")
        if r.teaching_strategies:
            lines.append("**맞춤 지도 전략**")
            lines.extend(f"- {t}" for t in r.teaching_strategies)
            lines.append("")

    if failed:
        lines.append("## 시뮬레이션 실패 학생")
        lines.append("")
        for r in failed:
            lines.append(f"- {r.student.name}: {r.error}")
        lines.append("")

    return "\n".join(lines)
