import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parents[1]/"tools"))

from goldeneye_ui_assets import (
    BANK_CHARTABLE_BYTES,
    BANK_GLYPH_COUNT,
    BANK_KERNING_BYTES,
)
from install_ui import patch_makefile


class OriginalUiTests(unittest.TestCase):
    def test_goldeneye_bank_font_resource_shape(self):
        self.assertEqual(BANK_KERNING_BYTES,13*13*4)
        self.assertEqual(BANK_GLYPH_COUNT,94)
        self.assertGreater(BANK_CHARTABLE_BYTES,BANK_GLYPH_COUNT*24)

    def test_makefile_patch_is_idempotent(self):
        source="TEST_OBJS := $(TEST_SRCS_C:.c=.o)\n"
        once=patch_makefile(source)
        self.assertEqual(patch_makefile(once),once)
        self.assertIn("test/mario_goldeneye_ui.o",once)


if __name__=="__main__":
    unittest.main()
