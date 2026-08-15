from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPOSITORY_ROOT / "src/classroom_sim/web/static/assets/vector"
SCALE = 4
EXPECTED = {
    "tiles.png": (256 * SCALE, 32 * SCALE),
    "blackboard.png": (192 * SCALE, 64 * SCALE),
    "desk_teacher.png": (64 * SCALE, 48 * SCALE),
    "desk_student.png": (40 * SCALE, 40 * SCALE),
    "char_teacher.png": (64 * SCALE, 48 * SCALE),
    **{f"char_s{index:02}.png": (64 * SCALE, 48 * SCALE) for index in range(1, 13)},
    "emotes.png": (128 * SCALE, 16 * SCALE),
}


class VectorAssetContractTest(unittest.TestCase):
    def test_renderer_consumes_vector_tiles_and_shared_color_tokens(self) -> None:
        # Given: the runtime source for the flat-vector classroom.
        app_source = (REPOSITORY_ROOT / "src/classroom_sim/web/static/app.js").read_text(encoding="utf-8")

        # When: the room renderer contract is inspected.
        tile_draw_calls = app_source.count("Stage.drawTile(")

        # Then: generated tiles and shared color tokens drive the visible room.
        self.assertGreaterEqual(tile_draw_calls, 4)
        self.assertIn("const CLASSROOM_COLORS =", app_source)
        self.assertNotIn("#b5824a", app_source)

    def test_all_vector_assets_match_dimensions_and_alpha_contract(self) -> None:
        # Given: the selected flat-vector asset contract.
        expected = EXPECTED

        # When: the generated asset directory is inspected.
        actual = {path.name: path for path in ASSET_DIR.glob("*.png")}

        # Then: all 18 RGBA files have the expected size and transparency policy.
        self.assertEqual(set(expected), set(actual))
        for filename, size in expected.items():
            with Image.open(actual[filename]) as image:
                self.assertEqual("PNG", image.format, filename)
                self.assertEqual("RGBA", image.mode, filename)
                self.assertEqual(size, image.size, filename)
                alpha = set(image.getchannel("A").get_flattened_data())
                if filename == "tiles.png":
                    self.assertEqual({255}, alpha, filename)
                else:
                    self.assertIn(0, alpha, filename)
                    self.assertIn(255, alpha, filename)

    def test_character_sheets_contain_two_distinct_frames(self) -> None:
        # Given: every character is a two-frame horizontal sheet.
        character_names = ["char_teacher.png", *(f"char_s{i:02}.png" for i in range(1, 13))]

        # When: the two 128×192 frames are compared.
        frame_pairs = []
        for filename in character_names:
            with Image.open(ASSET_DIR / filename) as image:
                frame_pairs.append(
                    (
                        image.crop((0, 0, 32 * SCALE, 48 * SCALE)).tobytes(),
                        image.crop((32 * SCALE, 0, 64 * SCALE, 48 * SCALE)).tobytes(),
                    )
                )

        # Then: neither breathing frame is duplicated.
        self.assertTrue(all(first != second for first, second in frame_pairs))

    def test_student_seat_layers_chair_behind_character_and_desk_in_front(self) -> None:
        # Given: the shared student furniture sheet and runtime renderer.
        split_y = 12 * SCALE
        desk_top_color = (213, 165, 111, 255)
        app_source = (REPOSITORY_ROOT / "src/classroom_sim/web/static/app.js").read_text(encoding="utf-8")

        # When: the furniture is divided at the shared seat-layer boundary.
        with Image.open(ASSET_DIR / "desk_student.png") as image:
            chair_back = image.crop((0, 0, image.width, split_y))

        # Then: the rear band contains only the chair, while runtime sandwiches
        # every character between the rear chair and front desk layers.
        self.assertNotIn(desk_top_color, set(chair_back.get_flattened_data()))
        back_call = "Stage.drawDesk(g, s, stu.id, 'back');"
        character_call = "Stage.drawCharacter(g, sprite, s.spriteX, s.spriteY, frame);"
        front_call = "Stage.drawDesk(g, s, stu.id, 'front');"
        self.assertIn(back_call, app_source)
        self.assertIn(front_call, app_source)
        self.assertLess(app_source.index(back_call), app_source.index(character_call))
        self.assertLess(app_source.index(character_call), app_source.index(front_call))


if __name__ == "__main__":
    unittest.main()
