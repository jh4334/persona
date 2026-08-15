from __future__ import annotations

from PIL import Image

from pixel_assets.palette import (
    BLUE,
    BLUE_DARK,
    BOARD,
    BOARD_LIGHT,
    CREAM,
    CREAM_SHADE,
    DARK,
    FLOOR,
    FLOOR_DARK,
    FLOOR_LIGHT,
    GREEN,
    MINT,
    ORANGE,
    PINK,
    RED,
    SKY,
    WHITE,
    WOOD,
    WOOD_DARK,
    WOOD_LIGHT,
    YELLOW,
)
from vector_assets.drawing import Surface


def _floor(surface: Surface, offset: int, knot: bool) -> None:
    surface.rectangle((offset, 0, offset + 32, 32), FLOOR)
    for row in range(4):
        y = row * 8
        surface.line(((offset, y + 7.8), (offset + 32, y + 7.8)), FLOOR_DARK, 0.5)
        seam = offset + ((row * 13) % 31)
        surface.line(((seam, y), (seam, y + 7.8)), FLOOR_DARK, 0.45)
        surface.line(((offset + 4, y + 2), (offset + 13, y + 1.5)), FLOOR_LIGHT, 0.45)
    if knot:
        surface.ellipse((offset + 21, 9, offset + 26, 13), FLOOR_DARK)
        surface.ellipse((offset + 22, 10, offset + 25, 12), WOOD_DARK)


def _wall(surface: Surface, offset: int) -> None:
    surface.rectangle((offset, 0, offset + 32, 32), CREAM)
    surface.rectangle((offset, 24, offset + 32, 32), CREAM_SHADE)
    surface.rectangle((offset, 23, offset + 32, 25), WOOD_LIGHT)
    surface.line(((offset, 25), (offset + 32, 25)), WOOD_DARK, 0.6)


def _window(surface: Surface, offset: int) -> None:
    surface.rectangle((offset, 0, offset + 32, 32), CREAM)
    surface.rounded((offset + 3, 2, offset + 29, 27), 1.5, WHITE, WOOD_DARK, 0.8)
    surface.rectangle((offset + 6, 5, offset + 26, 23), SKY)
    surface.ellipse((offset + 7, 9, offset + 17, 13), WHITE)
    surface.ellipse((offset + 13, 7, offset + 23, 13), WHITE)
    surface.ellipse((offset + 7, 17, offset + 18, 25), GREEN)
    surface.ellipse((offset + 16, 15, offset + 27, 25), MINT)
    surface.rectangle((offset + 15, 5, offset + 17, 23), WHITE)
    surface.rectangle((offset + 6, 13, offset + 26, 15), WHITE)
    surface.rounded((offset + 2, 25, offset + 30, 29), 1, CREAM_SHADE, WOOD_DARK, 0.6)


def _noticeboard(surface: Surface, offset: int) -> None:
    surface.rectangle((offset, 0, offset + 32, 32), CREAM)
    surface.rounded((offset + 2, 4, offset + 30, 28), 1.5, WOOD_LIGHT, WOOD_DARK, 1)
    for color, box in (
        (WHITE, (6, 8, 14, 16)),
        (PINK, (17, 7, 26, 14)),
        (YELLOW, (8, 19, 16, 26)),
        (MINT, (19, 17, 27, 25)),
    ):
        x1, y1, x2, y2 = box
        surface.rounded((offset + x1, y1, offset + x2, y2), 0.6, color)
        surface.ellipse((offset + x1 + 3, y1 + 1, offset + x1 + 4, y1 + 2), RED)


def _locker(surface: Surface, offset: int) -> None:
    surface.rectangle((offset, 0, offset + 32, 32), CREAM_SHADE)
    surface.rounded((offset + 2, 2, offset + 30, 32), 1.5, BLUE, BLUE_DARK, 0.8)
    for left in (4, 13, 22):
        surface.rounded((offset + left, 4, offset + left + 7, 30), 1, BLUE, BLUE_DARK, 0.6)
        surface.ellipse((offset + left + 4.5, 17, offset + left + 5.8, 18.3), YELLOW)


def _plant(surface: Surface, offset: int) -> None:
    surface.rectangle((offset, 0, offset + 32, 32), CREAM)
    surface.rectangle((offset, 25, offset + 32, 32), CREAM_SHADE)
    surface.line(((offset + 16, 9), (offset + 16, 23)), BOARD, 1)
    for box, color in (
        ((5, 7, 16, 16), GREEN),
        ((15, 4, 27, 14), MINT),
        ((10, 1, 21, 12), BOARD_LIGHT),
        ((9, 12, 18, 20), GREEN),
        ((17, 11, 27, 19), BOARD_LIGHT),
    ):
        x1, y1, x2, y2 = box
        surface.ellipse((offset + x1, y1, offset + x2, y2), color, BOARD, 0.45)
    surface.polygon(((offset + 9, 20), (offset + 23, 20), (offset + 20, 30), (offset + 12, 30)), ORANGE, WOOD_DARK, 0.7)


