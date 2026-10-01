import importlib.util
import struct
import sys
from pathlib import Path
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from decode_goldeneye_textures import png
from install_textures import texture_uv

class TextureOutputTests(unittest.TestCase):
    def test_uv_applies_shift_scale_and_half_texel_offset(self):
        state=dict(type=0,shift=[15,1],scale=[32768,65535],offset=2)
        texture=dict(width=32,height=64,explicit_lods=False)
        uv=texture_uv([1024,2048],state,texture)
        self.assertAlmostEqual(uv[0],31.5/32)
        self.assertAlmostEqual(uv[1],(32*65535/65536-.5)/64)

    def test_simple_material_ignores_detail_shift(self):
        state=dict(type=2,shift=[15,15],scale=[32768,32768],offset=2)
        texture=dict(width=32,height=32,explicit_lods=True)
        self.assertEqual(texture_uv([1024,-1024],state,texture),[.5,-.5])

    def test_png_preserves_rgba_and_rows(self):
        pixels=bytes([255,0,0,0,0,255,0,127,0,0,255,255,255,255,255,255])
        data=png(2,2,pixels)
        self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
        pos=8; payload=b''
        while pos<len(data):
            size=struct.unpack_from('>I',data,pos)[0]
            kind=data[pos+4:pos+8]; body=data[pos+8:pos+8+size]
            self.assertEqual(zlib.crc32(kind+body),struct.unpack_from('>I',data,pos+8+size)[0])
            if kind==b'IDAT': payload+=body
            pos+=12+size
        self.assertEqual(zlib.decompress(payload),b'\0'+pixels[:8]+b'\0'+pixels[8:])
