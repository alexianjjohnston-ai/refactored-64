#!/usr/bin/env python3
"""Install SM64-style coins and three Power Stars into GoldenEye levels.

Dam placements are generated from the original GoldenEye STAN navigation data:
every pickup is on a walkable floor triangle, clear of solid STAN boundaries,
and in the navigation component reachable from the original mission start.
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
from sm64_assets import (
    extract_power_star_asset,
    extract_yellow_coin_frames,
    read_power_star_asset,
    read_yellow_coin_asset,
)

MARKER = "// MARIO_GOLDENEYE_COINS_V1"
BACKUP = "coins-backup"

YELLOW_COUNT = 60
RED_COUNT = 8
BLUE_COUNT = 6
STAR_COUNT = 3

MIN_BOUNDARY_CLEARANCE = 140.0
MIN_SPAWN_DISTANCE = 260.0
YELLOW_SEPARATION = 250.0
RED_SEPARATION = 900.0
BLUE_SEPARATION = 900.0
STAR_SEPARATION = 900.0
STAR_FLOOR_HEIGHT = 70.0


def transform(point, origin, scale):
    return tuple(round((point[axis] - origin[axis]) * scale) for axis in range(3))


def _distance(a, b):
    return math.sqrt(sum((a[axis] - b[axis]) ** 2 for axis in range(3)))


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


def _tile_candidate(tile, origin, scale):
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


def _reachable_offsets(tiles, start_offset):
    tile_by_offset = {tile["offset"]: tile for tile in tiles}
    adjacency = {offset: set() for offset in tile_by_offset}

    for tile in tiles:
        base = tile["link_base"]
        for point in tile["points"]:
            link = point[3]
            if (link >> 4) == 0:
                continue
            target = base + (link << 3)
            if target not in tile_by_offset:
                raise ValueError(
                    f"STAN link from {tile['offset']:#x} targets unknown tile {target:#x}"
                )
            adjacency[tile["offset"]].add(target)
            adjacency[target].add(tile["offset"])

    seen = {start_offset}
    stack = [start_offset]
    while stack:
        current = stack.pop()
        for target in adjacency[current]:
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


def safe_candidates(tiles, origin, scale, spawn):
    candidates = []
    for tile in tiles:
        if tile.get("special", 0) != 0:
            continue
        candidate = _tile_candidate(tile, origin, scale)
        if candidate is None:
            continue
        point, clearance = candidate
        if clearance < MIN_BOUNDARY_CLEARANCE:
            continue
        candidates.append(
            {
                "point": point,
                "clearance": clearance,
                "room": tile["room"],
                "offset": tile["offset"],
                "spawn_distance": _distance(point, spawn),
            }
        )

    if not candidates:
        raise ValueError("No collision-safe STAN collectible positions were found")

    start = min(candidates, key=lambda item: item["spawn_distance"])
    reachable = _reachable_offsets(tiles, start["offset"])
    candidates = [
        candidate
        for candidate in candidates
        if candidate["offset"] in reachable
    ]
    return candidates, len(reachable)


def _points(items):
    return [item["point"] if isinstance(item, dict) else item for item in items]


def _remaining(candidates, used):
    used_points = {tuple(item["point"]) for item in used if isinstance(item, dict)}
    return [
        item for item in candidates
        if tuple(item["point"]) not in used_points
    ]


def select_distributed(candidates, count, reserved=(), min_separation=250.0, first="far"):
    if count == 0:
        return []

    reserved_points = _points(reserved)
    eligible = [
        candidate
        for candidate in candidates
        if all(_distance(candidate["point"], point) >= min_separation
               for point in reserved_points)
    ]
    if not eligible:
        raise ValueError("No collectible placement survives separation rules")

    if first == "near":
        first_item = min(eligible, key=lambda item: item["spawn_distance"])
    else:
        first_item = max(eligible, key=lambda item: item["spawn_distance"])

    selected = [first_item]
    remaining = [item for item in eligible if item is not first_item]

    while len(selected) < count:
        existing = reserved_points + [item["point"] for item in selected]
        eligible = [
            item
            for item in remaining
            if all(_distance(item["point"], point) >= min_separation
                   for point in existing)
        ]
        if not eligible:
            raise ValueError(
                f"Only found {len(selected)} of {count} separated collectible positions"
            )
        chosen = max(
            eligible,
            key=lambda item: (
                min(_distance(item["point"], point) for point in existing),
                item["spawn_distance"],
            ),
        )
        selected.append(chosen)
        remaining.remove(chosen)

    return selected


def choose_collectibles(
    tiles,
    origin,
    scale,
    spawn,
    yellow_count=YELLOW_COUNT,
    red_count=RED_COUNT,
    blue_count=BLUE_COUNT,
):
    candidates, reachable_tiles = safe_candidates(tiles, origin, scale, spawn)
    usable = [
        item for item in candidates
        if item["spawn_distance"] >= MIN_SPAWN_DISTANCE
    ]
    if len(usable) < yellow_count + red_count + blue_count + 2:
        raise ValueError("Not enough reachable STAN positions for collectibles")

    red_star_marker = min(usable, key=lambda item: item["spawn_distance"])
    exploration_star = max(usable, key=lambda item: item["spawn_distance"])
    used = [red_star_marker, exploration_star]

    red = select_distributed(
        _remaining(usable, used),
        red_count,
        used,
        RED_SEPARATION,
        first="far",
    )
    used += red
    blue = select_distributed(
        _remaining(usable, used),
        blue_count,
        used,
        BLUE_SEPARATION,
        first="far",
    )
    used += blue
    yellow = select_distributed(
        _remaining(usable, used),
        yellow_count,
        used,
        YELLOW_SEPARATION,
        first="near",
    )

    def raised(item):
        point = list(item["point"])
        point[1] += STAR_FLOOR_HEIGHT
        return tuple(point)

    all_pickups = yellow + red + blue
    metadata = {
        "safe_candidates": len(candidates),
        "reachable_stan_tiles": reachable_tiles,
        "minimum_boundary_clearance": min(
            item["clearance"] for item in all_pickups + used[:2]
        ),
        "yellow_rooms": sorted({item["room"] for item in yellow}),
        "red_rooms": sorted({item["room"] for item in red}),
        "blue_rooms": sorted({item["room"] for item in blue}),
        "max_coin_value": yellow_count + red_count * 2 + blue_count * 5,
    }
    return {
        "yellow": [item["point"] for item in yellow],
        "red": [item["point"] for item in red],
        "blue": [item["point"] for item in blue],
        "red_star": raised(red_star_marker),
        "exploration_star": raised(exploration_star),
    }, metadata


def _c_byte_array(data):
    rows = []
    for offset in range(0, len(data), 24):
        rows.append(
            "        "
            + ", ".join(f"0x{value:02x}" for value in data[offset : offset + 24])
        )
    return ",\n".join(rows)


def _parse_vtx(data):
    vertices = []
    if len(data) % 16:
        raise ValueError("SM64 vertex blob is not 16-byte aligned")
    for offset in range(0, len(data), 16):
        x, y, z, _flag, u, v, r, g, b, a = struct.unpack_from(
            ">hhhHhhBBBB", data, offset
        )
        vertices.append((x, y, z, u, v, r, g, b, a))
    return vertices


def _signed8(value):
    return value - 256 if value >= 128 else value


def _star_vertex_arrays(asset):
    body = []
    for x, y, z, _u, _v, nx, ny, nz, _a in _parse_vtx(asset["body_vertices"]):
        body.append(
            (
                x * 0.25,
                y * 0.25,
                z * 0.25,
                _signed8(nx) / 127.0,
                _signed8(ny) / 127.0,
                _signed8(nz) / 127.0,
            )
        )
    eyes = []
    for x, y, z, u, v, _r, _g, _b, _a in _parse_vtx(asset["eye_vertices"]):
        eyes.append((x * 0.25, y * 0.25, z * 0.25, u / 992.0, v / 992.0))
    return body, eyes


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
int mario_goldeneye_coin_value(void);
int mario_goldeneye_red_coins(void);
int mario_goldeneye_stars(void);
int mario_goldeneye_star_collected(int index);

#ifdef __cplusplus
}
#endif
"""