def _door(surface: Surface, offset: int) -> None:
    surface.rectangle((offset, 0, offset + 32, 32), CREAM)
    surface.rounded((offset + 4, 1, offset + 29, 33), 1, WOOD, WOOD_DARK, 1)
    surface.rounded((offset + 8, 5, offset + 25, 16), 1, WOOD_LIGHT, WOOD_DARK, 0.6)
    surface.rectangle((offset + 10, 7, offset + 23, 14), SKY)
    surface.rounded((offset + 8, 20, offset + 25, 30), 1, FLOOR_DARK, WOOD_DARK, 0.6)
    surface.ellipse((offset + 23, 17, offset + 25, 19), YELLOW, DARK, 0.45)


def make_tiles() -> Image.Image:
    surface = Surface.opaque(256, 32, FLOOR)
    _floor(surface, 0, False)
    _floor(surface, 32, True)
    _wall(surface, 64)
    _window(surface, 96)
    _noticeboard(surface, 128)
    _locker(surface, 160)
    _plant(surface, 192)
    _door(surface, 224)
    return surface.image


def make_blackboard() -> Image.Image:
    surface = Surface.transparent(192, 64)
    surface.rounded((2, 2, 190, 58), 3, WOOD_DARK, DARK, 1)
    surface.rounded((6, 5, 186, 54), 2, WOOD_LIGHT, WOOD_DARK, 0.8)
    surface.rounded((9, 8, 183, 51), 1.5, BOARD, DARK, 0.7)
    surface.line(((12, 11), (180, 11)), BOARD_LIGHT, 0.8)
    surface.polygon(((1, 55), (191, 55), (187, 63), (6, 63)), WOOD_LIGHT, WOOD_DARK, 0.8)
    surface.rounded((145, 55, 160, 58), 1, WHITE, CREAM_SHADE, 0.5)
    surface.rounded((163, 55, 173, 58), 1, YELLOW, CREAM_SHADE, 0.5)
    return surface.image


def make_teacher_desk() -> Image.Image:
    surface = Surface.transparent(64, 48)
    surface.ellipse((7, 35, 60, 46), (73, 61, 57, 70))
    surface.polygon(((7, 12), (47, 7), (60, 15), (18, 23)), WOOD_LIGHT, WOOD_DARK, 1)
    surface.polygon(((7, 12), (18, 23), (18, 41), (7, 31)), WOOD_DARK, DARK, 0.8)
    surface.polygon(((18, 23), (60, 15), (60, 36), (18, 43)), WOOD, WOOD_DARK, 0.8)
    surface.rounded((20, 36, 26, 48), 1.4, WOOD_DARK, DARK, 0.6)
    surface.rounded((51, 33, 57, 44), 1.4, WOOD_DARK, DARK, 0.6)
    surface.polygon(((18, 11), (38, 9), (42, 13), (22, 16)), BLUE_DARK, DARK, 0.6)
    surface.polygon(((20, 10), (37, 9), (39, 11), (22, 13)), CREAM)
    surface.rounded((45, 7, 53, 15), 2, WHITE, CREAM_SHADE, 0.6)
    surface.line(((49, 8), (49, 12)), YELLOW, 0.8)
    return surface.image


def make_student_desk() -> Image.Image:
    surface = Surface.transparent(40, 40)
    surface.ellipse((4, 30, 38, 39), (73, 61, 57, 70))
    surface.rounded((12, 4, 28, 19), 2, WOOD, WOOD_DARK, 0.8)
    surface.rounded((13.5, 17, 17, 29), 1, WOOD_DARK, DARK, 0.5)
    surface.rounded((24, 17, 27.5, 29), 1, WOOD_DARK, DARK, 0.5)
    surface.polygon(((3, 15), (28, 10), (38, 17), (13, 25)), WOOD_LIGHT, WOOD_DARK, 0.9)
    surface.polygon(((3, 15), (13, 25), (13, 30), (3, 21)), WOOD_DARK, DARK, 0.7)
    surface.polygon(((13, 25), (38, 17), (38, 23), (13, 31)), WOOD, WOOD_DARK, 0.7)
    surface.rounded((8, 26, 12, 40), 1.3, WOOD_DARK, DARK, 0.6)
    surface.rounded((31, 23, 35, 37), 1.3, WOOD_DARK, DARK, 0.6)
    return surface.image
