#!/usr/bin/env python3
"""Generate a local, versioned GoldenEye level manifest from a US ROM."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from install_facility import LEVELS, extract  # noqa: E402
from level_manifest import facility_manifest, write_manifest  # noqa: E402

EXPECTED_SHA1 = "abe01e4aeb033b6c0836819f549c791b26cfde83"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--level", choices=sorted(LEVELS), default="facility")
    args = parser.parse_args()
    rom = args.rom.expanduser().resolve()
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    digest = hashlib.sha1(rom.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA1:
        parser.error("Expected the original US GoldenEye .z64 ROM.")
    triangles, colors, spawn, room, materials, texture_coords = extract(rom.read_bytes(), args.level, include_materials=True)
    destination = args.out.expanduser().resolve()
    manifest = facility_manifest(triangles, colors, spawn, room, args.level, materials)
    for triangle, st in zip(manifest['geometry']['triangles'], texture_coords):
        triangle['texture_st_s10_5'] = st
    write_manifest(manifest, destination)
    atlas = destination.with_name(destination.stem + "-materials.ppm")
    import subprocess
    subprocess.run([sys.executable, str(TOOLS / "texture_converter.py"),
                    "--manifest", str(destination), "--out", str(atlas)], check=True)
    print(f"Wrote {args.level.title()} manifest with {len(triangles):,} triangles: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
