from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image

from pixel_assets.palette import Color, PALETTE, TRANSPARENT


@dataclass(frozen=True, slots=True)
class AssetSpec:
    filename: str
    size: tuple[int, int]
    frames: int = 1
    transparent: bool = True


@dataclass(frozen=True, slots=True)
class ValidationResult:
    filename: str
    expected_size: tuple[int, int]
    actual_size: tuple[int, int]
    frames: int
    background: str
    color_count: int


@dataclass(frozen=True, slots=True)
class ValidationReport:
    results: tuple[ValidationResult, ...]
    shared_color_count: int


ASSET_SPECS: Final[tuple[AssetSpec, ...]] = (
    AssetSpec("tiles.png", (256, 32), frames=8, transparent=False),
    AssetSpec("blackboard.png", (192, 64)),
    AssetSpec("desk_teacher.png", (64, 48)),
    AssetSpec("desk_student.png", (40, 40)),
    AssetSpec("char_teacher.png", (64, 48), frames=2),
    *(AssetSpec(f"char_s{index:02}.png", (64, 48), frames=2) for index in range(1, 13)),
    AssetSpec("emotes.png", (128, 16), frames=8),
)


def save_asset(image: Image.Image, path: Path) -> None:
    image.save(path, format="PNG", compress_level=9)


def _rgba_colors(image: Image.Image) -> frozenset[Color]:
    rgba_image = image.convert("RGBA")
    return frozenset(rgba_image.getdata())


def _validate_alpha(image: Image.Image, spec: AssetSpec) -> str:
    alpha_values = frozenset(pixel[3] for pixel in image.getdata())
    if not alpha_values <= {0, 255}:
        msg = f"{spec.filename}: semi-transparent pixels found"
        raise RuntimeError(msg)
    if spec.transparent:
        if 0 not in alpha_values:
            msg = f"{spec.filename}: transparent background missing"
            raise RuntimeError(msg)
        corners = ((0, 0), (image.width - 1, 0), (0, image.height - 1), (image.width - 1, image.height - 1))
        if any(image.getpixel(point) != TRANSPARENT for point in corners):
            msg = f"{spec.filename}: background corners are not transparent"
            raise RuntimeError(msg)
        return "transparent"
    if alpha_values != {255}:
        msg = f"{spec.filename}: tile sheet must be fully opaque"
        raise RuntimeError(msg)
    return "opaque"


def _validate_frames(image: Image.Image, spec: AssetSpec) -> None:
    frame_width = image.width // spec.frames
    if frame_width * spec.frames != image.width:
        msg = f"{spec.filename}: width is not divisible by frame count"
        raise RuntimeError(msg)
    if spec.frames == 2:
        first = image.crop((0, 0, frame_width, image.height))
        second = image.crop((frame_width, 0, image.width, image.height))
        if first.getbbox() is None or second.getbbox() is None or first.tobytes() == second.tobytes():
            msg = f"{spec.filename}: two distinct non-empty idle frames required"
            raise RuntimeError(msg)


def validate_assets(output_dir: Path) -> ValidationReport:
    results: list[ValidationResult] = []
    union_colors: set[Color] = set()
    for spec in ASSET_SPECS:
        path = output_dir / spec.filename
        if not path.is_file():
            msg = f"missing asset: {path}"
            raise RuntimeError(msg)
        with Image.open(path) as image:
            image.load()
            if image.format != "PNG" or image.mode != "RGBA":
                msg = f"{spec.filename}: expected RGBA PNG, got {image.format}/{image.mode}"
                raise RuntimeError(msg)
            if image.size != spec.size:
                msg = f"{spec.filename}: expected {spec.size}, got {image.size}"
                raise RuntimeError(msg)
            colors = _rgba_colors(image)
            unknown = colors - PALETTE
            if unknown:
                msg = f"{spec.filename}: colors outside shared palette: {sorted(unknown)}"
                raise RuntimeError(msg)
            background = _validate_alpha(image, spec)
            _validate_frames(image, spec)
            union_colors.update(colors)
            results.append(
                ValidationResult(
                    filename=spec.filename,
                    expected_size=spec.size,
                    actual_size=image.size,
                    frames=spec.frames,
                    background=background,
                    color_count=len(colors),
                )
            )
    if len(union_colors) > 32:
        msg = f"shared palette exceeds 32 colors: {len(union_colors)}"
        raise RuntimeError(msg)
    return ValidationReport(tuple(results), len(union_colors))
