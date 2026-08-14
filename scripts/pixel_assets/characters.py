from __future__ import annotations

from typing import assert_never

from PIL import Image, ImageDraw

from pixel_assets.character_specs import Accessory, CharacterSpec, HairStyle, Pose
from pixel_assets.palette import (
    BLUE_DARK,
    CREAM,
    DARK,
    FLOOR_DARK,
    HAIR_GOLD,
    PINK,
    RED,
    TRANSPARENT,
    WHITE,
    YELLOW,
)


def _draw_hair(draw: ImageDraw.ImageDraw, spec: CharacterSpec) -> None:
    left = 9 if spec.small else 8
    right = 22 if spec.small else 23
    draw.rectangle((left, 8, right, 13), fill=spec.hair)
    draw.rectangle((left - 1, 11, left + 1, 20), fill=spec.hair)
    draw.rectangle((right - 1, 11, right + 1, 20), fill=spec.hair)
    style: HairStyle = spec.hair_style
    match style:
        case "teacher":
            draw.rectangle((9, 6, 22, 11), fill=spec.hair)
            draw.rectangle((20, 4, 25, 9), fill=spec.hair)
            draw.rectangle((10, 6, 14, 7), fill=HAIR_GOLD)
        case "short":
            draw.rectangle((7, 9, 24, 14), fill=spec.hair)
            draw.point((11, 8), fill=spec.accent)
            draw.point((20, 8), fill=spec.accent)
        case "parted":
            draw.polygon(((7, 13), (11, 7), (24, 8), (24, 15), (17, 12), (12, 17)), fill=spec.hair)
            draw.line((16, 8, 22, 9), fill=HAIR_GOLD)
        case "bob":
            draw.rectangle((6, 12, 9, 25), fill=spec.hair)
            draw.rectangle((22, 12, 25, 25), fill=spec.hair)
            draw.rectangle((8, 7, 23, 13), fill=spec.hair)
        case "fringe":
            draw.rectangle((7, 8, 24, 14), fill=spec.hair)
            draw.polygon(((8, 13), (23, 13), (21, 20), (17, 17), (12, 21)), fill=spec.hair)
        case "twintail":
            draw.rectangle((7, 8, 24, 14), fill=spec.hair)
            draw.rectangle((3, 13, 8, 23), fill=spec.hair)
            draw.rectangle((23, 13, 28, 23), fill=spec.hair)
            draw.rectangle((6, 13, 8, 15), fill=spec.accent)
            draw.rectangle((23, 13, 25, 15), fill=spec.accent)
        case "cap":
            draw.rectangle((7, 10, 24, 15), fill=spec.hair)
            draw.rectangle((7, 6, 24, 11), fill=spec.shirt)
            draw.rectangle((4, 9, 9, 11), fill=spec.shirt)
            draw.rectangle((10, 6, 18, 7), fill=spec.accent)
        case "long":
            draw.rectangle((6, 11, 9, 31), fill=spec.hair)
            draw.rectangle((22, 11, 25, 31), fill=spec.hair)
            draw.rectangle((8, 7, 23, 13), fill=spec.hair)
            draw.line((7, 23, 7, 29), fill=spec.accent)
        case "crop":
            draw.rectangle((8, 8, 23, 13), fill=spec.hair)
            draw.point((7, 12), fill=spec.hair)
            draw.point((24, 12), fill=spec.hair)
            draw.line((11, 8, 14, 8), fill=HAIR_GOLD)
        case "pin":
            draw.rectangle((7, 8, 24, 13), fill=spec.hair)
            draw.rectangle((6, 13, 9, 24), fill=spec.hair)
            draw.rectangle((22, 13, 25, 24), fill=spec.hair)
            draw.rectangle((21, 11, 25, 13), fill=spec.accent)
        case "curly":
            for box in ((7, 8, 12, 13), (13, 6, 19, 12), (19, 8, 25, 14), (6, 13, 10, 19), (22, 13, 26, 19)):
                draw.rectangle(box, fill=spec.hair)
            draw.point((16, 7), fill=spec.accent)
        case "small":
            draw.rectangle((8, 9, 23, 14), fill=spec.hair)
            draw.rectangle((10, 7, 19, 9), fill=spec.hair)
        case "hood":
            draw.rectangle((6, 7, 25, 17), fill=spec.shirt)
            draw.rectangle((7, 11, 9, 23), fill=spec.shirt)
            draw.rectangle((22, 11, 24, 23), fill=spec.shirt)
            draw.rectangle((9, 8, 22, 12), fill=spec.hair)
        case unreachable:
            assert_never(unreachable)


