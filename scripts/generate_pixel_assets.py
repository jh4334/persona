#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pillow>=11.0",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/generate_pixel_assets.py
# 3. Or make executable and run:
#      chmod +x scripts/generate_pixel_assets.py && ./scripts/generate_pixel_assets.py
# ──────────────────

from __future__ import annotations

from pathlib import Path
from typing import Final

from PIL import Image

from pixel_assets.character_specs import STUDENTS, TEACHER
from pixel_assets.characters import make_character
from pixel_assets.classroom import make_blackboard, make_student_desk, make_teacher_desk, make_tiles
from pixel_assets.emotes import make_emotes
from pixel_assets.specs import ValidationResult, save_asset, validate_assets

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
OUTPUT_DIR: Final[Path] = REPOSITORY_ROOT / "src/classroom_sim/web/static/assets"


def _generated_assets() -> tuple[tuple[str, Image.Image], ...]:
    characters = ((TEACHER.filename, make_character(TEACHER)),) + tuple(
        (student.filename, make_character(student)) for student in STUDENTS
    )
    return (
        ("tiles.png", make_tiles()),
        ("blackboard.png", make_blackboard()),
        ("desk_teacher.png", make_teacher_desk()),
        ("desk_student.png", make_student_desk()),
        *characters,
        ("emotes.png", make_emotes()),
    )


def _size_text(size: tuple[int, int]) -> str:
    return f"{size[0]}×{size[1]}"


def _print_report(results: tuple[ValidationResult, ...], shared_colors: int) -> None:
    print("| 파일 | 예상 크기 | 실제 크기 | 프레임 | 배경 | 색상 수 | 결과 |")
    print("|---|---:|---:|---:|---|---:|---|")
    for result in results:
        print(
            f"| {result.filename} | {_size_text(result.expected_size)} | "
            f"{_size_text(result.actual_size)} | {result.frames} | {result.background} | "
            f"{result.color_count} | PASS |"
        )
    print(f"\n공유 팔레트: {shared_colors}/32색 (투명색 포함), 반투명 픽셀: 없음")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assets = _generated_assets()
    if len(assets) != 18:
        msg = f"expected 18 assets, generated {len(assets)}"
        raise RuntimeError(msg)
    for filename, image in assets:
        save_asset(image, OUTPUT_DIR / filename)
    report = validate_assets(OUTPUT_DIR)
    _print_report(report.results, report.shared_color_count)


if __name__ == "__main__":
    main()
