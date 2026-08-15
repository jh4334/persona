from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeAlias

from PIL import Image, ImageDraw

from pixel_assets.palette import Color, TRANSPARENT

Point: TypeAlias = tuple[float, float]
Box: TypeAlias = tuple[float, float, float, float]
SCALE = 4


def scaled(value: float) -> int:
    return round(value * SCALE)


def scaled_box(box: Box) -> tuple[int, int, int, int]:
    return tuple(scaled(value) for value in box)


@dataclass(slots=True)
class Surface:
    image: Image.Image
    draw: ImageDraw.ImageDraw

    @classmethod
    def transparent(cls, width: int, height: int) -> Surface:
        image = Image.new("RGBA", (width * SCALE, height * SCALE), TRANSPARENT)
        return cls(image, ImageDraw.Draw(image))

    @classmethod
    def opaque(cls, width: int, height: int, fill: Color) -> Surface:
        image = Image.new("RGBA", (width * SCALE, height * SCALE), fill)
        return cls(image, ImageDraw.Draw(image))

    def rectangle(self, box: Box, fill: Color, outline: Color | None = None, width: float = 1) -> None:
        self.draw.rectangle(scaled_box(box), fill=fill, outline=outline, width=scaled(width))

    def rounded(self, box: Box, radius: float, fill: Color, outline: Color | None = None, width: float = 1) -> None:
        self.draw.rounded_rectangle(
            scaled_box(box), radius=scaled(radius), fill=fill, outline=outline, width=scaled(width)
        )

    def ellipse(self, box: Box, fill: Color, outline: Color | None = None, width: float = 1) -> None:
        self.draw.ellipse(scaled_box(box), fill=fill, outline=outline, width=scaled(width))

    def polygon(self, points: Iterable[Point], fill: Color, outline: Color | None = None, width: float = 1) -> None:
        coords = [(scaled(x), scaled(y)) for x, y in points]
        self.draw.polygon(coords, fill=fill)
        if outline is not None:
            self.draw.line([*coords, coords[0]], fill=outline, width=scaled(width), joint="curve")

    def line(self, points: Iterable[Point], fill: Color, width: float = 1) -> None:
        self.draw.line(
            [(scaled(x), scaled(y)) for x, y in points], fill=fill, width=scaled(width), joint="curve"
        )
