#!/usr/bin/env python3
"""Decode local ROM slices to RGBA8 using pinned libpdtex source."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib

REFERENCE_URL = 'https://github.com/jkdansereau/goldeneye-pc-port.git'
REVISION = '0e8c2ce2135ce56bd09e0c3a0f76a74d2ed6337f'
TOOLS = Path(__file__).resolve().parent

def decode_lookup(blob, reference):
    """Use the reference's endian-independent lookup codec for methods 5-7."""
    if blob[0]&64 or (blob[3]&15) not in (5,6,7):
        return None
    sys.path.insert(0,str(reference/'tools_pc'))
    try:
        spec=importlib.util.spec_from_file_location('ge_reference_texdecode',reference/'tools_pc/texdecode.py')
        decoder=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(decoder)
    finally:
        sys.path.pop(0)
    bits=decoder.Bits(blob,1)
    fmt,w,h,cm=bits.read(4),bits.read(8),bits.read(8),bits.read(4)
    if not 0<w<=256 or not 0<h<=256: raise ValueError('Invalid dimensions')
    rows=decoder.decode_image(bits,fmt,w,h,cm)
    pixels=bytearray()
    for row in rows:
        for v in row:
            if fmt==0: rgba=tuple(v.to_bytes(4,'big'))
            elif fmt==1: rgba=((v>>11)*255//31,((v>>6)&31)*255//31,((v>>1)&31)*255//31,(v&1)*255)
            elif fmt==2: rgba=(*v.to_bytes(3,'big'),255)
            elif fmt==3: rgba=((v>>10)*255//31,((v>>5)&31)*255//31,(v&31)*255//31,255)
            elif fmt==4: rgba=(v>>8,v>>8,v>>8,v&255)
            elif fmt==5: rgba=((v>>4)*17,)*3+((v&15)*17,)
            elif fmt==6: rgba=((v>>1)*255//7,)*3+((v&1)*255,)
            elif fmt==7: rgba=(v,)*3+(255,)
            elif fmt==8: rgba=(v*17,)*3+(255,)
            else: raise ValueError('Unsupported lookup format')
            pixels.extend(rgba)
    return w,h,fmt,bytes(pixels)

def png(width, height, pixels):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    scan = b''.join(b'\0'+pixels[y*width*4:(y+1)*width*4] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))
            +chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b''))

def main():
    p=argparse.ArgumentParser()
    for name in ('rom','manifest','textures','out'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--reference',type=Path)
    a=p.parse_args()
    if hashlib.sha1(a.rom.read_bytes()).hexdigest()!='abe01e4aeb033b6c0836819f549c791b26cfde83':
        raise ValueError('Expected original US GoldenEye ROM')
    manifest=json.loads(a.manifest.read_text())
    ids=sorted({t['material_id'] for t in manifest['geometry']['triangles']})
    reference=(a.reference or a.out.parent/'.goldeneye-pc-port').resolve()
    if not reference.exists():
        subprocess.run(['git','clone',REFERENCE_URL,str(reference)],check=True)
        subprocess.run(['git','-C',str(reference),'checkout','--detach',REVISION],check=True)
    revision=subprocess.check_output(['git','-C',str(reference),'rev-parse','HEAD'],text=True).strip()
    if revision!=REVISION:
        raise ValueError('Texture reference revision mismatch: '+revision)
    a.out.mkdir(parents=True,exist_ok=True)
    src=reference/'tools/mktex/src/libpdtex'
    with tempfile.TemporaryDirectory(prefix='ge-decode-') as tmp:
        exe=Path(tmp)/'decode'
        subprocess.run(['cc','-O2','-I'+str(src),str(TOOLS/'ge_texture_raw.c'),
                        *[str(src/(n+'.c')) for n in ('pdtex','reader','writer')],'-lz','-o',str(exe)],check=True)
        entries=[]
        for tid in ids:
            stem=f'texture-{tid:04d}'
            source=a.textures/(stem+'.bin')
            target=Path(tmp)/(stem+'.rgba')
            decoded=decode_lookup(source.read_bytes(),reference)
            if decoded is None:
                r=subprocess.run([str(exe),str(source),str(target)],capture_output=True,text=True,timeout=20,check=True)
                w,h,fmt=map(int,r.stdout.split())
                pixels=target.read_bytes()
            else:
                w,h,fmt,pixels=decoded
            if len(pixels)!=w*h*4:
                raise ValueError(f'Wrong pixel count for {tid}')
            (a.out/(stem+'.rgba')).write_bytes(pixels)
            (a.out/(stem+'.png')).write_bytes(png(w,h,pixels))
            entries.append(dict(id=tid,width=w,height=h,format=fmt,file=stem+'.rgba',
                                explicit_lods=bool(source.read_bytes()[0]&128),
                                sha256=hashlib.sha256(pixels).hexdigest()))
        (a.out/'decoded.json').write_text(json.dumps(dict(revision=revision,textures=entries),indent=2)+'\n')
        print(f'Decoded {len(entries)} referenced textures to RGBA8 and PNG: {a.out}')

if __name__=='__main__':
    main()
