import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from level_manifest import facility_manifest, read_manifest, validate_manifest, write_manifest


class ManifestTests(unittest.TestCase):
    def sample(self):
        return facility_manifest(
            [[[(0, 0, 0), (1, 0, 0), (0, 1, 0)]]][0],
            [[[(1, 0, 0), (0, 1, 0), (0, 0, 1)]]][0],
            (0, 10, 0),
            1,
        )

    def test_round_trip(self):
        manifest = self.sample()
        self.assertEqual(validate_manifest(manifest), [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "facility.json"
            write_manifest(manifest, path)
            self.assertEqual(read_manifest(path), manifest)

    def test_rejects_missing_geometry(self):
        manifest = self.sample()
        manifest["geometry"]["triangles"] = []
        self.assertTrue(validate_manifest(manifest))

    def test_is_json_without_rom_data(self):
        text = json.dumps(self.sample())
        self.assertNotIn("ROM", text)


if __name__ == "__main__":
    unittest.main()
