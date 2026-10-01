import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from install_coins import (
    MIN_BOUNDARY_CLEARANCE,
    choose_coin_positions,
    patch_main,
    patch_makefile,
)
from sm64_assets import mio0_decompress


class CoinFeatureTests(unittest.TestCase):
    def floor_tiles(self):
        tiles = []
        for index in range(12):
            x = index * 220
            tiles.append({
                "room": 135,
                "special": 0,
                "points": [
                    (x, 0, 0, 0),
                    (x + 160, 0, 0, 0),
                    (x + 160, 0, 160, 0),
                    (x, 0, 160, 0),
                ],
            })
        return tiles

    def test_positions_are_on_floor_triangles_and_clear_of_walls(self):
        positions, metadata = choose_coin_positions(
            self.floor_tiles(),
            (0, 0, 0),
            4.0,
            (0, 0, 0),
            count=4,
        )
        self.assertEqual(len(positions), 4)
        self.assertTrue(all(position[1] == 0 for position in positions))
        self.assertGreaterEqual(
            metadata["minimum_boundary_clearance"],
            MIN_BOUNDARY_CLEARANCE,
        )
        self.assertEqual(metadata["rooms"], [135])
        for index, point in enumerate(positions):
            for other in positions[index + 1:]:
                dx = point[0] - other[0]
                dz = point[2] - other[2]
                self.assertGreaterEqual((dx * dx + dz * dz) ** 0.5, 520)

    def test_skinny_tile_near_collision_walls_is_rejected(self):
        tile = {
            "room": 1,
            "special": 0,
            "points": [
                (0, 0, 0, 0),
                (40, 0, 0, 0),
                (40, 0, 40, 0),
                (0, 0, 40, 0),
            ],
        }
        with self.assertRaises(ValueError):
            choose_coin_positions(
                [tile],
                (0, 0, 0),
                4.0,
                (-1000, 0, -1000),
                count=1,
            )

    def test_mio0_literal_decode(self):
        # Four literal bytes. The back-reference stream is unused.
        blob = (
            b"MIO0"
            + struct.pack(">III", 4, 17, 17)
            + bytes([0xF0])
            + b"ABCD"
        )
        self.assertEqual(mio0_decompress(blob, 0), b"ABCD")

    def test_patch_main_is_idempotent(self):
        source = '''#include "audio.h"
            sm64_mario_tick( marioId, &marioInputs, &marioState, &marioGeometry );
        renderer->draw( &renderState, cameraPos, &marioState, &marioGeometry );
'''
        once = patch_main(source)
        twice = patch_main(once)
        self.assertEqual(once, twice)
        self.assertIn("MARIO_GOLDENEYE_COINS_V1", once)
        self.assertIn("mario_goldeneye_coins_tick", once)
        self.assertIn("mario_goldeneye_coins_draw_gl20", once)

    def test_makefile_patch_is_idempotent(self):
        source = "TEST_SRCS_C   := test/context.c test/level.c\n"
        once = patch_makefile(source)
        self.assertEqual(patch_makefile(once), once)
        self.assertIn("TEST_OBJS += $(BUILD_DIR)/test/coins.o", once)
        self.assertIn("$(TEST_FILE): $(BUILD_DIR)/test/coins.o", once)

    def test_makefile_patch_repairs_previous_coin_line(self):
        source = (
            "TEST_SRCS_C   := test/context.c test/level.c\n"
            "# MARIO_GOLDENEYE_COINS_V1\n"
            "TEST_OBJS += $(BUILD_DIR)/test/coins.o\n"
        )
        updated = patch_makefile(source)
        self.assertEqual(
            updated.count("TEST_OBJS += $(BUILD_DIR)/test/coins.o"), 1
        )
        self.assertEqual(
            updated.count("$(TEST_FILE): $(BUILD_DIR)/test/coins.o"), 1
        )


if __name__ == "__main__":
    unittest.main()