def _draw_head(draw: ImageDraw.ImageDraw, spec: CharacterSpec) -> None:
    left = 10 if spec.small else 9
    right = 21 if spec.small else 22
    if spec.hooded:
        draw.rectangle((6, 10, 25, 25), fill=spec.shirt)
        draw.rectangle((6, 14, 8, 22), fill=spec.accent)
        draw.rectangle((23, 14, 25, 22), fill=spec.accent)
    draw.rectangle((left, 10, right, 24), fill=spec.skin)
    draw.rectangle((left - 1, 15, left, 20), fill=spec.skin)
    draw.rectangle((right, 15, right + 1, 20), fill=spec.skin)
    _draw_hair(draw, spec)
    eye_y = 19
    draw.line((12, eye_y, 13, eye_y), fill=DARK)
    draw.line((18, eye_y, 19, eye_y), fill=DARK)
    style: HairStyle = spec.hair_style
    match style:
        case "bob":
            draw.rectangle((10, 17, 14, 21), outline=BLUE_DARK)
            draw.rectangle((17, 17, 21, 21), outline=BLUE_DARK)
            draw.line((14, 18, 17, 18), fill=BLUE_DARK)
        case "fringe":
            draw.rectangle((11, 16, 15, 19), fill=spec.hair)
        case "teacher" | "short" | "parted" | "twintail" | "cap" | "long" | "crop" | "pin" | "curly" | "small" | "hood":
            pass
        case unreachable:
            assert_never(unreachable)
    if spec.smile:
        draw.line((14, 22, 17, 23), fill=DARK)
        draw.point((12, 22), fill=PINK)
        draw.point((19, 22), fill=PINK)
    else:
        draw.line((14, 23, 17, 23), fill=DARK)


def _draw_accessory(draw: ImageDraw.ImageDraw, spec: CharacterSpec, body_y: int) -> None:
    accessory: Accessory = spec.accessory
    match accessory:
        case "chalk":
            draw.rectangle((25, body_y + 6, 27, body_y + 8), fill=spec.skin)
            draw.rectangle((27, body_y + 5, 29, body_y + 5), fill=WHITE)
        case "pencil":
            draw.line((23, body_y + 7, 27, body_y + 3), fill=YELLOW)
            draw.point((27, body_y + 3), fill=DARK)
        case "stripe":
            draw.rectangle((11, body_y + 3, 20, body_y + 5), fill=spec.accent)
            draw.rectangle((14, body_y, 17, body_y + 11), fill=spec.accent)
        case "book":
            draw.polygon(((3, body_y + 8), (9, body_y + 7), (11, body_y + 12), (4, body_y + 13)), fill=BLUE_DARK)
            draw.line((5, body_y + 8, 9, body_y + 8), fill=CREAM)
        case "none":
            pass
        case "bow":
            draw.rectangle((6, 13, 8, 16), fill=PINK)
            draw.rectangle((23, 13, 25, 16), fill=PINK)
        case "ball":
            draw.ellipse((24, 36, 30, 42), fill=WHITE)
            draw.rectangle((26, 38, 28, 40), fill=DARK)
            draw.point((25, 37), fill=DARK)
            draw.point((29, 41), fill=DARK)
        case "highlighter":
            draw.rectangle((3, body_y + 7, 10, body_y + 11), fill=PINK)
            draw.line((4, body_y + 8, 9, body_y + 8), fill=CREAM)
            draw.rectangle((23, body_y + 8, 28, body_y + 9), fill=YELLOW)
            draw.point((28, body_y + 8), fill=DARK)
        case "star":
            draw.point((15, body_y + 3), fill=YELLOW)
            draw.line((13, body_y + 5, 17, body_y + 5), fill=YELLOW)
            draw.line((15, body_y + 3, 15, body_y + 7), fill=YELLOW)
        case unreachable:
            assert_never(unreachable)


