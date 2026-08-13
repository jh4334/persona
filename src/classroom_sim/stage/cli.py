"""교실 무대 터미널 UI.

    PYTHONPATH=src python -m classroom_sim.stage \\
        --personas personas/class_6_3.json --lesson lessons/ratio_and_rate.md \\
        --backend mock --seed 7
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from ..personas import load_classroom
from .backend import make_backend
from .session import StageSession
from .state import TurnEvent, TurnResult

PROMPT = "👩‍🏫 > "

_BANNER = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 교실 무대 — 실시간 수업 시뮬레이션
 ⚠️ 가상 페르소나 기반 시뮬레이션입니다. 실제 학생 예측이 아닙니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


def format_event(event: TurnEvent, names: dict[str, str]) -> str:
    name = names.get(event.actor, event.actor)
    if event.kind == "student_say":
        return f"💬 {name}: {event.content}"
    if event.kind == "student_action":
        body = event.content
        if not (body.startswith("(") and body.endswith(")")):
            body = f"({body})"
        return f"·  {name}: {body}"
    if event.kind == "teacher_action":
        return f"📝 {event.content}"
    if event.kind == "narration":
        return f"🎬 {event.content}"
    if event.kind == "system":
        if "\n" in event.content:
            return event.content
        return f"ℹ️  {event.content}"
    if event.kind == "teacher_say":
        return f"🗣  선생님: {event.content}"
    return f"   {event.content}"


def print_result(result: TurnResult, names: dict[str, str], *, echo_teacher: bool = False) -> None:
    for event in result.events:
        if event.kind == "teacher_say" and not echo_teacher:
            continue
        print(format_event(event, names))
    if result.events:
        print(f"   [{result.minute}분 · {result.phase} · {result.turn}턴]")


def _save_outputs(session: StageSession, out_dir: Path, lesson_path: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"stage_{lesson_path.stem}_{stamp}"
    report_path = out_dir / f"{stem}.md"
    report_path.write_text(session.end(), encoding="utf-8")
    transcript_path = session.transcript.save(out_dir / f"{stem}_transcript.json")
    return report_path, transcript_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="classroom_sim.stage",
        description="교실 무대 — 교사가 직접 진행하는 실시간 수업 시뮬레이션",
    )
    parser.add_argument("--personas", required=True, help="학급 페르소나 JSON 경로")
    parser.add_argument("--lesson", required=True, help="학습단원 마크다운 경로")
    parser.add_argument("--backend", default="mock", choices=["mock", "anthropic", "codex"],
                        help="LLM 백엔드 (기본: mock — API 키 불필요 / "
                             "codex — ChatGPT 구독으로 로그인한 codex CLI 사용)")
    parser.add_argument("--seed", type=int, default=None, help="mock 백엔드 난수 시드")
    parser.add_argument("--out", default="reports", help="리포트 출력 디렉터리 (기본: reports/)")
    parser.add_argument("--director-model", default="claude-haiku-4-5", help="감독 모델 (anthropic)")
    parser.add_argument("--actor-model", default="claude-opus-5", help="학생/분석 모델 (anthropic)")
    parser.add_argument("--codex-bin", default=None,
                        help="codex 실행 파일 경로 (기본: $CLASSROOM_SIM_CODEX_BIN 또는 codex)")
    parser.add_argument("--codex-model", default=None, help="codex 모델 이름 (생략 시 codex 기본값)")
    parser.add_argument("--codex-timeout", type=int, default=300,
                        help="codex 호출 1회 타임아웃 초 (기본: 300)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    classroom = load_classroom(args.personas)
    lesson_path = Path(args.lesson)
    lesson_text = lesson_path.read_text(encoding="utf-8")

    backend = make_backend(
        args.backend,
        seed=args.seed,
        director_model=args.director_model,
        actor_model=args.actor_model,
        codex_bin=args.codex_bin,
        codex_model=args.codex_model,
        codex_timeout=args.codex_timeout,
    )
    session = StageSession(classroom, lesson_text, backend, seed=args.seed)
    names = {s.id: s.name for s in classroom.students}

    print(_BANNER)
    print(f" 학급: {classroom.class_name} ({len(classroom.students)}명)  |  "
          f"단원: {session.lesson_title()}  |  백엔드: {args.backend}")
    print(" /도움말 로 명령 목록, /상태 로 게이지 표, /종료 로 수업 마감")
    print()

    while True:
        try:
            raw = input(PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw.strip():
            continue

        result = session.turn(raw)
        print_result(result, names)
        print()
        if result.ended:
            break

    report_path, transcript_path = _save_outputs(session, Path(args.out), lesson_path)
    print(f"📄 사후 리포트 저장: {report_path}")
    print(f"🗂  전사 JSON 저장: {transcript_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
