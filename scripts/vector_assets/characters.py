from __future__ import annotations

from typing import assert_never

from PIL import Image

from pixel_assets.character_specs import Accessory, CharacterSpec, HairStyle, Pose
from pixel_assets.palette import BLUE_DARK, CREAM, DARK, HAIR_GOLD, PINK, WHITE, YELLOW
from vector_assets.drawing import SCALE, Surface


def _hair(surface: Surface, spec: CharacterSpec) -> None:
    style: HairStyle = spec.hair_style
    surface.ellipse((6.2, 3.4, 25.8, 22.8), spec.hair, DARK, 0.8)
    match style:
        case "teacher":
            surface.ellipse((18, 2, 27, 10), spec.hair, DARK, 0.7)
            surface.line(((10, 7), (15, 5), (20, 6)), HAIR_GOLD, 0.8)
        case "short":
            surface.polygon(((6, 11), (8, 5), (14, 4), (12, 11), (20, 5), (26, 10)), spec.hair)
        case "parted":
            surface.polygon(((6, 11), (11, 4), (17, 4), (14, 13), (25, 7), (26, 13)), spec.hair)
        case "bob":
            surface.rounded((5, 8, 10, 28), 2, spec.hair, DARK, 0.7)
            surface.rounded((22, 8, 27, 28), 2, spec.hair, DARK, 0.7)
        case "fringe":
            surface.polygon(((6, 9), (9, 5), (26, 6), (24, 15), (20, 12), (17, 17), (12, 12), (9, 17)), spec.hair)
        case "twintail":
            surface.ellipse((1, 10, 9, 25), spec.hair, DARK, 0.7)
            surface.ellipse((23, 10, 31, 25), spec.hair, DARK, 0.7)
            surface.ellipse((5, 12, 9, 16), spec.accent)
            surface.ellipse((23, 12, 27, 16), spec.accent)
        case "cap":
            surface.rounded((5, 3, 26, 12), 4, spec.shirt, DARK, 0.8)
            surface.rounded((3, 8, 12, 11), 1.5, spec.shirt, DARK, 0.7)
        case "long":
            surface.rounded((4.5, 8, 10, 34), 2.5, spec.hair, DARK, 0.8)
            surface.rounded((22, 8, 27.5, 34), 2.5, spec.hair, DARK, 0.8)
        case "crop":
            surface.polygon(((7, 10), (9, 5), (13, 7), (17, 4), (20, 7), (24, 5), (26, 12)), spec.hair)
        case "pin":
            surface.rounded((5.5, 8, 10, 27), 2, spec.hair, DARK, 0.7)
            surface.rounded((22, 8, 26.5, 27), 2, spec.hair, DARK, 0.7)
            surface.rounded((21, 10, 26, 12.5), 1, spec.accent)
        case "curly":
            for box in ((5, 7, 12, 15), (10, 3, 18, 12), (16, 4, 24, 13), (21, 8, 28, 17)):
                surface.ellipse(box, spec.hair, DARK, 0.6)
        case "small":
            surface.rounded((7, 5, 25, 14), 4, spec.hair, DARK, 0.7)
        case "hood":
            surface.rounded((4, 3, 28, 27), 9, spec.shirt, DARK, 0.9)
            surface.ellipse((7, 6, 25, 22), spec.hair)
        case unreachable:
            assert_never(unreachable)


def _face(surface: Surface, spec: CharacterSpec) -> None:
    if spec.hooded:
        surface.rounded((4, 5, 28, 28), 9, spec.shirt, DARK, 0.9)
    surface.ellipse((8, 8, 24, 26), spec.skin, DARK, 0.8)
    surface.ellipse((6.6, 15, 10.6, 21), spec.skin, DARK, 0.6)
    surface.ellipse((21.4, 15, 25.4, 21), spec.skin, DARK, 0.6)
    _hair(surface, spec)
    surface.ellipse((10.5, 15, 15, 21), WHITE, DARK, 0.55)
    surface.ellipse((17, 15, 21.5, 21), WHITE, DARK, 0.55)
    surface.ellipse((12, 16.5, 14.2, 20.2), DARK)
    surface.ellipse((18.3, 16.5, 20.5, 20.2), DARK)
    surface.ellipse((12.2, 16.8, 12.9, 17.7), WHITE)
    surface.ellipse((18.5, 16.8, 19.2, 17.7), WHITE)
    surface.ellipse((9.4, 21, 12, 22.4), PINK)
    surface.ellipse((20, 21, 22.6, 22.4), PINK)
    if spec.hair_style == "bob":
        surface.rounded((9.8, 14.4, 15.4, 21.4), 1.4, (0, 0, 0, 0), BLUE_DARK, 0.65)
        surface.rounded((16.6, 14.4, 22.2, 21.4), 1.4, (0, 0, 0, 0), BLUE_DARK, 0.65)
        surface.line(((15.4, 17), (16.6, 17)), BLUE_DARK, 0.65)
    if spec.smile:
        surface.line(((13.4, 23), (16, 24), (18.6, 23)), DARK, 0.65)
    else:
        surface.line(((14, 23.5), (18, 23.5)), DARK, 0.65)


