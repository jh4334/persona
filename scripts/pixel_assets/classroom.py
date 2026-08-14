from __future__ import annotations

from PIL import Image, ImageDraw

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
    TRANSPARENT,
    WHITE,
    WOOD,
    WOOD_DARK,
    WOOD_LIGHT,
    YELLOW,
)


def _floor_tile(draw: ImageDraw.ImageDraw, x: int, knot: bool) -> None:
    draw.rectangle((x, 0, x + 31, 31), fill=FLOOR)
    for y in (7, 15, 23, 31):
        draw.line((x, y, x + 31, y), fill=FLOOR_DARK)
    for row, shift in enumerate((0, 13, 5, 20)):
        y = row * 8
        draw.line((x + shift, y, x + shift, y + 7), fill=FLOOR_DARK)
        draw.line((x + shift + 1, y + 1, x + shift + 1, y + 6), fill=FLOOR_LIGHT)
    draw.line((x + 3, 3, x + 11, 3), fill=FLOOR_LIGHT)
    draw.line((x + 20, 19, x + 27, 19), fill=FLOOR_LIGHT)
    if knot:
        draw.rectangle((x + 22, 10, x + 25, 12), fill=FLOOR_DARK)
        draw.rectangle((x + 23, 10, x + 24, 11), fill=WOOD_DARK)


