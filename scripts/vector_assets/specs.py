from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image

from vector_assets.drawing import SCALE


@dataclass(frozen=True, slots=True)
class AssetSpec:
    filename: str
    logical_size: tuple[int, int]
    frames: int = 1
    transparent: bool = True

    @property
    def size(self) -> tuple[int, int]:
        return self.logical_size[0] * SCALE, self.logical_size[1] * SCALE


@dataclass(frozen=True, slots=True)
class ValidationResult:
    filename: str
    expected_size: tuple[int, int]
    actual_size: tuple[int, int]
    frames: int
    background: str
    color_count: int


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


def validate_assets(output_dir: Path) -> tuple[ValidationResult, ...]:
    results: list[ValidationResult] = []
    for spec in ASSET_SPECS:
        path = output_dir / spec.filename
        if not path.is_file():
            raise RuntimeError(f"missing asset: {path}")
        with Image.open(path) as image:
            image.load()
            if image.format != "PNG" or image.mode != "RGBA":
                raise RuntimeError(f"{spec.filename}: expected RGBA PNG, got {image.format}/{image.mode}")
            if image.size != spec.size:
                raise RuntimeError(f"{spec.filename}: expected {spec.size}, got {image.size}")
            alpha_values = frozenset(image.getchannel("A").getdata())
            if spec.transparent:
                if 0 not in alpha_values or 255 not in alpha_values:
                    raise RuntimeError(f"{spec.filename}: transparent and opaque pixels are required")
                background = "투명"
            else:
                if alpha_values != {255}:
                    raise RuntimeError(f"{spec.filename}: tile sheet must be opaque")
                background = "불투명"
            if spec.frames == 2:
                frame_width = image.width // 2
                first = image.crop((0, 0, frame_width, image.height))
                second = image.crop((frame_width, 0, image.width, image.height))
                if first.tobytes() == second.tobytes():
                    raise RuntimeError(f"{spec.filename}: distinct breathing frames are required")
            results.append(
                ValidationResult(
                    spec.filename,
                    spec.size,
                    image.size,
                    spec.frames,
                    background,
                    len(image.getcolors(maxcolors=image.width * image.height) or ()),
                )
            )
    return tuple(results)
