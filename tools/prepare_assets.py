#!/usr/bin/env python3
"""Prepare/cache reusable local assets without patching gameplay."""
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
from asset_cache import AssetCache,fingerprint,sha1_file,sha256_file
from sm64_assets import ASSET_CATALOG,MARIO_SHA1,write_power_star_asset,write_sm64_hud_asset,write_yellow_coin_asset\nfrom goldeneye_ui_assets import write_bank_gothic_asset

TOOLS=Path(__file__).resolve().parent
GOLDENEYE_SHA1="abe01e4aeb033b6c0836819f549c791b26cfde83"
REFERENCE_REVISION="0e8c2ce2135ce56bd09e0c3a0f76a74d2ed6337f"

def run(command):
    print("+"," ".join(command)); subprocess.run(command,check=True)

def cached_run(cache,key,fp,outputs,command):
    outputs=[Path(p) for p in outputs]
    if cache.is_fresh(key,fp,outputs):
        print("Using cached assets:",key); return
    run(command)
    missing=[str(p) for p in outputs if not p.is_file()]
    if missing: raise RuntimeError(f"{key} missing outputs: {missing}")
    cache.mark(key,fp,outputs)

def prepare_sm64(cache,mario,generated):
    root=generated/"sm64"
    outputs=[root/"yellow-coin"/f"frame-{i}.ia16" for i in range(4)]
    outputs += [
        root/"power-star"/"surface.rgba8",
        root/"power-star"/"eyes.rgba8",
        root/"power-star"/"body.vtx",
        root/"power-star"/"eyes.vtx",
    ]
    outputs += [root/"hud"/f"digit-{i}.rgba8" for i in range(10)]
    outputs += [
        root/"hud"/"multiply.rgba8",
        root/"hud"/"coin.rgba8",
        root/"hud"/"mario-head.rgba8",
        root/"hud"/"star.rgba8",
        root/"hud"/"power-left.rgba8",
        root/"hud"/"power-right.rgba8",
    ]
    outputs += [root/"hud"/f"power-{i}.rgba8" for i in range(1,9)]
    fp=fingerprint("sm64-shared-v2",sha1_file(mario),json.dumps(ASSET_CATALOG,sort_keys=True),
                   files=(TOOLS/"sm64_assets.py",))
    if cache.is_fresh("sm64.shared",fp,outputs):
        print("Using cached assets: sm64.shared")
    else:
        rom=mario.read_bytes()
        write_yellow_coin_asset(rom,root)
        write_power_star_asset(rom,root)
        write_sm64_hud_asset(rom,root)
        cache.mark("sm64.shared",fp,outputs)
        print("Prepared shared SM64 assets:",root)
    return {"root":str(root),"catalog":ASSET_CATALOG}

def prepare_goldeneye_ui(cache,goldeneye,generated):
    root=generated/"goldeneye"
    outputs=[
        root/"ui"/"bank-gothic"/"font.bin",
        root/"ui"/"bank-gothic"/"font.json",
    ]
    fp=fingerprint(
        "goldeneye-ui-v1",
        sha1_file(goldeneye),
        files=(TOOLS/"goldeneye_ui_assets.py",),
    )
    if cache.is_fresh("goldeneye.ui",fp,outputs):
        print("Using cached assets: goldeneye.ui")
    else:
        write_bank_gothic_asset(goldeneye.read_bytes(),root)
        cache.mark("goldeneye.ui",fp,outputs)
        print("Prepared original GoldenEye UI assets:",root/"ui")
    return {"root":str(root),"bank_gothic":str(root/"ui"/"bank-gothic")}

def prepare_level(cache,goldeneye,generated,level):
    manifest=generated/f"{level}.json"
    texroot=generated/f"{level}-textures"; decoded=texroot/"decoded"
    fp=fingerprint("ge-manifest-v2",sha1_file(goldeneye),level,
        files=(TOOLS/"generate_level_manifest.py",TOOLS/"install_facility.py",
               TOOLS/"level_manifest.py",TOOLS/"project_constants.py"))
    cached_run(cache,f"goldeneye.{level}.manifest",fp,[manifest],[
        sys.executable,str(TOOLS/"generate_level_manifest.py"),"--rom",str(goldeneye),
        "--level",level,"--out",str(manifest)])
    raw_index=texroot/"textures.json"
    fp=fingerprint("ge-textures-raw-v2",sha1_file(goldeneye),sha256_file(manifest),
                   files=(TOOLS/"extract_goldeneye_textures.py",))
    cached_run(cache,f"goldeneye.{level}.textures.raw",fp,[raw_index],[
        sys.executable,str(TOOLS/"extract_goldeneye_textures.py"),"--rom",str(goldeneye),
        "--manifest",str(manifest),"--out",str(texroot)])
    decoded_index=decoded/"decoded.json"; reference=generated/".references"/"goldeneye-pc-port"
    fp=fingerprint("ge-textures-decoded-v2",sha256_file(manifest),sha256_file(raw_index),
                   REFERENCE_REVISION,files=(TOOLS/"decode_goldeneye_textures.py",TOOLS/"ge_texture_raw.c"))
    cached_run(cache,f"goldeneye.{level}.textures.decoded",fp,[decoded_index],[
        sys.executable,str(TOOLS/"decode_goldeneye_textures.py"),"--rom",str(goldeneye),
        "--manifest",str(manifest),"--textures",str(texroot),"--out",str(decoded),
        "--reference",str(reference)])
    return {"manifest":str(manifest),"textures":str(texroot),"decoded":str(decoded)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--goldeneye",type=Path,required=True); p.add_argument("--mario",type=Path,required=True)
    p.add_argument("--generated",type=Path,required=True)
    p.add_argument("--level",action="append",choices=("dam","facility"))
    a=p.parse_args(); ge=a.goldeneye.expanduser().resolve(); mario=a.mario.expanduser().resolve()
    generated=a.generated.expanduser().resolve(); generated.mkdir(parents=True,exist_ok=True)
    if sha1_file(ge)!=GOLDENEYE_SHA1: raise ValueError("Expected original US GoldenEye ROM")
    if sha1_file(mario)!=MARIO_SHA1: raise ValueError("Expected original US Super Mario 64 ROM")
    cache=AssetCache(generated)
    index={"schema":1,"sources":{"goldeneye_sha1":GOLDENEYE_SHA1,"mario_sha1":MARIO_SHA1,"roms_stay_local":True},
           "sm64":prepare_sm64(cache,mario,generated),
           "goldeneye":{"ui":prepare_goldeneye_ui(cache,ge,generated)}}
    for level in dict.fromkeys(a.level or ["dam"]):
        index["goldeneye"][level]=prepare_level(cache,ge,generated,level)
    (generated/"asset-index.json").write_text(json.dumps(index,indent=2)+"\n")
    print("Prepared local asset index:",generated/"asset-index.json")
    return 0

if __name__=="__main__": raise SystemExit(main())
