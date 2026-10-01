import importlib.util
import struct
import sys
from pathlib import Path
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from decode_goldeneye_textures import png

class TextureOutputTests(unittest.TestCase):
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
