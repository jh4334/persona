"""CLI 진입점.

사용 예:
    export ANTHROPIC_API_KEY=sk-ant-...
    python -m classroom_sim --personas personas/class_6_3.json \
        --lesson lessons/ratio_and_rate.md --out reports/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .personas import load_classroom
from .report import build_report
from .simulate import StudentResult, simulate_classroom, synthesize_class_insights


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="classroom_sim",
        description="학생 페르소나 기반 수업 반응 시뮬레이터",
    )
    parser.add_argument("--personas", required=True, help="학급 페르소나 JSON 파일 경로")
    parser.add_argument("--lesson", required=True, help="학습단원 마크다운 파일 경로")
    parser.add_argument("--out", default="reports", help="리포트 출력 디렉터리 (기본: reports/)")
    parser.add_argument("--workers", type=int, default=4, help="동시 요청 수 (기본: 4)")
    parser.add_argument(
        "--no-synthesis", action="store_true",
        help="학급 종합 분석(추가 API 호출 1회)을 생략",
    )
    args = parser.parse_args()

    classroom = load_classroom(args.personas)
    lesson_path = Path(args.lesson)
    lesson_text = lesson_path.read_text(encoding="utf-8")
    lesson_title = lesson_text.splitlines()[0].lstrip("# ").strip() or lesson_path.stem

    print(f"학급: {classroom.class_name} — 학생 {len(classroom.students)}명")
    print(f"단원: {lesson_title}")
    print("시뮬레이션 시작...\n")

    def on_progress(r: StudentResult) -> None:
        if r.error:
            print(f"  ✗ {r.student.name}: {r.error}")
        else:
            print(f"  ✓ {r.student.name}: 이해도 {r.comprehension}/5, 흥미 {r.engagement}/5")

    results = simulate_classroom(
        classroom, lesson_text, max_workers=args.workers, on_progress=on_progress
    )

    insights = None
    if not args.no_synthesis and any(not r.error for r in results):
        print("\n학급 종합 분석 생성 중...")
        insights = synthesize_class_insights(classroom, lesson_text, results)

    report = build_report(classroom, lesson_title, results, class_insights=insights)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{lesson_path.stem}_report.md"
    out_path.write_text(report, encoding="utf-8")

    print(f"\n리포트 저장 완료: {out_path}")
    failed = sum(1 for r in results if r.error)
    if failed:
        print(f"주의: {failed}명 시뮬레이션 실패 (리포트 하단 참조)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
