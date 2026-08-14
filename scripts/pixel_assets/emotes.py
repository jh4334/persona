from __future__ import annotations

from PIL import Image, ImageDraw

from pixel_assets.palette import BLUE, CREAM, DARK, RED, SKIN_MEDIUM, TRANSPARENT, WHITE, YELLOW


def _hand(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.rectangle((x + 6, 2, x + 10, 13), fill=WHITE)
    draw.rectangle((x + 3, 4, x + 12, 9), fill=WHITE)
    draw.rectangle((x + 7, 3, x + 9, 12), fill=SKIN_MEDIUM)
    draw.rectangle((x + 4, 5, x + 11, 8), fill=SKIN_MEDIUM)
    draw.line((x + 5, 6, x + 10, 6), fill=CREAM)
    draw.rectangle((x + 6, 10, x + 10, 14), fill=BLUE)


def _sleep(draw: ImageDraw.ImageDraw, x: int) -> None:
    for dx, dy in ((3, 7), (8, 3)):
        draw.rectangle((x + dx - 1, dy - 1, x + dx + 4, dy + 4), fill=WHITE)
        draw.line((x + dx, dy, x + dx + 3, dy), fill=BLUE)
        draw.line((x + dx + 3, dy, x + dx, dy + 3), fill=BLUE)
        draw.line((x + dx, dy + 3, x + dx + 3, dy + 3), fill=BLUE)


def _question(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.rectangle((x + 5, 2, x + 11, 4), fill=WHITE)
    draw.rectangle((x + 9, 4, x + 13, 8), fill=WHITE)
    draw.rectangle((x + 7, 7, x + 11, 11), fill=WHITE)
    draw.rectangle((x + 7, 12, x + 10, 15), fill=WHITE)
    draw.line((x + 6, 3, x + 10, 3), fill=YELLOW)
    draw.rectangle((x + 10, 4, x + 11, 7), fill=YELLOW)
    draw.rectangle((x + 8, 7, x + 10, 9), fill=YELLOW)
    draw.rectangle((x + 8, 13, x + 9, 14), fill=YELLOW)


def _spark(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.polygon(((x + 8, 1), (x + 10, 6), (x + 15, 8), (x + 10, 10), (x + 8, 15), (x + 6, 10), (x + 1, 8), (x + 6, 6)), fill=WHITE)
    draw.line((x + 8, 3, x + 8, 13), fill=YELLOW)
    draw.line((x + 3, 8, x + 13, 8), fill=YELLOW)
    draw.rectangle((x + 7, 7, x + 9, 9), fill=YELLOW)


def _anxious(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.polygon(((x + 5, 1), (x + 10, 7), (x + 9, 12), (x + 5, 14), (x + 1, 11), (x + 1, 7)), fill=WHITE)
    draw.polygon(((x + 5, 3), (x + 8, 7), (x + 8, 11), (x + 5, 12), (x + 3, 10), (x + 3, 7)), fill=BLUE)
    draw.rectangle((x + 11, 10, x + 15, 14), fill=WHITE)
    draw.rectangle((x + 12, 11, x + 14, 13), fill=BLUE)


def _chat(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.rectangle((x + 1, 2, x + 14, 11), fill=WHITE)
    draw.polygon(((x + 8, 10), (x + 12, 10), (x + 10, 14)), fill=WHITE)
    draw.rectangle((x + 3, 4, x + 12, 9), fill=BLUE)
    draw.polygon(((x + 9, 9), (x + 11, 9), (x + 10, 12)), fill=BLUE)
    for px in (5, 8, 11):
        draw.point((x + px, 6), fill=WHITE)


def _bored(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.rectangle((x + 1, 5, x + 14, 11), fill=WHITE)
    draw.rectangle((x + 2, 6, x + 7, 9), fill=CREAM)
    draw.rectangle((x + 9, 6, x + 14, 9), fill=CREAM)
    draw.line((x + 2, 7, x + 7, 8), fill=DARK)
    draw.line((x + 9, 8, x + 14, 7), fill=DARK)
    draw.point((x + 5, 8), fill=DARK)
    draw.point((x + 11, 8), fill=DARK)
    draw.line((x + 6, 12, x + 10, 12), fill=WHITE)
    draw.line((x + 7, 12, x + 9, 12), fill=DARK)


def _excited(draw: ImageDraw.ImageDraw, x: int) -> None:
    draw.polygon(((x + 7, 1), (x + 10, 5), (x + 15, 4), (x + 12, 8), (x + 15, 12), (x + 10, 11), (x + 7, 15), (x + 6, 10), (x + 1, 12), (x + 4, 8), (x + 1, 4), (x + 6, 5)), fill=WHITE)
    draw.polygon(((x + 7, 3), (x + 9, 6), (x + 13, 6), (x + 10, 8), (x + 12, 10), (x + 9, 9), (x + 7, 13), (x + 7, 9), (x + 3, 10), (x + 6, 8), (x + 3, 6), (x + 7, 7)), fill=RED)
    draw.rectangle((x + 7, 7, x + 9, 9), fill=YELLOW)


def make_emotes() -> Image.Image:
    image = Image.new("RGBA", (128, 16), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    drawers = (_hand, _sleep, _question, _spark, _anxious, _chat, _bored, _excited)
    for index, draw_icon in enumerate(drawers):
        draw_icon(draw, index * 16)
    return image
