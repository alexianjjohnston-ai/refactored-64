import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/"tools"))
from asset_cache import AssetCache,fingerprint
from sm64_assets import mio0_decompress

class AssetFoundationTests(unittest.TestCase):
    def test_cache_matches_fingerprint_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); output=root/"x.bin"; output.write_bytes(b"ok")
            cache=AssetCache(root); fp=fingerprint("x",1)
            self.assertFalse(cache.is_fresh("x",fp,[output]))
            cache.mark("x",fp,[output])
            self.assertTrue(AssetCache(root).is_fresh("x",fp,[output]))
            self.assertFalse(cache.is_fresh("x",fingerprint("x",2),[output]))
            output.unlink(); self.assertFalse(cache.is_fresh("x",fp,[output]))

    def test_cache_is_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); output=root/"x"; output.write_bytes(b"x")
            AssetCache(root).mark("x",fingerprint("x"),[output])
            data=json.loads((root/".asset-cache.json").read_text())
            self.assertEqual(data["schema"],1); self.assertIn("x",data["entries"])

    def test_shared_mio0_literal_decode(self):
        blob=b"MIO0"+(4).to_bytes(4,"big")+(17).to_bytes(4,"big")+(17).to_bytes(4,"big")+bytes([0xF0])+b"ABCD"
        self.assertEqual(mio0_decompress(blob,0),b"ABCD")

if __name__=="__main__": unittest.main()