def _wall_tile(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.rectangle((x, 0, x + 31, 31), fill=CREAM)
    draw.rectangle((x, 24, x + 31, 31), fill=CREAM_SHADE)
    draw.line((x, 23, x + 31, 23), fill=WOOD_LIGHT)
    draw.line((x, 31, x + 31, 31), fill=WOOD_DARK)
    draw.rectangle((x + 3, 5, x + 4, 6), fill=WHITE)
    draw.rectangle((x + 25, 14, x + 27, 15), fill=WHITE)


def _window_tile(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.rectangle((x, 0, x + 31, 31), fill=CREAM)
    draw.rectangle((x + 3, 3, x + 28, 25), fill=WOOD_DARK)
    draw.rectangle((x + 5, 5, x + 26, 23), fill=SKY)
    draw.rectangle((x + 8, 9, x + 13, 11), fill=WHITE)
    draw.rectangle((x + 11, 7, x + 18, 11), fill=WHITE)
    draw.rectangle((x + 15, 9, x + 22, 12), fill=WHITE)
    draw.rectangle((x + 15, 14, x + 16, 23), fill=WOOD_LIGHT)
    draw.rectangle((x + 5, 14, x + 26, 15), fill=WOOD_LIGHT)
    draw.rectangle((x + 2, 25, x + 29, 28), fill=WOOD_LIGHT)
    draw.line((x + 3, 28, x + 28, 28), fill=WOOD_DARK)
    draw.rectangle((x, 29, x + 31, 31), fill=CREAM_SHADE)


def _noticeboard_tile(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.rectangle((x, 0, x + 31, 31), fill=CREAM)
    draw.rectangle((x + 2, 4, x + 29, 27), fill=WOOD_DARK)
    draw.rectangle((x + 4, 6, x + 27, 25), fill=WOOD_LIGHT)
    draw.rectangle((x + 6, 8, x + 13, 16), fill=WHITE)
    draw.rectangle((x + 7, 9, x + 12, 10), fill=BLUE)
    draw.rectangle((x + 16, 7, x + 24, 13), fill=PINK)
    draw.rectangle((x + 17, 9, x + 23, 10), fill=WHITE)
    draw.polygon(((x + 9, 19), (x + 15, 18), (x + 16, 24), (x + 8, 24)), fill=YELLOW)
    draw.rectangle((x + 19, 16, x + 25, 23), fill=MINT)
    for px, py in ((7, 8), (17, 7), (10, 19), (20, 16)):
        draw.point((x + px, py), fill=RED)


def _locker_tile(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.rectangle((x, 0, x + 31, 31), fill=CREAM_SHADE)
    draw.rectangle((x + 2, 2, x + 29, 31), fill=BOARD)
    for left in (4, 13, 22):
        draw.rectangle((x + left, 4, x + left + 6, 29), fill=GREEN)
        draw.line((x + left + 6, 4, x + left + 6, 29), fill=BOARD_LIGHT)
        draw.rectangle((x + left + 2, 7, x + left + 4, 8), fill=CREAM_SHADE)
        draw.point((x + left + 4, 17), fill=YELLOW)
    draw.line((x + 2, 30, x + 29, 30), fill=WOOD_DARK)


def _plant_tile(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.rectangle((x, 0, x + 31, 31), fill=CREAM)
    draw.rectangle((x, 25, x + 31, 31), fill=CREAM_SHADE)
    draw.rectangle((x + 14, 10, x + 16, 23), fill=BOARD)
    draw.ellipse((x + 5, 5, x + 15, 14), fill=GREEN)
    draw.ellipse((x + 16, 3, x + 26, 13), fill=MINT)
    draw.ellipse((x + 10, 1, x + 20, 11), fill=BOARD_LIGHT)
    draw.polygon(((x + 9, 19), (x + 23, 19), (x + 20, 29), (x + 12, 29)), fill=ORANGE)
    draw.line((x + 11, 20, x + 21, 20), fill=YELLOW)
    draw.line((x + 12, 29, x + 20, 29), fill=WOOD_DARK)


def _door_tile(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.rectangle((x, 0, x + 31, 31), fill=CREAM)
    draw.rectangle((x + 4, 1, x + 28, 31), fill=WOOD_DARK)
    draw.rectangle((x + 6, 3, x + 26, 31), fill=WOOD)
    draw.rectangle((x + 9, 6, x + 23, 16), fill=WOOD_LIGHT)
    draw.rectangle((x + 9, 20, x + 23, 29), fill=FLOOR_DARK)
    draw.rectangle((x + 11, 8, x + 21, 14), fill=SKY)
    draw.point((x + 23, 18), fill=YELLOW)
    draw.point((x + 24, 18), fill=WHITE)


def make_tiles() -> Image.Image:
    image = Image.new("RGBA", (256, 32), FLOOR)
    draw = ImageDraw.Draw(image)
    _floor_tile(draw, 0, False)
    _floor_tile(draw, 32, True)
    _wall_tile(draw, 64)
    _window_tile(draw, 96)
    _noticeboard_tile(draw, 128)
    _locker_tile(draw, 160)
    _plant_tile(draw, 192)
    _door_tile(draw, 224)
    return image


def make_blackboard() -> Image.Image:
    image = Image.new("RGBA", (192, 64), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 3, 189, 57), fill=WOOD_DARK)
    draw.rectangle((5, 5, 186, 54), fill=WOOD_LIGHT)
    draw.rectangle((8, 8, 183, 52), fill=BOARD)
    draw.line((9, 9, 182, 9), fill=BOARD_LIGHT)
    draw.line((9, 51, 182, 51), fill=DARK)
    draw.rectangle((0, 56, 191, 60), fill=WOOD_DARK)
    draw.polygon(((3, 56), (188, 56), (184, 62), (7, 62)), fill=WOOD_LIGHT)
    draw.rectangle((145, 56, 158, 57), fill=WHITE)
    draw.rectangle((161, 56, 169, 57), fill=YELLOW)
    return image


def make_teacher_desk() -> Image.Image:
    image = Image.new("RGBA", (64, 48), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    draw.polygon(((7, 12), (47, 7), (59, 15), (18, 22)), fill=WOOD_LIGHT)
    draw.polygon(((7, 12), (18, 22), (18, 40), (7, 31)), fill=WOOD_DARK)
    draw.polygon(((18, 22), (59, 15), (59, 35), (18, 42)), fill=WOOD)
    draw.line((20, 25, 56, 19), fill=FLOOR_LIGHT)
    draw.rectangle((21, 36, 26, 47), fill=WOOD_DARK)
    draw.rectangle((51, 33, 56, 43), fill=WOOD_DARK)
    draw.polygon(((18, 11), (37, 9), (41, 13), (22, 16)), fill=BLUE_DARK)
    draw.polygon(((20, 10), (37, 9), (39, 11), (22, 13)), fill=CREAM)
    draw.rectangle((45, 8, 52, 14), fill=WHITE)
    draw.rectangle((46, 7, 51, 8), fill=CREAM_SHADE)
    draw.rectangle((52, 9, 54, 12), fill=WHITE)
    return image


def make_student_desk() -> Image.Image:
    image = Image.new("RGBA", (40, 40), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 4, 27, 18), fill=WOOD_DARK)
    draw.rectangle((14, 5, 25, 16), fill=WOOD)
    draw.rectangle((14, 17, 16, 27), fill=WOOD_DARK)
    draw.rectangle((24, 17, 26, 27), fill=WOOD_DARK)
    draw.polygon(((3, 15), (27, 10), (37, 17), (13, 24)), fill=WOOD_LIGHT)
    draw.polygon(((3, 15), (13, 24), (13, 29), (3, 20)), fill=WOOD_DARK)
    draw.polygon(((13, 24), (37, 17), (37, 23), (13, 30)), fill=WOOD)
    draw.rectangle((8, 25, 11, 38), fill=WOOD_DARK)
    draw.rectangle((31, 23, 34, 35), fill=WOOD_DARK)
    draw.line((8, 38, 12, 38), fill=DARK)
    draw.line((31, 35, 35, 35), fill=DARK)
    return image
