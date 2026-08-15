#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow>=11.0"]
# ///

from __future__ import annotations

from pathlib import Path
from typing import Final

from PIL import Image

from pixel_assets.character_specs import STUDENTS, TEACHER
from vector_assets.characters import make_character
from vector_assets.classroom import make_blackboard, make_student_desk, make_teacher_desk, make_tiles
from vector_assets.emotes import make_emotes
from vector_assets.specs import ValidationResult, save_asset, validate_assets

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
OUTPUT_DIR: Final[Path] = REPOSITORY_ROOT / "src/classroom_sim/web/static/assets/vector"


def generated_assets() -> tuple[tuple[str, Image.Image], ...]:
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


def size_text(size: tuple[int, int]) -> str:
    return f"{size[0]}×{size[1]}"


def print_report(results: tuple[ValidationResult, ...]) -> None:
    print("| 파일 | 예상 크기 | 실제 크기 | 프레임 | 배경 | 색상 수 | 결과 |")
    print("|---|---:|---:|---:|---|---:|---|")
    for result in results:
        print(
            f"| {result.filename} | {size_text(result.expected_size)} | "
            f"{size_text(result.actual_size)} | {result.frames} | {result.background} | "
            f"{result.color_count} | PASS |"
        )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assets = generated_assets()
    if len(assets) != 18:
        raise RuntimeError(f"expected 18 assets, generated {len(assets)}")
    for filename, image in assets:
        save_asset(image, OUTPUT_DIR / filename)
    print_report(validate_assets(OUTPUT_DIR))


if __name__ == "__main__":
    main()