def c_source(placements, coin_frames, star_asset):
    coin_rows = []
    for coin_type, value, key in (
        ("COIN_YELLOW", 1, "yellow"),
        ("COIN_RED", 2, "red"),
        ("COIN_BLUE", 5, "blue"),
    ):
        for point in placements[key]:
            coin_rows.append(
                "    {{%.3ff, %.3ff, %.3ff}, 1, %s, %d}"
                % (*point, coin_type, value)
            )

    body_vertices, eye_vertices = _star_vertex_arrays(star_asset)
    body_rows = ",\n".join(
        "    {%.3ff, %.3ff, %.3ff, %.6ff, %.6ff, %.6ff}" % vertex
        for vertex in body_vertices
    )
    eye_rows = ",\n".join(
        "    {%.3ff, %.3ff, %.3ff, %.6ff, %.6ff}" % vertex
        for vertex in eye_vertices
    )

    red_star = placements["red_star"]
    exploration = placements["exploration_star"]
    star_rows = (
        "    {{%.3ff, %.3ff, %.3ff}, 0, 0, 0, STAR_RED},\n"
        "    {{0.0f, 0.0f, 0.0f}, 0, 0, 0, STAR_HUNDRED},\n"
        "    {{%.3ff, %.3ff, %.3ff}, 1, 0, 0, STAR_EXPLORATION}"
        % (*red_star, *exploration)
    )

    frame_rows = ",\n".join(
        "    {\n" + _c_byte_array(frame) + "\n    }"
        for frame in coin_frames
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
#define RED_COIN_SOUND_BASE 0x78289081
#define STAR_APPEARS_SOUND 0x3057FF91
#define STAR_COLLECT_SOUND 0x701EFF81

#define COIN_TEXTURE_SIZE 32
#define COIN_FRAME_COUNT 4
#define COIN_WIDTH 64.0f
#define COIN_HEIGHT 64.0f
#define COIN_PICKUP_RADIUS 100.0f
#define COIN_PICKUP_HEIGHT 64.0f
#define STAR_PICKUP_RADIUS 120.0f
#define STAR_PICKUP_HEIGHT 150.0f
#define STAR_COUNT 3

enum CoinType {
    COIN_YELLOW = 0,
    COIN_RED = 1,
    COIN_BLUE = 2
};

enum StarType {
    STAR_RED = 0,
    STAR_HUNDRED = 1,
    STAR_EXPLORATION = 2
};

struct MarioGoldenEyeCoin {
    float position[3];
    int active;
    int type;
    int value;
};

struct MarioGoldenEyeStar {
    float position[3];
    int active;
    int collected;
    int delay;
    int type;
};

struct StarBodyVertex {
    float x, y, z;
    float nx, ny, nz;
};

struct StarEyeVertex {
    float x, y, z;
    float u, v;
};

static struct MarioGoldenEyeCoin gCoins[] = {
__COINS__
};

static struct MarioGoldenEyeStar gStars[STAR_COUNT] = {
__STARS__
};

static const unsigned char gCoinTexturePixels[COIN_FRAME_COUNT][COIN_TEXTURE_SIZE * COIN_TEXTURE_SIZE * 2] = {
__COIN_FRAMES__
};

static const unsigned char gStarSurfacePixels[32 * 32 * 4] = {
__STAR_SURFACE__
};

static const unsigned char gStarEyePixels[32 * 32 * 4] = {
__STAR_EYES__
};

static const struct StarBodyVertex gStarBodyVertices[12] = {
__STAR_BODY__
};

static const struct StarEyeVertex gStarEyeVertices[10] = {
__STAR_EYE_VERTICES__
};

static const unsigned char gStarBodyTriangles[][3] = {
    {0,1,2},{0,3,1},{2,1,4},{1,3,4},{5,3,0},{4,3,5},
    {6,7,4},{7,2,4},{8,6,4},{9,4,10},{9,11,4},{4,5,10},
    {11,8,4},{0,2,7},{0,7,6},{0,6,8},{0,8,11},{0,11,9},
    {10,5,0},{10,0,9}
};

static const unsigned char gStarEyeTriangles[][3] = {
    {0,1,2},{0,3,1},{4,5,6},{7,8,9}
};

static GLuint gCoinTextures[COIN_FRAME_COUNT] = {0};
static GLuint gStarSurfaceTexture = 0;
static GLuint gStarEyeTexture = 0;
static int gTexturesReady = 0;
static int gCollectedCoinObjects = 0;
static int gCoinValue = 0;
static int gRedCollected = 0;
static int gStarsCollected = 0;
static int gHundredStarSpawned = 0;
static unsigned int gAnimationTick = 0;

int mario_goldeneye_coins_collected(void) { return gCollectedCoinObjects; }
int mario_goldeneye_coins_total(void) { return (int)(sizeof(gCoins) / sizeof(gCoins[0])); }
int mario_goldeneye_coin_value(void) { return gCoinValue; }
int mario_goldeneye_red_coins(void) { return gRedCollected; }
int mario_goldeneye_stars(void) { return gStarsCollected; }
int mario_goldeneye_star_collected(int index) {
    if (index < 0 || index >= STAR_COUNT) return 0;
    return gStars[index].collected;
}

static const char *star_name(int type) {
    if (type == STAR_RED) return "8 Red Coins";
    if (type == STAR_HUNDRED) return "100 Coins";
    return "Exploration";
}

static void spawn_star(int index, const float position[3], int delay) {
    if (gStars[index].active || gStars[index].collected) return;
    gStars[index].position[0] = position[0];
    gStars[index].position[1] = position[1];
    gStars[index].position[2] = position[2];
    gStars[index].active = 1;
    gStars[index].delay = delay;
    sm64_play_sound(STAR_APPEARS_SOUND, gStars[index].position);
    printf("Power Star appeared: %s\n", star_name(gStars[index].type));
    fflush(stdout);
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
            gCollectedCoinObjects++;
            gCoinValue += gCoins[i].value;
            sm64_mario_heal(marioId, 4 * gCoins[i].value);

            if (gCoins[i].type == COIN_RED) {
                gRedCollected++;
                sm64_play_sound(
                    RED_COIN_SOUND_BASE + ((gRedCollected - 1) << 16),
                    gCoins[i].position
                );
                printf("Red Coin %d/8 - total coin value %d\n", gRedCollected, gCoinValue);
                if (gRedCollected == 8) {
                    spawn_star(STAR_RED, gStars[STAR_RED].position, 20);
                }
            } else {
                sm64_play_sound(COIN_SOUND, gCoins[i].position);
                printf(
                    "%s coin - total coin value %d/100\n",
                    gCoins[i].type == COIN_BLUE ? "Blue" : "Yellow",
                    gCoinValue
                );
            }

            if (gCoinValue >= 100 && !gHundredStarSpawned) {
                float position[3] = {
                    marioPosition[0],
                    marioPosition[1] + 220.0f,
                    marioPosition[2]
                };
                gHundredStarSpawned = 1;
                spawn_star(STAR_HUNDRED, position, 30);
            }
            fflush(stdout);
        }
    }

    for (int i = 0; i < STAR_COUNT; ++i) {
        if (!gStars[i].active) continue;
        if (gStars[i].delay > 0) {
            gStars[i].delay--;
            continue;
        }

        float dx = marioPosition[0] - gStars[i].position[0];
        float dy = marioPosition[1] - gStars[i].position[1];
        float dz = marioPosition[2] - gStars[i].position[2];
        if (dx * dx + dz * dz <= STAR_PICKUP_RADIUS * STAR_PICKUP_RADIUS
            && fabsf(dy) <= STAR_PICKUP_HEIGHT) {
            gStars[i].active = 0;
            gStars[i].collected = 1;
            gStarsCollected++;
            sm64_play_sound(STAR_COLLECT_SOUND, gStars[i].position);
            printf(
                "Power Star %d/3 collected: %s\n",
                gStarsCollected,
                star_name(gStars[i].type)
            );
            fflush(stdout);
        }
    }
}

