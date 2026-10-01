#!/usr/bin/env python3
"""Regenerate the installed GoldenEye level at the project's canonical world scale."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil

from install_facility import extract
from stan_collision import build_dam_collision
from project_constants import GOLDENEYE_WORLD_SCALE


NUMBER = r"-?\d+(?:\.\d+)?f?"


def level_source(triangles, double_sided=True) -> str:
    out = ['#include "level.h"', 'const struct SM64Surface surfaces[] = {']
    for triangle in triangles:
        windings = (triangle, list(reversed(triangle))) if double_sided else (triangle,)
        for points in windings:
            encoded = ",".join("{" + ",".join(map(str, point)) + "}" for point in points)
            out.append("{0,0,0,{" + encoded + "}},")
    out += ["};", "const size_t surfaces_count=sizeof(surfaces)/sizeof(surfaces[0]);"]
    return "\n".join(out) + "\n"


def replace_spawn(source: str, spawn: tuple[int, int, int]) -> str:
    args = ",".join(map(str, spawn))

    # Update every sm64_mario_create(x,y,z) in the prototype. This covers both
    # initial spawn and the fall-reset path without depending on old coordinates.
    source, create_count = re.subn(
        r"sm64_mario_create\(\s*-?\d+(?:\.\d+)?f?\s*,\s*-?\d+(?:\.\d+)?f?\s*,\s*-?\d+(?:\.\d+)?f?\s*\)",
        f"sm64_mario_create({args})",
        source,
    )
    if create_count < 1:
        raise ValueError("Could not find Mario creation spawn in test/main.cpp")

    for axis, value in enumerate(spawn):
        source, count = re.subn(
            rf"marioState\.position\[{axis}\]\s*=\s*-?\d+(?:\.\d+)?f?\s*;",
            f"marioState.position[{axis}] = {value};",
            source,
        )
        if count != 1:
            raise ValueError(f"Could not uniquely update Mario state axis {axis}")

    vector = "{" + args + "}"
    source, count = re.subn(
        r"float lastPos\[3\]\s*=\s*\{[^}]+\}\s*,\s*currPos\[3\]\s*=\s*\{[^}]+\}\s*;",
        f"float lastPos[3] = {vector}, currPos[3] = {vector};",
        source,
    )
    if count != 1:
        raise ValueError("Could not uniquely update interpolated Mario spawn")
    return source


def replace_fall_reset(source: str, death_y: int, spawn: tuple[int, int, int]) -> str:
    # Existing check from older installs: update it in place regardless of
    # whitespace or numeric suffix. Some local prototypes do not contain this
    # check at all, so fall back to inserting one before the position copy.
    source, count = re.subn(
        r"marioState\.position\[1\]\s*<\s*-?\d+(?:\.\d+)?f?",
        f"marioState.position[1] < {death_y}",
        source,
    )
    if count:
        return source

    anchor = "memcpy(currPos, marioState.position, sizeof(currPos));"
    if source.count(anchor) != 1:
        raise ValueError("Could not find a unique Mario position-copy anchor for fall reset")

    args = ",".join(map(str, spawn))
    reset = (
        f"if (marioState.position[1] < {death_y}) {{ "
        f"sm64_mario_delete(marioId); marioId = sm64_mario_create({args}); }}\n"
        "            "
    )
    return source.replace(anchor, reset + anchor)

def refresh_renderer_distance(root: Path, backup: Path) -> None:
    for relative in ("test/gl20/gl20_renderer.c", "test/gl33core/gl33core_renderer.c"):
        path = root / relative
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        updated = source.replace("10.0f, 30000.0f", "10.0f, 100000.0f")
        updated = updated.replace("100.0f, 20000.0f", "10.0f, 100000.0f")
        if updated == source:
            continue
        saved = backup / Path(relative).name
        if not saved.exists():
            shutil.copy2(path, saved)
        path.write_text(updated, encoding="utf-8")


def refresh(root: Path, rom: Path, level: str) -> None:
    main_path = root / "test/main.cpp"
    level_path = root / "test/level.c"
    if not main_path.is_file() or not level_path.is_file():
        raise ValueError("Installed libsm64 prototype files were not found")

    rom_bytes = rom.read_bytes()
    triangles, _colors, spawn, room, transform = extract(
        rom_bytes, level, include_transform=True
    )
    collision_triangles = triangles
    double_sided = True
    collision = None
    if level == "dam":
        collision_triangles, spawn, collision = build_dam_collision(
            rom_bytes, transform["origin"], transform["scale"], spawn
        )
        room = collision["spawn_room"]
        double_sided = False

    new_main = replace_spawn(main_path.read_text(encoding="utf-8"), tuple(spawn))
    if collision is not None:
        new_main = replace_fall_reset(new_main, collision["death_y"], tuple(spawn))
    new_level = level_source(collision_triangles, double_sided=double_sided)

    backup = root / "world-scale-backup"
    if not backup.exists():
        backup.mkdir()
        shutil.copy2(main_path, backup / "main.cpp")
        shutil.copy2(level_path, backup / "level.c")

    main_path.write_text(new_main, encoding="utf-8")
    level_path.write_text(new_level, encoding="utf-8")
    refresh_renderer_distance(root, backup)
    bounds = [
        (min(p[axis] for tri in triangles for p in tri),
         max(p[axis] for tri in triangles for p in tri))
        for axis in range(3)
    ]
    print(
        f"Refreshed {level} at {GOLDENEYE_WORLD_SCALE:g}x: "
        f"{len(triangles):,} triangles, spawn room {room}, spawn {tuple(spawn)}"
    )
    print(f"Rendered world bounds X={bounds[0]} Y={bounds[1]} Z={bounds[2]}")
    if collision is not None:
        collision_bounds = [
            (min(p[axis] for tri in collision_triangles for p in tri),
             max(p[axis] for tri in collision_triangles for p in tri))
            for axis in range(3)
        ]
        print(
            f"Installed Dam STAN collision: {collision['floor_triangles']:,} floor triangles, "
            f"{collision['wall_triangles']:,} boundary-wall triangles."
        )
        print(
            f"Collision bounds X={collision_bounds[0]} Y={collision_bounds[1]} "
            f"Z={collision_bounds[2]}; fall reset Y={collision['death_y']}."
        )
        print(
            f"Spawn snapped to legal STAN room {collision['spawn_room']} at {tuple(spawn)} "
            f"(raw snap distance {collision['spawn_snap_distance_raw']:.1f})."
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
