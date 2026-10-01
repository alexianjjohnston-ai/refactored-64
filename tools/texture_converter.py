#!/usr/bin/env python3
"""Create local GoldenEye material swatches from a generated level manifest.

This is intentionally dependency-free. It creates a small PPM atlas from the
decoded vertex palette so the renderer has a deterministic local material
asset while N64 texture/palette command decoding is added.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--size", type=int, default=16)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.expanduser().read_text(encoding="utf-8"))
    colors = []
    for triangle in manifest["geometry"]["triangles"]:
        for color in triangle["colors"]:
            rgb = tuple(max(0, min(255, round(channel * 255))) for channel in color)
            if rgb not in colors:
                colors.append(rgb)
    size = max(4, args.size)
    atlas = max(size, ((len(colors) + size - 1) // size) * size)
    pixels = [(32, 32, 36)] * (atlas * atlas)
    for index, color in enumerate(colors):
        x = index % atlas
        y = index // atlas
        for py in range(size):
            for px in range(size):
                pixels[(y * size + py) * atlas + x * size + px] = color
    out = args.out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as handle:
        handle.write(f"P6\n{atlas} {atlas}\n255\n".encode("ascii"))
        handle.write(bytes(channel for pixel in pixels for channel in pixel))
    print(f"Wrote local material atlas with {len(colors)} swatches: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
