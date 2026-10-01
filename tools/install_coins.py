#!/usr/bin/env python3
"""Install the first Mario collectible-coin gameplay feature into libsm64.

Coin placements are derived locally from GoldenEye STAN tiles. No extracted
ROM assets or generated level coordinates are committed to this repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil

from install_facility import extract
from stan_collision import extract_dam_stan, triangulate_polygon

MARKER = "// MARIO_GOLDENEYE_COINS_V1"
BACKUP = "coins-backup"
COIN_COUNT = 8
COIN_HEIGHT = 110
MIN_SEPARATION = 520
MIN_SPAWN_DISTANCE = 260


def transform(point, origin, scale):
    return tuple(round((point[axis] - origin[axis]) * scale) for axis in range(3))


def choose_coin_positions(tiles, origin, scale, spawn, count=COIN_COUNT):
    candidates = []
    for tile in tiles:
        if tile.get("special", 0) != 0:
            continue
        raw_points = [point[:3] for point in tile["points"]]
        if not triangulate_polygon(raw_points):
            continue
        raw_center = tuple(sum(point[axis] for point in raw_points) / len(raw_points) for axis in range(3))
        world = list(transform(raw_center, origin, scale))
        world[1] += COIN_HEIGHT
        dx = world[0] - spawn[0]
        dz = world[2] - spawn[2]
        distance = math.hypot(dx, dz)
        if distance < MIN_SPAWN_DISTANCE:
            continue
        candidates.append((distance, tuple(world)))

    candidates.sort(key=lambda item: item[0])
    selected = []
    for _distance, point in candidates:
        if all(
            math.hypot(point[0] - existing[0], point[2] - existing[2]) >= MIN_SEPARATION
            for existing in selected
        ):
            selected.append(point)
            if len(selected) == count:
                break

    if len(selected) < count:
        raise ValueError(f"Only found {len(selected)} separated STAN coin positions")
    return selected


def header_source():
    return """#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void mario_goldeneye_coins_tick(int32_t marioId, const float marioPosition[3]);
void mario_goldeneye_coins_draw_gl20(void);
int mario_goldeneye_coins_collected(void);
int mario_goldeneye_coins_total(void);

#ifdef __cplusplus
}
#endif
"""


def c_source(positions):
    encoded = ",\n".join(
        "    {{%.1ff, %.1ff, %.1ff}, 1}" % point
        for point in positions
    )
    return f"""#ifdef __APPLE__
#include <OpenGL/gl.h>
#else
#include <GL/glew.h>
#endif

#include <math.h>
#include <stdio.h>

#include "../src/libsm64.h"
#include "coins.h"

#define COIN_SOUND 0x38118081
#define COIN_RADIUS 88.0f
#define COIN_HALF_THICKNESS 10.0f
#define COIN_PICKUP_RADIUS 170.0f
#define COIN_PICKUP_HEIGHT 230.0f
#define COIN_SIDES 12
#define COIN_PI 3.14159265358979323846f

struct MarioGoldenEyeCoin {{
    float position[3];
    int active;
}};

static struct MarioGoldenEyeCoin gCoins[] = {{
{encoded}
}};

static int gCollected = 0;
static float gSpinDegrees = 0.0f;

int mario_goldeneye_coins_collected(void) {{
    return gCollected;
}}

int mario_goldeneye_coins_total(void) {{
    return (int)(sizeof(gCoins) / sizeof(gCoins[0]));
}}

void mario_goldeneye_coins_tick(int32_t marioId, const float marioPosition[3]) {{
    gSpinDegrees += 12.0f;
    if (gSpinDegrees >= 360.0f) gSpinDegrees -= 360.0f;

    for (int i = 0; i < mario_goldeneye_coins_total(); ++i) {{
        if (!gCoins[i].active) continue;
        float dx = marioPosition[0] - gCoins[i].position[0];
        float dy = marioPosition[1] - gCoins[i].position[1];
        float dz = marioPosition[2] - gCoins[i].position[2];
        if (dx * dx + dz * dz <= COIN_PICKUP_RADIUS * COIN_PICKUP_RADIUS
            && fabsf(dy) <= COIN_PICKUP_HEIGHT) {{
            gCoins[i].active = 0;
            gCollected++;
            // A normal SM64 coin restores one health wedge (4 heal-counter ticks).
            sm64_mario_heal(marioId, 4);
            sm64_play_sound(COIN_SOUND, gCoins[i].position);
            printf("Coin %d/%d\\n", gCollected, mario_goldeneye_coins_total());
            fflush(stdout);
        }}
    }}
}}

static void draw_coin_disc(float z, float normal) {{
    glNormal3f(0.0f, 0.0f, normal);
    glBegin(GL_TRIANGLE_FAN);
    glColor3f(1.0f, 0.92f, 0.18f);
    glVertex3f(0.0f, 0.0f, z);
    glColor3f(1.0f, 0.70f, 0.02f);
    for (int i = 0; i <= COIN_SIDES; ++i) {{
        float angle = (2.0f * COIN_PI * i) / COIN_SIDES;
        glVertex3f(cosf(angle) * COIN_RADIUS, sinf(angle) * COIN_RADIUS, z);
    }}
    glEnd();
}}