def _draw_seated_body(draw: ImageDraw.ImageDraw, spec: CharacterSpec, breath: int) -> None:
    base_y = (28 if spec.small else 26) + breath
    pose: Pose = spec.pose
    match pose:
        case "neutral":
            body_y, left, right, left_arm_y, right_arm_y = base_y, 8, 23, 3, 3
        case "confident":
            body_y, left, right, left_arm_y, right_arm_y = base_y, 7, 24, 2, 2
        case "hunched":
            body_y, left, right, left_arm_y, right_arm_y = base_y + 1, 10, 21, 4, 4
        case "active":
            body_y, left, right, left_arm_y, right_arm_y = base_y, 7, 24, 1, 4
        case "shy":
            body_y, left, right, left_arm_y, right_arm_y = base_y + 1, 10, 21, 4, 4
        case "relaxed":
            body_y, left, right, left_arm_y, right_arm_y = base_y + 1, 9, 23, 5, 2
        case unreachable:
            assert_never(unreachable)
    draw.polygon(((left, body_y), (right, body_y), (21, body_y + 12), (10, body_y + 12)), fill=spec.shirt)
    draw.line((10, body_y + 1, 21, body_y + 1), fill=spec.accent, width=2)
    draw.rectangle((left - 2, body_y + left_arm_y, left + 1, body_y + left_arm_y + 6), fill=spec.shirt)
    draw.rectangle((right - 1, body_y + right_arm_y, right + 2, body_y + right_arm_y + 6), fill=spec.shirt)
    draw.rectangle((left - 1, body_y + left_arm_y + 5, left + 1, body_y + left_arm_y + 7), fill=spec.skin)
    draw.rectangle((right - 1, body_y + right_arm_y + 5, right + 1, body_y + right_arm_y + 7), fill=spec.skin)
    match pose:
        case "shy":
            draw.line((12, body_y + 6, 15, body_y + 9), fill=spec.shirt, width=2)
            draw.line((19, body_y + 6, 16, body_y + 9), fill=spec.shirt, width=2)
            draw.point((15, body_y + 9), fill=spec.skin)
            draw.point((16, body_y + 9), fill=spec.skin)
        case "neutral" | "confident" | "hunched" | "active" | "relaxed":
            pass
        case unreachable:
            assert_never(unreachable)
    draw.polygon(((10, body_y + 10), (15, body_y + 10), (13, 42), (6, 42)), fill=BLUE_DARK)
    draw.polygon(((17, body_y + 10), (22, body_y + 10), (26, 42), (19, 42)), fill=BLUE_DARK)
    draw.rectangle((5, 41, 12, 45), fill=DARK)
    draw.rectangle((20, 41, 27, 45), fill=DARK)
    draw.line((6, 45, 12, 45), fill=WHITE)
    draw.line((20, 45, 26, 45), fill=WHITE)
    _draw_accessory(draw, spec, body_y)


def _draw_standing_body(draw: ImageDraw.ImageDraw, spec: CharacterSpec, breath: int) -> None:
    body_y = 24 + breath
    draw.polygon(((8, body_y), (23, body_y), (21, 39), (10, 39)), fill=spec.shirt)
    draw.rectangle((14, body_y, 17, 36), fill=spec.accent)
    draw.polygon(((8, body_y + 1), (5, body_y + 9), (8, body_y + 11), (12, body_y + 3)), fill=spec.shirt)
    draw.polygon(((23, body_y + 1), (26, body_y + 7), (23, body_y + 10), (20, body_y + 3)), fill=spec.shirt)
    draw.rectangle((5, body_y + 9, 8, body_y + 12), fill=spec.skin)
    draw.rectangle((23, body_y + 8, 26, body_y + 11), fill=spec.skin)
    draw.polygon(((10, 38), (15, 38), (14, 47), (9, 47)), fill=BLUE_DARK)
    draw.polygon(((17, 38), (21, 38), (23, 47), (18, 47)), fill=BLUE_DARK)
    draw.line((8, 47, 14, 47), fill=DARK)
    draw.line((18, 47, 24, 47), fill=DARK)
    _draw_accessory(draw, spec, body_y)


def _make_frame(spec: CharacterSpec, breath: int) -> Image.Image:
    image = Image.new("RGBA", (32, 48), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    if spec.seated:
        _draw_seated_body(draw, spec, breath)
    else:
        _draw_standing_body(draw, spec, breath)
    _draw_head(draw, spec)
    return image


def make_character(spec: CharacterSpec) -> Image.Image:
    sheet = Image.new("RGBA", (64, 48), TRANSPARENT)
    sheet.paste(_make_frame(spec, 0), (0, 0))
    sheet.paste(_make_frame(spec, -1), (32, 0))
    return sheet
