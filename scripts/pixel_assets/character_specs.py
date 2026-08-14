from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from pixel_assets.palette import (
    BLUE,
    BLUE_DARK,
    CREAM,
    GREEN,
    HAIR_BLACK,
    HAIR_BROWN,
    HAIR_CHESTNUT,
    HAIR_DARK,
    HAIR_GOLD,
    MINT,
    ORANGE,
    PINK,
    PURPLE,
    RED,
    SKIN_DARK,
    SKIN_DEEP,
    SKIN_LIGHT,
    SKIN_MEDIUM,
    WHITE,
    YELLOW,
    Color,
)

HairStyle = Literal[
    "teacher",
    "short",
    "parted",
    "bob",
    "fringe",
    "twintail",
    "cap",
    "long",
    "crop",
    "pin",
    "curly",
    "small",
    "hood",
]
Accessory = Literal[
    "chalk",
    "pencil",
    "stripe",
    "book",
    "none",
    "bow",
    "ball",
    "highlighter",
    "star",
]
Pose = Literal["neutral", "confident", "hunched", "active", "shy", "relaxed"]


@dataclass(frozen=True, slots=True)
class CharacterSpec:
    filename: str
    skin: Color
    hair: Color
    shirt: Color
    accent: Color
    hair_style: HairStyle
    accessory: Accessory
    pose: Pose = "neutral"
    seated: bool = True
    small: bool = False
    smile: bool = False
    hooded: bool = False


TEACHER: Final[CharacterSpec] = CharacterSpec(
    "char_teacher.png",
    SKIN_MEDIUM,
    HAIR_DARK,
    CREAM,
    BLUE_DARK,
    "teacher",
    "chalk",
    seated=False,
    smile=True,
)

STUDENTS: Final[tuple[CharacterSpec, ...]] = (
    CharacterSpec(
        "char_s01.png",
        SKIN_MEDIUM,
        HAIR_BLACK,
        BLUE,
        BLUE_DARK,
        "short",
        "pencil",
        pose="confident",
        hooded=True,
    ),
    CharacterSpec("char_s02.png", SKIN_DEEP, HAIR_DARK, GREEN, WHITE, "parted", "stripe", smile=True),
    CharacterSpec("char_s03.png", SKIN_LIGHT, HAIR_BROWN, MINT, BLUE_DARK, "bob", "book"),
    CharacterSpec("char_s04.png", SKIN_MEDIUM, HAIR_CHESTNUT, ORANGE, CREAM, "fringe", "none", pose="hunched"),
    CharacterSpec("char_s05.png", SKIN_DEEP, HAIR_BLACK, PINK, YELLOW, "twintail", "bow", smile=True),
    CharacterSpec("char_s06.png", SKIN_DARK, HAIR_BLACK, RED, BLUE, "cap", "none", pose="active", smile=True),
    CharacterSpec("char_s07.png", SKIN_LIGHT, HAIR_DARK, PURPLE, MINT, "long", "none"),
    CharacterSpec("char_s08.png", SKIN_MEDIUM, HAIR_GOLD, BLUE, WHITE, "crop", "ball", smile=True),
    CharacterSpec("char_s09.png", SKIN_DEEP, HAIR_BROWN, MINT, PINK, "pin", "highlighter"),
    CharacterSpec("char_s10.png", SKIN_DARK, HAIR_CHESTNUT, BLUE_DARK, YELLOW, "curly", "star", smile=True),
    CharacterSpec("char_s11.png", SKIN_LIGHT, HAIR_BLACK, YELLOW, CREAM, "small", "none", pose="shy", small=True),
    CharacterSpec("char_s12.png", SKIN_MEDIUM, HAIR_DARK, PURPLE, BLUE, "hood", "none", pose="relaxed"),
)