static void ensure_textures(void) {
    if (gTexturesReady) return;

    glGenTextures(COIN_FRAME_COUNT, gCoinTextures);
    for (int frame = 0; frame < COIN_FRAME_COUNT; ++frame) {
        glBindTexture(GL_TEXTURE_2D, gCoinTextures[frame]);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_LUMINANCE_ALPHA,
            COIN_TEXTURE_SIZE, COIN_TEXTURE_SIZE, 0,
            GL_LUMINANCE_ALPHA, GL_UNSIGNED_BYTE,
            gCoinTexturePixels[frame]
        );
    }

    glGenTextures(1, &gStarSurfaceTexture);
    glBindTexture(GL_TEXTURE_2D, gStarSurfaceTexture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
    glTexImage2D(
        GL_TEXTURE_2D, 0, GL_RGBA, 32, 32, 0,
        GL_RGBA, GL_UNSIGNED_BYTE, gStarSurfacePixels
    );

    glGenTextures(1, &gStarEyeTexture);
    glBindTexture(GL_TEXTURE_2D, gStarEyeTexture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(
        GL_TEXTURE_2D, 0, GL_RGBA, 32, 32, 0,
        GL_RGBA, GL_UNSIGNED_BYTE, gStarEyePixels
    );

    gTexturesReady = 1;
}

static void load_billboard_at(float x, float y, float z) {
    GLfloat matrix[16];
    glTranslatef(x, y, z);
    glGetFloatv(GL_MODELVIEW_MATRIX, matrix);
    matrix[0] = 1.0f; matrix[1] = 0.0f; matrix[2] = 0.0f;
    matrix[4] = 0.0f; matrix[5] = 1.0f; matrix[6] = 0.0f;
    matrix[8] = 0.0f; matrix[9] = 0.0f; matrix[10] = 1.0f;
    glLoadMatrixf(matrix);
}

static void draw_coin(const struct MarioGoldenEyeCoin *coin, int frame) {
    if (coin->type == COIN_RED) glColor4ub(255, 50, 50, 255);
    else if (coin->type == COIN_BLUE) glColor4ub(55, 110, 255, 255);
    else glColor4ub(255, 255, 0, 255);

    glBindTexture(GL_TEXTURE_2D, gCoinTextures[frame]);
    glPushMatrix();
    load_billboard_at(coin->position[0], coin->position[1], coin->position[2]);
    glBegin(GL_QUADS);
    glTexCoord2f(0.0f, 1.0f); glVertex3f(-COIN_WIDTH / 2.0f, 0.0f, 0.0f);
    glTexCoord2f(1.0f, 1.0f); glVertex3f( COIN_WIDTH / 2.0f, 0.0f, 0.0f);
    glTexCoord2f(1.0f, 0.0f); glVertex3f( COIN_WIDTH / 2.0f, COIN_HEIGHT, 0.0f);
    glTexCoord2f(0.0f, 0.0f); glVertex3f(-COIN_WIDTH / 2.0f, COIN_HEIGHT, 0.0f);
    glEnd();
    glPopMatrix();
}

static void draw_star(const struct MarioGoldenEyeStar *star) {
    glPushMatrix();
    glTranslatef(star->position[0], star->position[1], star->position[2]);
    glRotatef((float)(gAnimationTick * 3 % 360), 0.0f, 1.0f, 0.0f);

    glBindTexture(GL_TEXTURE_2D, gStarSurfaceTexture);
    glColor4ub(255, 255, 255, 255);
    glEnable(GL_TEXTURE_GEN_S);
    glEnable(GL_TEXTURE_GEN_T);
    glTexGeni(GL_S, GL_TEXTURE_GEN_MODE, GL_SPHERE_MAP);
    glTexGeni(GL_T, GL_TEXTURE_GEN_MODE, GL_SPHERE_MAP);

    glBegin(GL_TRIANGLES);
    for (unsigned int t = 0; t < sizeof(gStarBodyTriangles) / sizeof(gStarBodyTriangles[0]); ++t) {
        for (int corner = 0; corner < 3; ++corner) {
            const struct StarBodyVertex *vertex =
                &gStarBodyVertices[gStarBodyTriangles[t][corner]];
            glNormal3f(vertex->nx, vertex->ny, vertex->nz);
            glVertex3f(vertex->x, vertex->y, vertex->z);
        }
    }
    glEnd();

    glDisable(GL_TEXTURE_GEN_S);
    glDisable(GL_TEXTURE_GEN_T);

    glBindTexture(GL_TEXTURE_2D, gStarEyeTexture);
    glBegin(GL_TRIANGLES);
    for (unsigned int t = 0; t < sizeof(gStarEyeTriangles) / sizeof(gStarEyeTriangles[0]); ++t) {
        for (int corner = 0; corner < 3; ++corner) {
            const struct StarEyeVertex *vertex =
                &gStarEyeVertices[gStarEyeTriangles[t][corner]];
            glTexCoord2f(vertex->u, vertex->v);
            glVertex3f(vertex->x, vertex->y, vertex->z);
        }
    }
    glEnd();

    glPopMatrix();
}

void mario_goldeneye_coins_draw_gl20(void) {
    GLint previousMatrixMode = GL_MODELVIEW;
    glGetIntegerv(GL_MATRIX_MODE, &previousMatrixMode);
    glMatrixMode(GL_MODELVIEW);

    glPushAttrib(
        GL_ENABLE_BIT | GL_CURRENT_BIT | GL_TEXTURE_BIT |
        GL_COLOR_BUFFER_BIT | GL_LIGHTING_BIT | GL_TRANSFORM_BIT
    );
    glEnable(GL_TEXTURE_2D);
    glDisable(GL_LIGHTING);
    glDisable(GL_CULL_FACE);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);

    ensure_textures();

    int frame = (int)((gAnimationTick / 2) % COIN_FRAME_COUNT);
    for (int i = 0; i < mario_goldeneye_coins_total(); ++i) {
        if (gCoins[i].active) draw_coin(&gCoins[i], frame);
    }

    for (int i = 0; i < STAR_COUNT; ++i) {
        if (gStars[i].active) draw_star(&gStars[i]);
    }

    glPopAttrib();
    glMatrixMode(previousMatrixMode);
}
'''

    return (
        template.replace("__COINS__", ",\n".join(coin_rows))
        .replace("__STARS__", star_rows)
        .replace("__COIN_FRAMES__", frame_rows)
        .replace("__STAR_SURFACE__", _c_byte_array(star_asset["surface_rgba8"]))
        .replace("__STAR_EYES__", _c_byte_array(star_asset["eyes_rgba8"]))
        .replace("__STAR_BODY__", body_rows)
        .replace("__STAR_EYE_VERTICES__", eye_rows)
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
                f"Could not find unique {description} anchor; no collectible patch applied"
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


def install(root, goldeneye_rom, mario_rom, asset_root, level):
    main_path = root / "test/main.cpp"
    makefile_path = root / "Makefile"
    if not main_path.is_file() or not makefile_path.is_file():
        raise ValueError("libsm64 prototype checkout was not found")

    goldeneye_bytes = goldeneye_rom.read_bytes()
    if asset_root is not None:
        coin_frames = read_yellow_coin_asset(asset_root)
        star_asset = read_power_star_asset(asset_root)
    elif mario_rom is not None:
        mario_bytes = mario_rom.read_bytes()
        coin_frames = extract_yellow_coin_frames(mario_bytes)
        star_asset = extract_power_star_asset(mario_bytes)
    else:
        raise ValueError("Provide --asset-root or --mario-rom for SM64 assets")

    _triangles, _colors, spawn, _room, transform_data = extract(
        goldeneye_bytes, level, include_transform=True
    )
    if level != "dam":
        raise ValueError(
            "Three-star collectible placement currently requires a level STAN importer; "
            "Dam is the supported course."
        )

    tiles = extract_dam_stan(goldeneye_bytes)
    spawn = dam_mission_start(transform_data["origin"], transform_data["scale"])
    placements, placement_metadata = choose_collectibles(
        tiles,
        transform_data["origin"],
        transform_data["scale"],
        spawn,
    )

    main_source = main_path.read_text(encoding="utf-8")
    make_source = makefile_path.read_text(encoding="utf-8")
    patched_main = patch_main(main_source)
    patched_make = patch_makefile(make_source)

    backup = root / BACKUP
    first_install = MARKER not in main_source
    if first_install:
        if backup.exists():
            raise ValueError(
                "coins-backup exists but collectible marker is absent; refusing to overwrite"
            )
        backup.mkdir()
        shutil.copy2(main_path, backup / "main.cpp")
        shutil.copy2(makefile_path, backup / "Makefile")

    (root / "test/coins.h").write_text(header_source(), encoding="utf-8")
    (root / "test/coins.c").write_text(
        c_source(placements, coin_frames, star_asset), encoding="utf-8"
    )
    main_path.write_text(patched_main, encoding="utf-8")
    makefile_path.write_text(patched_make, encoding="utf-8")

    state = {
        "version": 3,
        "level": level,
        "yellow_coins": len(placements["yellow"]),
        "red_coins": len(placements["red"]),
        "blue_coins": len(placements["blue"]),
        "stars": STAR_COUNT,
        "star_rules": [
            "8 red coins",
            "100 total coin value",
            "exploration star",
        ],
        "placement": placement_metadata,
        "main_sha256": hashlib.sha256(main_path.read_bytes()).hexdigest(),
        "makefile_sha256": hashlib.sha256(makefile_path.read_bytes()).hexdigest(),
    }
    backup.mkdir(exist_ok=True)
    (backup / "state.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"Mario course collectibles ready: {len(placements['yellow'])} yellow, "
        f"{len(placements['red'])} red, {len(placements['blue'])} blue coins."
    )
    print(
        "Three Power Stars: 8 Red Coins, 100 Coins, and Exploration."
    )
    print(
        "Placement validation: "
        f"{placement_metadata['safe_candidates']} safe candidates, "
        f"{placement_metadata['reachable_stan_tiles']} reachable STAN tiles, "
        f"minimum wall clearance "
        f"{placement_metadata['minimum_boundary_clearance']:.1f}, "
        f"maximum coin value {placement_metadata['max_coin_value']}."
    )
    print("Collectible patch backup:", backup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libsm64", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--mario-rom", type=Path)
    parser.add_argument(
        "--asset-root",
        "--coin-assets",
        dest="asset_root",
        type=Path,
        help="Prepared SM64 asset root",
    )
    parser.add_argument("--level", choices=("dam", "facility"), default="dam")
    args = parser.parse_args()
    install(
        args.libsm64.expanduser().resolve(),
        args.rom.expanduser().resolve(),
        args.mario_rom.expanduser().resolve() if args.mario_rom else None,
        args.asset_root.expanduser().resolve() if args.asset_root else None,
        args.level,
    )
