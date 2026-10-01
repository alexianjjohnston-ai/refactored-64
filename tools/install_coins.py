#!/usr/bin/env python3
"""Install SM64 collectible coins into the Mario/GoldenEye libsm64 prototype.

GoldenEye STAN supplies collision-safe pickup positions. The four original
yellow-coin IA16 animation frames are extracted locally from the user's US
Super Mario 64 ROM; no extracted Nintendo assets are stored in this repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct

from install_facility import extract
from stan_collision import dam_mission_start, extract_dam_stan, triangulate_polygon

MARKER = "// MARIO_GOLDENEYE_COINS_V1"
BACKUP = "coins-backup"

MARIO_SHA1 = "9bef1128717f958171a4afac3ed78ee2bb4e86ce"
SM64_COMMON1_MIO0_OFFSET = 0x201410
SM64_COIN_VERTEX_OFFSET = 0x56C0
SM64_COIN_TEXTURE_OFFSETS = (0x5780, 0x5F80, 0x6780, 0x6F80)
SM64_COIN_TEXTURE_BYTES = 32 * 32 * 2

COIN_COUNT = 8
MIN_SEPARATION = 520.0
MIN_SPAWN_DISTANCE = 260.0
MIN_BOUNDARY_CLEARANCE = 140.0


def transform(point, origin, scale):
    return tuple(round((point[axis] - origin[axis]) * scale) for axis in range(3))


def _distance_to_segment_xz(point, start, end):
    dx = end[0] - start[0]
    dz = end[2] - start[2]
    denominator = dx * dx + dz * dz
    if denominator == 0:
        return math.hypot(point[0] - start[0], point[2] - start[2])
    amount = max(
        0.0,
        min(
            1.0,
            ((point[0] - start[0]) * dx + (point[2] - start[2]) * dz)
            / denominator,
        ),
    )
    nearest_x = start[0] + amount * dx
    nearest_z = start[2] + amount * dz
    return math.hypot(point[0] - nearest_x, point[2] - nearest_z)


def _tile_coin_candidate(tile, origin, scale):
    """Pick a point guaranteed to sit on one generated STAN floor triangle."""
    raw_points = [point[:3] for point in tile["points"]]
    triangle_indices = triangulate_polygon(raw_points)
    if not triangle_indices:
        return None

    world_points = [transform(point, origin, scale) for point in raw_points]
    boundary_edges = [
        (world_points[index], world_points[(index + 1) % len(world_points)])
        for index, point in enumerate(tile["points"])
        if (point[3] >> 4) == 0
    ]

    best = None
    for indices in triangle_indices:
        triangle = [world_points[index] for index in indices]
        point = tuple(
            sum(vertex[axis] for vertex in triangle) / 3.0
            for axis in range(3)
        )
        clearance = min(
            (
                _distance_to_segment_xz(point, start, end)
                for start, end in boundary_edges
            ),
            default=float("inf"),
        )
        if best is None or clearance > best[1]:
            best = (point, clearance)

    return best


def choose_coin_positions(tiles, origin, scale, spawn, count=COIN_COUNT):
    candidates = []
    checked = 0
    for tile in tiles:
        if tile.get("special", 0) != 0:
            continue
        candidate = _tile_coin_candidate(tile, origin, scale)
        if candidate is None:
            continue
        checked += 1
        point, clearance = candidate
        if clearance < MIN_BOUNDARY_CLEARANCE:
            continue
        distance = math.hypot(point[0] - spawn[0], point[2] - spawn[2])
        if distance < MIN_SPAWN_DISTANCE:
            continue
        candidates.append((distance, point, clearance, tile["room"]))

    candidates.sort(key=lambda item: item[0])
    selected = []
    for _distance, point, clearance, room in candidates:
        if all(
            math.hypot(point[0] - existing[0][0], point[2] - existing[0][2])
            >= MIN_SEPARATION
            for existing in selected
        ):
            selected.append((point, clearance, room))
            if len(selected) == count:
                break

    if len(selected) < count:
        raise ValueError(
            f"Only found {len(selected)} collision-safe STAN coin positions"
        )

    positions = [entry[0] for entry in selected]
    metadata = {
        "checked_floor_tiles": checked,
        "minimum_boundary_clearance": min(entry[1] for entry in selected),
        "rooms": sorted(set(entry[2] for entry in selected)),
    }
    return positions, metadata


def mio0_decompress(rom, offset):
    if rom[offset : offset + 4] != b"MIO0":
        raise ValueError("SM64 common1 MIO0 header is missing")
    output_size, compressed_offset, raw_offset = struct.unpack_from(
        ">III", rom, offset + 4
    )
    command_position = offset + 16
    compressed_position = offset + compressed_offset
    raw_position = offset + raw_offset
    output = bytearray()
    command = 0
    command_bits = 0

    while len(output) < output_size:
        if command_bits == 0:
            if command_position >= len(rom):
                raise ValueError("SM64 MIO0 command stream is truncated")
            command = rom[command_position]
            command_position += 1
            command_bits = 8

        literal = command & 0x80
        command = (command << 1) & 0xFF
        command_bits -= 1

        if literal:
            if raw_position >= len(rom):
                raise ValueError("SM64 MIO0 raw stream is truncated")
            output.append(rom[raw_position])
            raw_position += 1
            continue

        if compressed_position + 2 > len(rom):
            raise ValueError("SM64 MIO0 back-reference stream is truncated")
        first = rom[compressed_position]
        second = rom[compressed_position + 1]
        compressed_position += 2
        length = (first >> 4) + 3
        distance = (((first & 0x0F) << 8) | second) + 1
        if distance > len(output):
            raise ValueError("SM64 MIO0 contains an invalid back-reference")
        for _ in range(length):
            output.append(output[-distance])
            if len(output) == output_size:
                break

    return bytes(output)


def extract_sm64_coin_frames(mario_rom):
    if hashlib.sha1(mario_rom).hexdigest() != MARIO_SHA1:
        raise ValueError("Expected the original US Super Mario 64 .z64 ROM")

    common1 = mio0_decompress(mario_rom, SM64_COMMON1_MIO0_OFFSET)

    # This is the first yellow-coin vertex from the US game's segment 3. It
    # verifies that the decompressed common1 segment is exactly the expected one
    # before any texture bytes are read.
    expected_vertex = struct.pack(
        ">hhhHhhBBBB",
        -32,
        0,
        0,
        0,
        0,
        1984,
        0xFF,
        0xFF,
        0x00,
        0xFF,
    )
    if (
        common1[
            SM64_COIN_VERTEX_OFFSET : SM64_COIN_VERTEX_OFFSET + len(expected_vertex)
        ]
        != expected_vertex
    ):
        raise ValueError("SM64 common1 coin layout did not match the expected US ROM")

    frames = [
        common1[offset : offset + SM64_COIN_TEXTURE_BYTES]
        for offset in SM64_COIN_TEXTURE_OFFSETS
    ]
    if any(len(frame) != SM64_COIN_TEXTURE_BYTES for frame in frames):
        raise ValueError("SM64 yellow-coin texture data is truncated")
    return frames


def _c_byte_array(data):
    rows = []
    for offset in range(0, len(data), 24):
        rows.append(
            "        "
            + ", ".join(f"0x{value:02x}" for value in data[offset : offset + 24])
        )
    return ",\n".join(rows)


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


def c_source(positions, frames):
    encoded_positions = ",\n".join(
        "    {{%.3ff, %.3ff, %.3ff}, 1}" % point for point in positions
    )
    encoded_frames = ",\n".join(
        "    {\n" + _c_byte_array(frame) + "\n    }" for frame in frames
    )

    template = r'''#ifdef __APPLE__
#include <OpenGL/gl.h>
#else
#include <GL/glew.h>
#endif

#include <math.h>
#include <stdio.h>

#include "../src/libsm64.h"
#include "coins.h"

#define COIN_SOUND 0x38118081
#define COIN_TEXTURE_SIZE 32
#define COIN_FRAME_COUNT 4
#define COIN_WIDTH 64.0f
#define COIN_HEIGHT 64.0f
#define COIN_PICKUP_RADIUS 100.0f
#define COIN_PICKUP_HEIGHT 64.0f

struct MarioGoldenEyeCoin {
    float position[3];
    int active;
};

static struct MarioGoldenEyeCoin gCoins[] = {
__POSITIONS__
};

static const unsigned char gCoinTexturePixels[COIN_FRAME_COUNT][COIN_TEXTURE_SIZE * COIN_TEXTURE_SIZE * 2] = {
__FRAMES__
};

static GLuint gCoinTextures[COIN_FRAME_COUNT] = {0};
static int gCoinTexturesReady = 0;
static int gCollected = 0;
static unsigned int gAnimationTick = 0;

int mario_goldeneye_coins_collected(void) {
    return gCollected;
}

int mario_goldeneye_coins_total(void) {
    return (int)(sizeof(gCoins) / sizeof(gCoins[0]));
}

void mario_goldeneye_coins_tick(int32_t marioId, const float marioPosition[3]) {
    gAnimationTick++;

    for (int i = 0; i < mario_goldeneye_coins_total(); ++i) {
        if (!gCoins[i].active) continue;
        float dx = marioPosition[0] - gCoins[i].position[0];
        float dy = marioPosition[1] - gCoins[i].position[1];
        float dz = marioPosition[2] - gCoins[i].position[2];
        if (dx * dx + dz * dz <= COIN_PICKUP_RADIUS * COIN_PICKUP_RADIUS
            && dy >= 0.0f && dy <= COIN_PICKUP_HEIGHT) {
            gCoins[i].active = 0;
            gCollected++;
            sm64_mario_heal(marioId, 4);
            sm64_play_sound(COIN_SOUND, gCoins[i].position);
            printf("Coin %d/%d\n", gCollected, mario_goldeneye_coins_total());
            fflush(stdout);
        }
    }
}

static void ensure_coin_textures(void) {
    if (gCoinTexturesReady) return;

    glGenTextures(COIN_FRAME_COUNT, gCoinTextures);
    for (int frame = 0; frame < COIN_FRAME_COUNT; ++frame) {
        glBindTexture(GL_TEXTURE_2D, gCoinTextures[frame]);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_LUMINANCE_ALPHA,
            COIN_TEXTURE_SIZE,
            COIN_TEXTURE_SIZE,
            0,
            GL_LUMINANCE_ALPHA,
            GL_UNSIGNED_BYTE,
            gCoinTexturePixels[frame]
        );
    }
    gCoinTexturesReady = 1;
}

static void load_billboard_at(float x, float y, float z) {
    GLfloat matrix[16];
    glTranslatef(x, y, z);
    glGetFloatv(GL_MODELVIEW_MATRIX, matrix);

    // Preserve camera-space translation but remove world rotation/scale so the
    // original SM64 sprite plane faces the camera consistently.
    matrix[0] = 1.0f; matrix[1] = 0.0f; matrix[2] = 0.0f;
    matrix[4] = 0.0f; matrix[5] = 1.0f; matrix[6] = 0.0f;
    matrix[8] = 0.0f; matrix[9] = 0.0f; matrix[10] = 1.0f;
    glLoadMatrixf(matrix);
}

void mario_goldeneye_coins_draw_gl20(void) {
    GLint previousMatrixMode = GL_MODELVIEW;
    glGetIntegerv(GL_MATRIX_MODE, &previousMatrixMode);
    glMatrixMode(GL_MODELVIEW);

    glPushAttrib(
        GL_ENABLE_BIT | GL_CURRENT_BIT | GL_TEXTURE_BIT | GL_COLOR_BUFFER_BIT
    );
    glEnable(GL_TEXTURE_2D);
    glDisable(GL_LIGHTING);
    glDisable(GL_CULL_FACE);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);

    ensure_coin_textures();

    // SM64 uses 8 animation states: each of the four IA16 textures is shown
    // twice (front, tilt-right, side, tilt-left).
    int frame = (int)((gAnimationTick / 2) % COIN_FRAME_COUNT);
    glBindTexture(GL_TEXTURE_2D, gCoinTextures[frame]);
    glColor4ub(255, 255, 0, 255);

    for (int i = 0; i < mario_goldeneye_coins_total(); ++i) {
        if (!gCoins[i].active) continue;

        glPushMatrix();
        load_billboard_at(
            gCoins[i].position[0],
            gCoins[i].position[1],
            gCoins[i].position[2]
        );

        // Original yellow-coin geometry is -32..32 X and 0..64 Y.
        glBegin(GL_QUADS);
        glTexCoord2f(0.0f, 1.0f); glVertex3f(-COIN_WIDTH / 2.0f, 0.0f, 0.0f);
        glTexCoord2f(1.0f, 1.0f); glVertex3f( COIN_WIDTH / 2.0f, 0.0f, 0.0f);
        glTexCoord2f(1.0f, 0.0f); glVertex3f( COIN_WIDTH / 2.0f, COIN_HEIGHT, 0.0f);
        glTexCoord2f(0.0f, 0.0f); glVertex3f(-COIN_WIDTH / 2.0f, COIN_HEIGHT, 0.0f);
        glEnd();

        glPopMatrix();
    }

    glPopAttrib();
    glMatrixMode(previousMatrixMode);
}
'''
    return (
        template.replace("__POSITIONS__", encoded_positions)
        .replace("__FRAMES__", encoded_frames)
    )


def patch_main(source):
    if MARKER in source:
        return source
    include_anchor = '#include "audio.h"'
    tick_anchor = (
        "            sm64_mario_tick( marioId, &marioInputs, "
        "&marioState, &marioGeometry );"
    )
    draw_anchor = (
        "        renderer->draw( &renderState, cameraPos, "
        "&marioState, &marioGeometry );"
    )
    for anchor, description in (
        (include_anchor, "audio include"),
        (tick_anchor, "Mario tick"),
        (draw_anchor, "renderer draw"),
    ):
        if source.count(anchor) != 1:
            raise ValueError(
                f"Could not find unique {description} anchor; no coin patch applied"
            )

    source = source.replace(
        include_anchor,
        include_anchor + '\n#include "coins.h"\n' + MARKER,
        1,
    )
    source = source.replace(
        tick_anchor,
        tick_anchor
        + "\n            mario_goldeneye_coins_tick(marioId, marioState.position);",
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
    object_line = "TEST_OBJS += $(BUILD_DIR)/test/coins.o"
    dependency_line = "$(TEST_FILE): $(BUILD_DIR)/test/coins.o"

    additions = []
    if object_line not in source:
        additions.append(object_line)
    if dependency_line not in source:
        additions.append(dependency_line)
    if not additions:
        return source

    suffix = "" if source.endswith("\n") else "\n"
    marker = (
        ""
        if "# MARIO_GOLDENEYE_COINS_V1" in source
        else "\n# MARIO_GOLDENEYE_COINS_V1\n"
    )
    return source + suffix + marker + "\n".join(additions) + "\n"


def install(root, goldeneye_rom, mario_rom, level):
    main_path = root / "test/main.cpp"
    makefile_path = root / "Makefile"
    if not main_path.is_file() or not makefile_path.is_file():
        raise ValueError("libsm64 prototype checkout was not found")

    goldeneye_bytes = goldeneye_rom.read_bytes()
    mario_bytes = mario_rom.read_bytes()
    frames = extract_sm64_coin_frames(mario_bytes)

    _triangles, _colors, spawn, _room, transform_data = extract(
        goldeneye_bytes, level, include_transform=True
    )
    placement_metadata = {
        "checked_floor_tiles": 0,
        "minimum_boundary_clearance": 0.0,
        "rooms": [],
    }
    if level == "dam":
        tiles = extract_dam_stan(goldeneye_bytes)
        spawn = dam_mission_start(
            transform_data["origin"], transform_data["scale"]
        )
        positions, placement_metadata = choose_coin_positions(
            tiles,
            transform_data["origin"],
            transform_data["scale"],
            spawn,
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
            raise ValueError(
                "coins-backup exists but coin marker is absent; refusing to overwrite"
            )
        backup.mkdir()
        shutil.copy2(main_path, backup / "main.cpp")
        shutil.copy2(makefile_path, backup / "Makefile")

    (root / "test/coins.h").write_text(header_source(), encoding="utf-8")
    (root / "test/coins.c").write_text(
        c_source(positions, frames), encoding="utf-8"
    )
    main_path.write_text(patched_main, encoding="utf-8")
    makefile_path.write_text(patched_make, encoding="utf-8")

    state = {
        "version": 2,
        "level": level,
        "coin_count": len(positions),
        "texture": "SM64 yellow coin IA16, 4 original frames",
        "placement": placement_metadata,
        "main_sha256": hashlib.sha256(main_path.read_bytes()).hexdigest(),
        "makefile_sha256": hashlib.sha256(makefile_path.read_bytes()).hexdigest(),
    }
    backup.mkdir(exist_ok=True)
    (backup / "state.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"Coin feature ready: {len(positions)} collectible coins for {level} "
        "using the original SM64 yellow-coin textures."
    )
    if positions:
        print(
            "Coin collision validation: all pickups are on STAN floor triangles; "
            f"minimum boundary clearance "
            f"{placement_metadata['minimum_boundary_clearance']:.1f} world units; "
            f"rooms {placement_metadata['rooms']}."
        )
        print(
            "Coin pickups use the original SM64 100x64 hitbox dimensions, "
            "healing, animation frames, and coin sound; no custom HUD added."
        )
    print("Coin patch backup:", backup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libsm64", type=Path, required=True)
    parser.add_argument(
        "--rom",
        type=Path,
        required=True,
        help="US GoldenEye ROM used for STAN placement",
    )
    parser.add_argument(
        "--mario-rom",
        type=Path,
        required=True,
        help="US Super Mario 64 ROM used to extract original coin textures",
    )
    parser.add_argument("--level", choices=("dam", "facility"), default="dam")
    args = parser.parse_args()
    install(
        args.libsm64.expanduser().resolve(),
        args.rom.expanduser().resolve(),
        args.mario_rom.expanduser().resolve(),
        args.level,
    )
