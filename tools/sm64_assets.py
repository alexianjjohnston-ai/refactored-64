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


POWER_STAR_ASSET_NAME="power-star"
POWER_STAR_SURFACE_OFFSET=0x2A6F0
POWER_STAR_EYE_OFFSET=0x2AEF0
POWER_STAR_BODY_VERTEX_OFFSET=0x2B6F0
POWER_STAR_EYE_VERTEX_OFFSET=0x2B920
POWER_STAR_TEXTURE_BYTES=32*32*2
POWER_STAR_BODY_VERTEX_BYTES=12*16
POWER_STAR_EYE_VERTEX_BYTES=10*16

def rgba16_to_rgba8(data:bytes)->bytes:
    if len(data)%2: raise ValueError("RGBA16 byte count must be even")
    out=bytearray()
    for i in range(0,len(data),2):
        value=(data[i]<<8)|data[i+1]
        out.extend((
            ((value>>11)&31)*255//31,
            ((value>>6)&31)*255//31,
            ((value>>1)&31)*255//31,
            255 if value&1 else 0,
        ))
    return bytes(out)

def extract_power_star_asset(rom:bytes):
    common1=common1_segment(rom)
    expected=struct.pack(">hhhHhhBBBB",0,8,-89,0,0,0,0x00,0x07,0x82,0xff)
    actual=common1[POWER_STAR_BODY_VERTEX_OFFSET:POWER_STAR_BODY_VERTEX_OFFSET+len(expected)]
    if actual!=expected: raise ValueError("SM64 common1 Power Star layout mismatch")
    surface=common1[POWER_STAR_SURFACE_OFFSET:POWER_STAR_SURFACE_OFFSET+POWER_STAR_TEXTURE_BYTES]
    eyes=common1[POWER_STAR_EYE_OFFSET:POWER_STAR_EYE_OFFSET+POWER_STAR_TEXTURE_BYTES]
    body=common1[POWER_STAR_BODY_VERTEX_OFFSET:POWER_STAR_BODY_VERTEX_OFFSET+POWER_STAR_BODY_VERTEX_BYTES]
    eyev=common1[POWER_STAR_EYE_VERTEX_OFFSET:POWER_STAR_EYE_VERTEX_OFFSET+POWER_STAR_EYE_VERTEX_BYTES]
    if len(surface)!=POWER_STAR_TEXTURE_BYTES or len(eyes)!=POWER_STAR_TEXTURE_BYTES:
        raise ValueError("SM64 Power Star texture data is truncated")
    if len(body)!=POWER_STAR_BODY_VERTEX_BYTES or len(eyev)!=POWER_STAR_EYE_VERTEX_BYTES:
        raise ValueError("SM64 Power Star vertex data is truncated")
    return {
        "surface_rgba8":rgba16_to_rgba8(surface),
        "eyes_rgba8":rgba16_to_rgba8(eyes),
        "body_vertices":body,
        "eye_vertices":eyev,
    }

def write_power_star_asset(rom:bytes,root:Path):
    directory=Path(root).expanduser().resolve()/POWER_STAR_ASSET_NAME
    directory.mkdir(parents=True,exist_ok=True)
    asset=extract_power_star_asset(rom)
    paths=[]
    for name,data in (
        ("surface.rgba8",asset["surface_rgba8"]),
        ("eyes.rgba8",asset["eyes_rgba8"]),
        ("body.vtx",asset["body_vertices"]),
        ("eyes.vtx",asset["eye_vertices"]),
    ):
        path=directory/name; path.write_bytes(data); paths.append(path)
    return paths

def read_power_star_asset(root:Path):
    directory=Path(root).expanduser().resolve()/POWER_STAR_ASSET_NAME
    names=("surface.rgba8","eyes.rgba8","body.vtx","eyes.vtx")
    paths=[directory/name for name in names]
    if not all(p.is_file() for p in paths):
        raise FileNotFoundError(f"Missing prepared Power Star asset under {directory}")
    asset={
        "surface_rgba8":paths[0].read_bytes(),
        "eyes_rgba8":paths[1].read_bytes(),
        "body_vertices":paths[2].read_bytes(),
        "eye_vertices":paths[3].read_bytes(),
    }
    if len(asset["surface_rgba8"])!=32*32*4 or len(asset["eyes_rgba8"])!=32*32*4:
        raise ValueError("Prepared Power Star texture has wrong size")
    if len(asset["body_vertices"])!=POWER_STAR_BODY_VERTEX_BYTES or len(asset["eye_vertices"])!=POWER_STAR_EYE_VERTEX_BYTES:
        raise ValueError("Prepared Power Star vertex data has wrong size")
    return asset

