#!/usr/bin/env python3
"""Shared local extractors for reusable Super Mario 64 assets."""
from __future__ import annotations
import hashlib, struct
from pathlib import Path

MARIO_SHA1="9bef1128717f958171a4afac3ed78ee2bb4e86ce"
SM64_COMMON1_MIO0_OFFSET=0x201410
YELLOW_COIN_VERTEX_OFFSET=0x56C0
YELLOW_COIN_TEXTURE_OFFSETS=(0x5780,0x5F80,0x6780,0x6F80)
YELLOW_COIN_TEXTURE_BYTES=32*32*2
YELLOW_COIN_ASSET_NAME="yellow-coin"

def verify_us_rom(rom:bytes):
    if hashlib.sha1(rom).hexdigest()!=MARIO_SHA1:
        raise ValueError("Expected the original US Super Mario 64 .z64 ROM")

def mio0_decompress(rom:bytes,offset:int)->bytes:
    if rom[offset:offset+4]!=b"MIO0": raise ValueError(f"MIO0 header missing at {offset:#x}")
    size,comp_off,raw_off=struct.unpack_from(">III",rom,offset+4)
    cmd_pos=offset+16; comp_pos=offset+comp_off; raw_pos=offset+raw_off
    out=bytearray(); cmd=0; bits=0
    while len(out)<size:
        if bits==0:
            cmd=rom[cmd_pos]; cmd_pos+=1; bits=8
        literal=cmd&0x80; cmd=(cmd<<1)&0xff; bits-=1
        if literal:
            out.append(rom[raw_pos]); raw_pos+=1
        else:
            first,second=rom[comp_pos],rom[comp_pos+1]; comp_pos+=2
            length=(first>>4)+3; distance=(((first&15)<<8)|second)+1
            if distance>len(out): raise ValueError("Invalid MIO0 back-reference")
            for _ in range(length):
                out.append(out[-distance])
                if len(out)==size: break
    return bytes(out)

def common1_segment(rom:bytes)->bytes:
    verify_us_rom(rom)
    return mio0_decompress(rom,SM64_COMMON1_MIO0_OFFSET)

def extract_yellow_coin_frames(rom:bytes)->list[bytes]:
    common1=common1_segment(rom)
    expected=struct.pack(">hhhHhhBBBB",-32,0,0,0,0,1984,0xff,0xff,0x00,0xff)
    actual=common1[YELLOW_COIN_VERTEX_OFFSET:YELLOW_COIN_VERTEX_OFFSET+len(expected)]
    if actual!=expected: raise ValueError("SM64 common1 coin layout mismatch")
    frames=[common1[o:o+YELLOW_COIN_TEXTURE_BYTES] for o in YELLOW_COIN_TEXTURE_OFFSETS]
    if any(len(f)!=YELLOW_COIN_TEXTURE_BYTES for f in frames):
        raise ValueError("SM64 yellow-coin texture data is truncated")
    return frames

def write_yellow_coin_asset(rom:bytes,root:Path):
    directory=Path(root).expanduser().resolve()/YELLOW_COIN_ASSET_NAME
    directory.mkdir(parents=True,exist_ok=True)
    paths=[]
    for i,frame in enumerate(extract_yellow_coin_frames(rom)):
        path=directory/f"frame-{i}.ia16"; path.write_bytes(frame); paths.append(path)
    return paths

def read_yellow_coin_asset(root:Path):
    directory=Path(root).expanduser().resolve()/YELLOW_COIN_ASSET_NAME
    paths=[directory/f"frame-{i}.ia16" for i in range(4)]
    if not all(p.is_file() for p in paths): raise FileNotFoundError(f"Missing prepared coin asset under {directory}")
    frames=[p.read_bytes() for p in paths]
    if any(len(f)!=YELLOW_COIN_TEXTURE_BYTES for f in frames): raise ValueError("Prepared coin frame has wrong size")
    return frames

ASSET_CATALOG={
    "yellow_coin":{
        "game":"sm64","segment":"common1","format":"IA16",
        "dimensions":[32,32],"frames":4,"prepared_subdir":YELLOW_COIN_ASSET_NAME,
    }
}