void mario_goldeneye_coins_draw_gl20(void) {{
    glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT | GL_LIGHTING_BIT | GL_POLYGON_BIT);
    glDisable(GL_TEXTURE_2D);
    glDisable(GL_LIGHTING);
    glDisable(GL_CULL_FACE);

    for (int i = 0; i < mario_goldeneye_coins_total(); ++i) {{
        if (!gCoins[i].active) continue;
        glPushMatrix();
        glTranslatef(gCoins[i].position[0], gCoins[i].position[1], gCoins[i].position[2]);
        glRotatef(gSpinDegrees, 0.0f, 1.0f, 0.0f);

        draw_coin_disc(COIN_HALF_THICKNESS, 1.0f);
        draw_coin_disc(-COIN_HALF_THICKNESS, -1.0f);

        glColor3f(0.90f, 0.55f, 0.0f);
        glBegin(GL_QUAD_STRIP);
        for (int side = 0; side <= COIN_SIDES; ++side) {{
            float angle = (2.0f * COIN_PI * side) / COIN_SIDES;
            float x = cosf(angle) * COIN_RADIUS;
            float y = sinf(angle) * COIN_RADIUS;
            glVertex3f(x, y, -COIN_HALF_THICKNESS);
            glVertex3f(x, y, COIN_HALF_THICKNESS);
        }}
        glEnd();
        glPopMatrix();
    }}

    glPopAttrib();
}}
"""


def patch_main(source):
    if MARKER in source:
        return source
    include_anchor = '#include "audio.h"'
    tick_anchor = "            sm64_mario_tick( marioId, &marioInputs, &marioState, &marioGeometry );"
    draw_anchor = "        renderer->draw( &renderState, cameraPos, &marioState, &marioGeometry );"
    for anchor, description in (
        (include_anchor, "audio include"),
        (tick_anchor, "Mario tick"),
        (draw_anchor, "renderer draw"),
    ):
        if source.count(anchor) != 1:
            raise ValueError(f"Could not find unique {description} anchor; no coin patch applied")

    source = source.replace(
        include_anchor,
        include_anchor + '\n#include "coins.h"\n' + MARKER,
        1,
    )
    source = source.replace(
        tick_anchor,
        tick_anchor + "\n            mario_goldeneye_coins_tick(marioId, marioState.position);",
        1,
    )
    source = source.replace(
        draw_anchor,
        draw_anchor
        + "\n#ifndef GL33_CORE\n"
        + "        mario_goldeneye_coins_draw_gl20();\n"
        + "#endif",
        1,
    )
    return source


def patch_makefile(source):
    if "test/coins.c" in source:
        return source
    lines = source.splitlines()
    matches = [index for index, line in enumerate(lines) if line.startswith("TEST_SRCS_C")]
    if len(matches) != 1:
        raise ValueError("Could not find unique TEST_SRCS_C Makefile line")
    index = matches[0]
    lines[index] += " test/coins.c"
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


def install(root, rom, level):
    main_path = root / "test/main.cpp"
    makefile_path = root / "Makefile"
    if not main_path.is_file() or not makefile_path.is_file():
        raise ValueError("libsm64 prototype checkout was not found")

    rom_bytes = rom.read_bytes()
    _triangles, _colors, spawn, _room, transform_data = extract(
        rom_bytes, level, include_transform=True
    )
    if level == "dam":
        tiles = extract_dam_stan(rom_bytes)
        positions = choose_coin_positions(
            tiles, transform_data["origin"], transform_data["scale"], spawn
        )
    else:
        positions = []

    main_source = main_path.read_text(encoding="utf-8")
    make_source = makefile_path.read_text(encoding="utf-8")
    patched_main = patch_main(main_source)
    patched_make = patch_makefile(make_source)

    backup = root / BACKUP
    first_install = MARKER not in main_source
    if first_install:
        if backup.exists():
            raise ValueError("coins-backup exists but coin marker is absent; refusing to overwrite")
        backup.mkdir()
        shutil.copy2(main_path, backup / "main.cpp")
        shutil.copy2(makefile_path, backup / "Makefile")

    (root / "test/coins.h").write_text(header_source(), encoding="utf-8")
    (root / "test/coins.c").write_text(c_source(positions), encoding="utf-8")
    main_path.write_text(patched_main, encoding="utf-8")
    makefile_path.write_text(patched_make, encoding="utf-8")

    state = {
        "version": 1,
        "level": level,
        "coin_count": len(positions),
        "main_sha256": hashlib.sha256(main_path.read_bytes()).hexdigest(),
        "makefile_sha256": hashlib.sha256(makefile_path.read_bytes()).hexdigest(),
    }
    backup.mkdir(exist_ok=True)
    (backup / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"Coin feature ready: {len(positions)} collectible coins for {level}.")
    if positions:
        print("Coin pickups use SM64 healing and the original SM64 coin sound; no custom HUD added.")
    print("Coin patch backup:", backup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libsm64", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--level", choices=("dam", "facility"), default="dam")
    args = parser.parse_args()
    install(args.libsm64.expanduser().resolve(), args.rom.expanduser().resolve(), args.level)