ASSET_CATALOG["power_star"]={
    "game":"sm64","segment":"common1","format":"original model + RGBA16 textures",
    "surface_dimensions":[32,32],"eye_dimensions":[32,32],
    "prepared_subdir":POWER_STAR_ASSET_NAME,
}


# Original SM64 in-game HUD assets.
SM64_SEGMENT2_MIO0_OFFSET=0x108A40
SM64_HUD_ASSET_NAME="hud"
SM64_HUD_GLYPH_BYTES=16*16*2
SM64_HUD_GLYPH_OFFSETS={
    **{f"digit-{i}":i*0x200 for i in range(10)},
    "multiply":0x05600,
    "coin":0x05800,
    "mario-head":0x05A00,
    "star":0x05C00,
}
SM64_POWER_BASE_OFFSETS={
    "power-left":(0x233E0,32,64),
    "power-right":(0x243E0,32,64),
}
SM64_POWER_HEALTH_OFFSETS={
    1:0x28BE0, 2:0x283E0, 3:0x27BE0, 4:0x273E0,
    5:0x26BE0, 6:0x263E0, 7:0x25BE0, 8:0x253E0,
}

def segment2_segment(rom:bytes)->bytes:
    verify_us_rom(rom)
    return mio0_decompress(rom,SM64_SEGMENT2_MIO0_OFFSET)

def extract_sm64_hud_asset(rom:bytes):
    segment2=segment2_segment(rom)
    common1=common1_segment(rom)
    result={}
    for name,offset in SM64_HUD_GLYPH_OFFSETS.items():
        raw=segment2[offset:offset+SM64_HUD_GLYPH_BYTES]
        if len(raw)!=SM64_HUD_GLYPH_BYTES:
            raise ValueError(f"SM64 HUD glyph {name} is truncated")
        result[name]=rgba16_to_rgba8(raw)
    for name,(offset,width,height) in SM64_POWER_BASE_OFFSETS.items():
        size=width*height*2
        raw=common1[offset:offset+size]
        if len(raw)!=size: raise ValueError(f"SM64 HUD asset {name} is truncated")
        result[name]=rgba16_to_rgba8(raw)
    for wedges,offset in SM64_POWER_HEALTH_OFFSETS.items():
        raw=common1[offset:offset+32*32*2]
        if len(raw)!=32*32*2: raise ValueError(f"SM64 power meter {wedges} is truncated")
        result[f"power-{wedges}"]=rgba16_to_rgba8(raw)
    return result

def write_sm64_hud_asset(rom:bytes,root:Path):
    directory=Path(root).expanduser().resolve()/SM64_HUD_ASSET_NAME
    directory.mkdir(parents=True,exist_ok=True)
    asset=extract_sm64_hud_asset(rom)
    paths=[]
    for name,data in asset.items():
        path=directory/f"{name}.rgba8"
        path.write_bytes(data); paths.append(path)
    return paths

def read_sm64_hud_asset(root:Path):
    directory=Path(root).expanduser().resolve()/SM64_HUD_ASSET_NAME
    names=list(SM64_HUD_GLYPH_OFFSETS)
    names += list(SM64_POWER_BASE_OFFSETS)
    names += [f"power-{i}" for i in range(1,9)]
    asset={}
    for name in names:
        path=directory/f"{name}.rgba8"
        if not path.is_file(): raise FileNotFoundError(f"Missing prepared SM64 HUD asset: {path}")
        asset[name]=path.read_bytes()
    for name in SM64_HUD_GLYPH_OFFSETS:
        if len(asset[name])!=16*16*4: raise ValueError(f"Prepared HUD glyph {name} has wrong size")
    for name,(_offset,width,height) in SM64_POWER_BASE_OFFSETS.items():
        if len(asset[name])!=width*height*4: raise ValueError(f"Prepared {name} has wrong size")
    for i in range(1,9):
        if len(asset[f"power-{i}"])!=32*32*4: raise ValueError(f"Prepared power-{i} has wrong size")
    return asset

ASSET_CATALOG["hud"]={
    "game":"sm64",
    "segment":"segment2 + common1",
    "format":"original RGBA16 converted locally to RGBA8",
    "glyph_dimensions":[16,16],
    "power_meter_base":[64,64],
    "prepared_subdir":SM64_HUD_ASSET_NAME,
}
