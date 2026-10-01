#!/usr/bin/env python3
"""Extract the local GoldenEye texture blobs referenced by a level manifest.

The image index contains offsets and sizes only; the ROM remains the source
of truth and all output is written to the caller's generated-data directory.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from urllib.request import urlopen

INDEX_URL = "https://raw.githubusercontent.com/jkdansereau/goldeneye-pc-port/main/imagelist.u.csv"


def load_index(cache: Path) -> list[tuple[int, int]]:
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(urlopen(INDEX_URL, timeout=20).read())
    with cache.open(newline="", encoding="utf-8") as handle:
        return [(int(row[0]), int(row[1])) for row in csv.reader(handle) if row]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--index-cache", type=Path)
    args = parser.parse_args()
    manifest = __import__("json").loads(args.manifest.expanduser().read_text(encoding="utf-8"))
    ids = sorted({int(t["material_id"]) for t in manifest["geometry"]["triangles"]
                  if int(t.get("material_id", 0)) >= 0})
    cache = args.index_cache or args.out.expanduser() / "imagelist.u.csv"
    rows = load_index(cache.expanduser())
    rom = args.rom.expanduser().read_bytes()
    out = args.out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    extracted = []
    for texture_id in ids:
        if texture_id >= len(rows):
            continue
        offset, size = rows[texture_id]
        blob = rom[offset:offset + size]
        if len(blob) != size:
            continue
        path = out / f"texture-{texture_id:04d}.bin"
        path.write_bytes(blob)
        extracted.append({"id": texture_id, "offset": offset, "size": size, "file": path.name})
    (out / "textures.json").write_text(__import__("json").dumps(extracted, indent=2) + "\n", encoding="utf-8")
    print(f"Extracted {len(extracted)} local GoldenEye texture blobs to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