def _accessory(surface: Surface, spec: CharacterSpec, body_y: float) -> None:
    accessory: Accessory = spec.accessory
    match accessory:
        case "chalk":
            surface.rounded((25, body_y + 5, 28, body_y + 8), 1, spec.skin, DARK, 0.5)
            surface.line(((27, body_y + 5), (30, body_y + 3)), WHITE, 0.8)
        case "pencil":
            surface.line(((23, body_y + 8), (28, body_y + 2)), YELLOW, 1)
        case "stripe":
            surface.rectangle((10, body_y + 3, 22, body_y + 6), spec.accent)
        case "book":
            surface.rounded((2, body_y + 7, 11, body_y + 13), 1, BLUE_DARK, DARK, 0.6)
            surface.line(((4, body_y + 9), (9, body_y + 9)), CREAM, 0.5)
        case "none":
            pass
        case "bow":
            surface.ellipse((4, 13, 8, 17), spec.accent)
            surface.ellipse((24, 13, 28, 17), spec.accent)
        case "ball":
            surface.ellipse((24, 35, 31, 42), WHITE, DARK, 0.7)
            surface.polygon(((26, 37), (29, 37), (30, 40), (27, 41), (25, 39)), DARK)
        case "highlighter":
            surface.rounded((24, body_y + 7, 30, body_y + 9), 0.7, YELLOW, DARK, 0.5)
        case "star":
            surface.polygon(((16, body_y + 2), (17, body_y + 5), (20, body_y + 5), (17.7, body_y + 7), (18.5, body_y + 10), (16, body_y + 8), (13.5, body_y + 10), (14.3, body_y + 7), (12, body_y + 5), (15, body_y + 5)), YELLOW)
        case unreachable:
            assert_never(unreachable)


def _body(surface: Surface, spec: CharacterSpec, breath: int) -> None:
    base_y = (28 if spec.small else 27) + breath
    pose: Pose = spec.pose
    width = {"neutral": 17, "confident": 19, "hunched": 14, "active": 19, "shy": 14, "relaxed": 17}[pose]
    left = 16 - width / 2
    surface.rounded((left, base_y, left + width, base_y + 13), 3.5, spec.shirt, DARK, 0.9)
    surface.line(((left + 2, base_y + 3), (left + width - 2, base_y + 3)), spec.accent, 1)
    surface.rounded((left - 3, base_y + 2, left + 2, base_y + 11), 2, spec.shirt, DARK, 0.7)
    surface.rounded((left + width - 2, base_y + 2, left + width + 3, base_y + 11), 2, spec.shirt, DARK, 0.7)
    surface.ellipse((left - 2, base_y + 8, left + 2, base_y + 12), spec.skin, DARK, 0.5)
    surface.ellipse((left + width - 2, base_y + 8, left + width + 2, base_y + 12), spec.skin, DARK, 0.5)
    surface.rounded((8, base_y + 10, 15.5, 43), 2, BLUE_DARK, DARK, 0.7)
    surface.rounded((16.5, base_y + 10, 24, 43), 2, BLUE_DARK, DARK, 0.7)
    surface.rounded((6.5, 41, 15.5, 46), 2, WHITE, DARK, 0.8)
    surface.rounded((16.5, 41, 25.5, 46), 2, WHITE, DARK, 0.8)
    surface.line(((8, 43), (14, 43)), spec.accent, 0.6)
    surface.line(((18, 43), (24, 43)), spec.accent, 0.6)
    _accessory(surface, spec, base_y)


def _frame(spec: CharacterSpec, breath: int) -> Image.Image:
    surface = Surface.transparent(32, 48)
    surface.ellipse((5, 44, 27, 47), (73, 61, 57, 70))
    _body(surface, spec, breath)
    _face(surface, spec)
    return surface.image


def make_character(spec: CharacterSpec) -> Image.Image:
    sheet = Image.new("RGBA", (64 * SCALE, 48 * SCALE), (0, 0, 0, 0))
    sheet.alpha_composite(_frame(spec, 0), (0, 0))
    sheet.alpha_composite(_frame(spec, -1), (32 * SCALE, 0))
    return sheet
