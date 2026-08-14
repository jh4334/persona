from typing import Final, TypeAlias

Color: TypeAlias = tuple[int, int, int, int]


def rgba(hex_color: str) -> Color:
    value = hex_color.removeprefix("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 255)


TRANSPARENT: Final[Color] = (0, 0, 0, 0)
FLOOR: Final[Color] = rgba("#C8996B")
FLOOR_LIGHT: Final[Color] = rgba("#DBB183")
FLOOR_DARK: Final[Color] = rgba("#A8734F")
CREAM: Final[Color] = rgba("#F2E8D5")
CREAM_SHADE: Final[Color] = rgba("#DCCCAD")
BOARD: Final[Color] = rgba("#3E6B4F")
BOARD_LIGHT: Final[Color] = rgba("#5C836A")
WOOD: Final[Color] = rgba("#A96F45")
WOOD_LIGHT: Final[Color] = rgba("#D5A56F")
WOOD_DARK: Final[Color] = rgba("#79543C")
SKY: Final[Color] = rgba("#84BED1")
GREEN: Final[Color] = rgba("#6FA77A")
BLUE: Final[Color] = rgba("#6F9CC4")
BLUE_DARK: Final[Color] = rgba("#486E98")
PINK: Final[Color] = rgba("#D9899E")
PURPLE: Final[Color] = rgba("#9A82B8")
YELLOW: Final[Color] = rgba("#E8C568")
RED: Final[Color] = rgba("#C96F68")
ORANGE: Final[Color] = rgba("#D99A5B")
MINT: Final[Color] = rgba("#80B8A0")
WHITE: Final[Color] = rgba("#FFFDF5")
DARK: Final[Color] = rgba("#493D39")
SKIN_LIGHT: Final[Color] = rgba("#F2C7A5")
SKIN_MEDIUM: Final[Color] = rgba("#D9A17E")
SKIN_DEEP: Final[Color] = rgba("#B87557")
SKIN_DARK: Final[Color] = rgba("#8E5B43")
HAIR_DARK: Final[Color] = rgba("#554239")
HAIR_BROWN: Final[Color] = rgba("#75513B")
HAIR_CHESTNUT: Final[Color] = rgba("#BA8060")
HAIR_GOLD: Final[Color] = rgba("#D4B27C")
HAIR_BLACK: Final[Color] = rgba("#342F38")

PALETTE: Final[frozenset[Color]] = frozenset(
    {
        TRANSPARENT,
        FLOOR,
        FLOOR_LIGHT,
        FLOOR_DARK,
        CREAM,
        CREAM_SHADE,
        BOARD,
        BOARD_LIGHT,
        WOOD,
        WOOD_LIGHT,
        WOOD_DARK,
        SKY,
        GREEN,
        BLUE,
        BLUE_DARK,
        PINK,
        PURPLE,
        YELLOW,
        RED,
        ORANGE,
        MINT,
        WHITE,
        DARK,
        SKIN_LIGHT,
        SKIN_MEDIUM,
        SKIN_DEEP,
        SKIN_DARK,
        HAIR_DARK,
        HAIR_BROWN,
        HAIR_CHESTNUT,
        HAIR_GOLD,
        HAIR_BLACK,
    }
)
