import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from install_coins import (
    MIN_BOUNDARY_CLEARANCE,
    choose_collectibles,
    patch_main,
    patch_makefile,
)
from sm64_assets import mio0_decompress, rgba16_to_rgba8


def connected_tiles(count=30):
    tiles=[]
    base=-96
    offsets=[32+40*i for i in range(count)]
    for index,offset in enumerate(offsets):
        x=index*220
        links=[0,0,0,0]
        if index+1<count:
            links[0]=(offsets[index+1]-base)//8
        if index>0:
            links[2]=(offsets[index-1]-base)//8
        tiles.append({
            "room":index%6+1,
            "special":0,
            "offset":offset,
            "link_base":base,
            "points":[
                (x,0,0,links[0]),
                (x+160,0,0,links[1]),
                (x+160,0,160,links[2]),
                (x,0,160,links[3]),
            ],
        })
    return tiles


class CoinFeatureTests(unittest.TestCase):
    def test_distributed_collectibles_have_three_star_course_rules(self):
        placements,metadata=choose_collectibles(
            connected_tiles(40),(0,0,0),4.0,(0,0,0),
            yellow_count=6,red_count=3,blue_count=2,
        )
        self.assertEqual(len(placements["yellow"]),6)
        self.assertEqual(len(placements["red"]),3)
        self.assertEqual(len(placements["blue"]),2)
        self.assertGreaterEqual(metadata["minimum_boundary_clearance"],MIN_BOUNDARY_CLEARANCE)
        self.assertEqual(metadata["max_coin_value"],6+3*2+2*5)
        self.assertGreater(metadata["reachable_stan_tiles"],1)
        self.assertNotEqual(placements["red_star"],placements["exploration_star"])

    def test_unreachable_island_is_not_used(self):
        tiles=connected_tiles(12)
        island=connected_tiles(1)[0]
        island["offset"]=5000
        island["link_base"]=-96
        island["room"]=99
        island["points"]=[(10000,0,10000,0),(10200,0,10000,0),(10200,0,10200,0),(10000,0,10200,0)]
        tiles.append(island)
        placements,metadata=choose_collectibles(
            tiles,(0,0,0),4.0,(0,0,0),
            yellow_count=2,red_count=1,blue_count=1,
        )
        all_points=placements["yellow"]+placements["red"]+placements["blue"]
        self.assertTrue(all(point[0]<30000 for point in all_points))

    def test_mio0_literal_decode(self):
        blob=(
            b"MIO0"+struct.pack(">III",4,17,17)+bytes([0xF0])+b"ABCD"
        )
        self.assertEqual(mio0_decompress(blob,0),b"ABCD")

    def test_rgba16_decode(self):
        self.assertEqual(rgba16_to_rgba8(bytes([0xff,0xff])),bytes([255,255,255,255]))
        self.assertEqual(rgba16_to_rgba8(bytes([0x00,0x00])),bytes([0,0,0,0]))

    def test_patch_main_is_idempotent(self):
        source='''#include "audio.h"
            sm64_mario_tick( marioId, &marioInputs, &marioState, &marioGeometry );
        renderer->draw( &renderState, cameraPos, &marioState, &marioGeometry );
'''
        once=patch_main(source)
        self.assertEqual(patch_main(once),once)
        self.assertIn("MARIO_GOLDENEYE_COINS_V1",once)

    def test_makefile_patch_is_idempotent(self):
        source="TEST_SRCS_C   := test/context.c test/level.c\n"
        once=patch_makefile(source)
        self.assertEqual(patch_makefile(once),once)
        self.assertIn("$(TEST_FILE): $(BUILD_DIR)/test/coins.o",once)


if __name__=="__main__":
    unittest.main()
