#!/usr/bin/env python3
"""Regenerate the installed GoldenEye level at the project's canonical world scale."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil

from install_facility import extract
from project_constants import GOLDENEYE_WORLD_SCALE


NUMBER = r"-?\\d+(?:\\.\\d+)?f?"


def level_source(triangles) -> str:
    out = ['#include "level.h"', 'const struct SM64Surface surfaces[] = {']
    for triangle in triangles:
        for points in (triangle, list(reversed(triangle))):
            encoded = ",".join("{" + ",".join(map(str, point)) + "}" for point in points)
            out.append("{0,0,0,{" + encoded + "}},")
    out += ["};", "const size_t surfaces_count=sizeof(surfaces)/sizeof(surfaces[0]);"]
    return "\n".join(out) + "\n"


def replace_spawn(source: str, spawn: tuple[int, int, int]) -> str:
    args = ",".join(map(str, spawn))
    source, create_count = re.subn(
        rf"sm64_mario_create\\(\\s*{NUMBER}\\s*,\\s*{NUMBER}\\s*,\\s*{NUMBER}\\s*\\)",
        f"sm64_mario_create({args})",
        source,
    )
    if create_count < 1:
        raise ValueError("Could not find Mario creation spawn in test/main.cpp")

    for axis, value in enumerate(spawn):
        source, count = re.subn(
            rf"marioState\\.position\\[{axis}\\]\\s*=\\s*{NUMBER}\\s*;",
            f"marioState.position[{axis}] = {value};",
            source,
        )
        if count != 1:
            raise ValueError(f"Could not uniquely update Mario state axis {axis}")

    vector = "{" + args + "}"
    source, count = re.subn(
        rf"float lastPos\\[3\\]\\s*=\\s*\\{{[^}}]+\\}}\\s*,\\s*currPos\\[3\\]\\s*=\\s*\\{{[^}}]+\\}}\\s*;",
        f"float lastPos[3] = {vector}, currPos[3] = {vector};",
        source,
    )
    if count != 1:
        raise ValueError("Could not uniquely update interpolated Mario spawn")
    return source


def refresh(root: Path, rom: Path, level: str) -> None:
    main_path = root / "test/main.cpp"
    level_path = root / "test/level.c"
    if not main_path.is_file() or not level_path.is_file():
        raise ValueError("Installed libsm64 prototype files were not found")

    triangles, _colors, spawn, room = extract(rom.read_bytes(), level)
    new_main = replace_spawn(main_path.read_text(encoding="utf-8"), tuple(spawn))
    new_level = level_source(triangles)

    backup = root / "world-scale-backup"
    if not backup.exists():
        backup.mkdir()
        shutil.copy2(main_path, backup / "main.cpp")
        shutil.copy2(level_path, backup / "level.c")

    main_path.write_text(new_main, encoding="utf-8")
    level_path.write_text(new_level, encoding="utf-8")
    print(
        f"Refreshed {level} at {GOLDENEYE_WORLD_SCALE:g}x: "
        f"{len(triangles):,} triangles, spawn room {room}, spawn {tuple(spawn)}"
    )
    print("Original pre-scale files preserved at", backup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libsm64", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--level", choices=("dam", "facility"), default="dam")
    args = parser.parse_args()
    refresh(
        args.libsm64.expanduser().resolve(),
        args.rom.expanduser().resolve(),
        args.level,
    )
