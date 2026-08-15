from __future__ import annotations

from PIL import Image

from pixel_assets.palette import BLUE, BLUE_DARK, CREAM, DARK, PINK, RED, SKIN_MEDIUM, WHITE, YELLOW
from vector_assets.drawing import Surface


def _hand(surface: Surface, x: int) -> None:
    surface.rounded((x + 6, 4, x + 10, 14), 2, SKIN_MEDIUM, WHITE, 0.8)
    for left, top in ((4, 5), (6, 2), (8, 1), (10, 3), (12, 5)):
        surface.rounded((x + left, top, x + left + 2.2, top + 7), 1, SKIN_MEDIUM, WHITE, 0.7)


def _sleep(surface: Surface, x: int) -> None:
    surface.line(((x + 3, 5), (x + 9, 5), (x + 3, 11), (x + 9, 11)), BLUE, 1.5)
    surface.line(((x + 9, 2), (x + 14, 2), (x + 10, 6), (x + 14, 6)), WHITE, 1)


def _question(surface: Surface, x: int) -> None:
    surface.rounded((x + 4, 1, x + 12, 11), 4, CREAM, WHITE, 0.8)
    surface.line(((x + 6, 4), (x + 8, 2.7), (x + 10.5, 4), (x + 8, 7), (x + 8, 9)), BLUE_DARK, 1.4)
    surface.ellipse((x + 7, 12, x + 9, 14), BLUE_DARK, WHITE, 0.4)


def _spark(surface: Surface, x: int) -> None:
    surface.polygon(((x + 8, 0), (x + 10, 6), (x + 16, 8), (x + 10, 10), (x + 8, 16), (x + 6, 10), (x, 8), (x + 6, 6)), YELLOW, WHITE, 0.7)
    surface.polygon(((x + 3, 1), (x + 4, 3), (x + 6, 4), (x + 4, 5), (x + 3, 7), (x + 2, 5), (x, 4), (x + 2, 3)), WHITE)


def _anxious(surface: Surface, x: int) -> None:
    surface.polygon(((x + 8, 1), (x + 13, 9), (x + 11, 14), (x + 5, 14), (x + 3, 9)), BLUE, WHITE, 0.8)
    surface.ellipse((x + 6, 5, x + 8, 8), WHITE)


def _chat(surface: Surface, x: int) -> None:
    surface.rounded((x + 1, 2, x + 15, 12), 4, WHITE, BLUE_DARK, 0.8)
    surface.polygon(((x + 5, 11), (x + 4, 15), (x + 9, 11)), WHITE, BLUE_DARK, 0.6)
    for center in (5, 8, 11):
        surface.ellipse((x + center - 0.8, 6, x + center + 0.8, 7.6), BLUE_DARK)


def _bored(surface: Surface, x: int) -> None:
    surface.rounded((x + 1, 3, x + 15, 13), 4, CREAM, WHITE, 0.8)
    surface.line(((x + 4, 7), (x + 7, 8)), DARK, 1.2)
    surface.line(((x + 9, 8), (x + 12, 7)), DARK, 1.2)
    surface.line(((x + 6, 11), (x + 10, 11)), DARK, 0.9)


def _excited(surface: Surface, x: int) -> None:
    surface.ellipse((x + 4, 4, x + 12, 12), RED, WHITE, 0.8)
    for start, end in (
        (((x + 8), 0), ((x + 8), 3)),
        (((x + 8), 13), ((x + 8), 16)),
        (((x + 0), 8), ((x + 3), 8)),
        (((x + 13), 8), ((x + 16), 8)),
        (((x + 2), 2), ((x + 4), 4)),
        (((x + 12), 12), ((x + 14), 14)),
    ):
        surface.line((start, end), YELLOW, 1.2)
    surface.ellipse((x + 6, 6, x + 8, 9), WHITE)
    surface.ellipse((x + 9, 6, x + 11, 9), WHITE)


def make_emotes() -> Image.Image:
    surface = Surface.transparent(128, 16)
    drawers = (_hand, _sleep, _question, _spark, _anxious, _chat, _bored, _excited)
    for index, drawer in enumerate(drawers):
        drawer(surface, index * 16)
    return surface.image
