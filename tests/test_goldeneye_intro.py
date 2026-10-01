import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from goldeneye_intro import (
    DAM_LEVEL_SCALE,
    INTRO_CAMERA,
    INTRO_END,
    INTRO_SPAWN,
    INTRO_SWIRL,
    camera_to_project,
    decompress_1172,
    parse_setup_intro,
    swirl_to_project,
)
from install_intro import patch_camera_header, patch_makefile


class GoldenEyeIntroTests(unittest.TestCase):
    def synthetic_setup(self):
        intro_offset = 40
        header = bytearray(40)
        struct.pack_into(">I", header, 8, intro_offset)

        camera = struct.pack(
            ">10I",
            INTRO_CAMERA,
            10000,
            20000,
            30000,
            0x00008000,
            0,
            12,
            1,
            2,
            0,
        )
        spawn = struct.pack(">III", INTRO_SPAWN, 33, 0)
        swirls = b""
        for index in range(5):
            flags = 1 if index == 4 else 2
            swirls += struct.pack(
                ">8I",
                INTRO_SWIRL,
                flags,
                0x00010000,
                0x00020000,
                0x00030000,
                0x00008000,
                0x003C0000,
                0xFFFFFFFF,
            )
        end = struct.pack(">I", INTRO_END)
        return bytes(header) + camera + spawn + swirls + end

    def test_parse_setup_intro(self):
        intro = parse_setup_intro(self.synthetic_setup())
        self.assertEqual(len(intro["cameras"]), 1)
        self.assertEqual(len(intro["swirls"]), 5)
        self.assertEqual(intro["spawns"], [33])
        self.assertEqual(intro["cameras"][0]["pad"], 12)

    def test_1172_decompression(self):
        payload = self.synthetic_setup()
        compressor = zlib.compressobj(level=9, wbits=-15)
        compressed = b"\x11\x72" + compressor.compress(payload) + compressor.flush()
        self.assertEqual(decompress_1172(compressed), payload)

    def test_fixed_camera_uses_goldeneye_level_scale_then_project_transform(self):
        camera = {
            "coords_cm100": (10000, 20000, 30000),
            "yaw_fixed": 0,
            "pitch_fixed": 0,
            "pad": 0,
            "text1": 0,
            "text2": 0,
        }
        projected = camera_to_project(camera, (10.0, 20.0, 30.0), 4.0)
        expected_raw = (100.0 * DAM_LEVEL_SCALE, 200.0 * DAM_LEVEL_SCALE, 300.0 * DAM_LEVEL_SCALE)
        self.assertAlmostEqual(projected["position"][0], (expected_raw[0] - 10.0) * 4.0)
        self.assertAlmostEqual(projected["position"][1], (expected_raw[1] - 20.0) * 4.0)
        self.assertAlmostEqual(projected["position"][2], (expected_raw[2] - 30.0) * 4.0)

    def test_swirl_delta_converts_runtime_units_to_project_units(self):
        swirl = {
            "flags": 2,
            "offset_fixed": (65535, 0, -65535),
            "scale_fixed": 32768,
            "duration_fixed": 65535,
            "pad": -1,
        }
        projected = swirl_to_project(swirl, 4.0)
        self.assertAlmostEqual(projected["offset"][0], 4.0 / DAM_LEVEL_SCALE)
        self.assertAlmostEqual(projected["offset"][2], -4.0 / DAM_LEVEL_SCALE)
        self.assertAlmostEqual(projected["duration_frames"], 1.0)

    def test_camera_header_patch_is_idempotent(self):
        source = '''#pragma once
#include <math.h>
#include "../src/libsm64.h"

static void facility_camera_target(const float position[3], float target[3])
{
    target[0] = position[0];
}
'''
        once = patch_camera_header(source)
        self.assertEqual(patch_camera_header(once), once)
        self.assertIn("goldeneye_intro_camera_target", once)

    def test_makefile_patch_is_idempotent(self):
        source = "TEST_OBJS := $(TEST_SRCS_C:.c=.o)\n"
        once = patch_makefile(source)
        self.assertEqual(patch_makefile(once), once)
        self.assertIn("test/goldeneye_intro.o", once)


if __name__ == "__main__":
    unittest.main()
