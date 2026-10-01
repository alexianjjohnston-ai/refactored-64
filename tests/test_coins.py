import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from install_coins import choose_coin_positions, patch_main, patch_makefile


class CoinFeatureTests(unittest.TestCase):
    def test_positions_are_separated_and_raised(self):
        tiles = []
        for index in range(12):
            x = index * 200
            tiles.append({
                "special": 0,
                "points": [
                    (x, 0, 0, 0),
                    (x + 120, 0, 0, 0),
                    (x + 120, 0, 120, 0),
                    (x, 0, 120, 0),
                ],
            })
        positions = choose_coin_positions(tiles, (0, 0, 0), 4.0, (0, 0, 0), count=4)
        self.assertEqual(len(positions), 4)
        self.assertTrue(all(position[1] == 110 for position in positions))
        for index, point in enumerate(positions):
            for other in positions[index + 1:]:
                dx = point[0] - other[0]
                dz = point[2] - other[2]
                self.assertGreaterEqual((dx * dx + dz * dz) ** 0.5, 520)

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


if __name__ == "__main__":
    unittest.main()
