import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from stan_collision import (
    DAM_MISSION_START_RAW,
    build_collision_from_tiles,
    dam_mission_start,
    parse_stan,
    triangulate_polygon,
)


def normal_y(triangle):
    a = [triangle[1][axis] - triangle[0][axis] for axis in range(3)]
    b = [triangle[2][axis] - triangle[0][axis] for axis in range(3)]
    return a[2] * b[0] - a[0] * b[2]


class StanCollisionTests(unittest.TestCase):
    def square(self, links=(0, 0, 0, 0)):
        return [{
            "room": 7,
            "special": 0,
            "points": [
                (0, 0, 0, links[0]),
                (10, 0, 0, links[1]),
                (10, 0, 10, links[2]),
                (0, 0, 10, links[3]),
            ],
        }]

    def test_dam_mission_start_uses_original_spawn_pad(self):
        self.assertEqual(DAM_MISSION_START_RAW, (4719.0, -18.0, 3949.0))
        self.assertEqual(
            dam_mission_start((-303.0, -200.0, -1008.5), 4.0),
            (20088, 728, 19830),
        )

    def test_concave_polygon_ear_clips(self):
        points = [(0, 0, 0), (10, 0, 0), (5, 0, 5), (10, 0, 10), (0, 0, 10)]
        self.assertEqual(len(triangulate_polygon(points)), 3)

    def test_unlinked_square_builds_floor_and_boundary_walls(self):
        triangles, spawn, metadata = build_collision_from_tiles(
            self.square(), (0, 0, 0), 1.0, (5, 60, 5)
        )
        self.assertEqual(metadata["floor_triangles"], 2)
        self.assertEqual(metadata["wall_triangles"], 8)
        self.assertEqual(len(triangles), 10)
        self.assertEqual(spawn, (5, 60, 5))
        self.assertEqual(metadata["spawn_room"], 7)
        self.assertTrue(all(normal_y(triangle) > 0 for triangle in triangles[:2]))

    def test_linked_edge_stays_open(self):
        _triangles, _spawn, metadata = build_collision_from_tiles(
            self.square((0x20, 0, 0, 0)), (0, 0, 0), 1.0, (5, 60, 5)
        )
        self.assertEqual(metadata["wall_triangles"], 6)

    def test_parse_release_stan_tile(self):
        point_data = b"".join(
            struct.pack(">hhhH", *point)
            for point in ((0, 0, 0, 0), (10, 0, 0, 0), (0, 0, 10, 0))
        )
        tile = b"\x00\x00\x01\x07" + struct.pack(">HH", 0x0FFF, 0x3012) + point_data
        blob = b"\0\0\0\0" + struct.pack(">I", 8) + tile + b"\0" * 8 + b"unstric\0" + b"\0" * 16
        parsed = parse_stan(blob)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["room"], 7)
        self.assertEqual(len(parsed[0]["points"]), 3)


if __name__ == "__main__":
    unittest.main()
