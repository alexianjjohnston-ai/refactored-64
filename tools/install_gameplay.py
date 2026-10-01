#!/usr/bin/env python3
"""Install the first playable merged gameplay layer: gun, guards, Mario enemies."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil

from install_facility import extract
from install_coins import safe_candidates, select_distributed
from stan_collision import dam_mission_start, extract_dam_stan

MARKER = "// MARIO_GOLDENEYE_GAMEPLAY_V1"
BACKUP = "gameplay-backup"
GOOMBA_COUNT = 5
GUARD_COUNT = 6


def header_source() -> str:
    return r'''#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void mario_goldeneye_gameplay_tick(
    int32_t marioId,
    const float marioPosition[3],
    const float cameraPosition[3],
    int fireDown
);
void mario_goldeneye_gameplay_draw_gl20(void);
int mario_goldeneye_gameplay_ammo(void);
int mario_goldeneye_gameplay_reserve(void);
int mario_goldeneye_gameplay_enemies_left(void);

#ifdef __cplusplus
}
#endif
'''


def _rows(enemies):
    rows = []
    for enemy in enemies:
        x, y, z = enemy["point"]
        rows.append(
            "    {{%.3ff, %.3ff, %.3ff}, %.3ff, %d, 1, %d, 0.0f, 0}"
            % (x, y + enemy["height_offset"], z, y, enemy["type"], enemy["health"])
        )
    return ",\n".join(rows)


def c_source(enemies):
    return r'''#ifdef __APPLE__
#include <OpenGL/gl.h>
#else
#include <GL/glew.h>
#endif

#include <math.h>
#include <stdio.h>

#include "../src/libsm64.h"
#include "mario_goldeneye_gameplay.h"

#define GE_GUN_SOUND 0x700e8081
#define GE_HIT_SOUND 0x500c8081
#define GE_GUARD_DOWN_SOUND 0x7018ff81
#define ENEMY_GOOMBA 0
#define ENEMY_GUARD 1
#define MAX_AMMO 7
#define SHOT_RANGE 4200.0f

struct MashupEnemy {
    float position[3];
    float floorY;
    int type;
    int active;
    int health;
    float phase;
    int hurtCooldown;
};

static struct MashupEnemy gEnemies[] = {
__ENEMIES__
};

static int gAmmo = MAX_AMMO;
static int gReserve = 93;
static int gPrevFire = 0;
static int gShotFlash = 0;
static unsigned int gFrame = 0;

static float distance_xz(const float a[3], const float b[3]) {
    float dx = a[0] - b[0];
    float dz = a[2] - b[2];
    return sqrtf(dx * dx + dz * dz);
}

static float distance3(const float a[3], const float b[3]) {
    float dx = a[0] - b[0];
    float dy = a[1] - b[1];
    float dz = a[2] - b[2];
    return sqrtf(dx * dx + dy * dy + dz * dz);
}

int mario_goldeneye_gameplay_ammo(void) { return gAmmo; }
int mario_goldeneye_gameplay_reserve(void) { return gReserve; }

int mario_goldeneye_gameplay_enemies_left(void) {
    int count = 0;
    for (unsigned int i = 0; i < sizeof(gEnemies) / sizeof(gEnemies[0]); ++i) {
        if (gEnemies[i].active) count++;
    }
    return count;
}

static void reload_if_needed(void) {
    if (gAmmo > 0 || gReserve <= 0) return;
    int amount = gReserve < MAX_AMMO ? gReserve : MAX_AMMO;
    gAmmo = amount;
    gReserve -= amount;
    printf("PP7 reload: %d / %d\n", gAmmo, gReserve);
    fflush(stdout);
}

static int nearest_target(const float marioPosition[3]) {
    int best = -1;
    float bestScore = SHOT_RANGE;
    for (unsigned int i = 0; i < sizeof(gEnemies) / sizeof(gEnemies[0]); ++i) {
        if (!gEnemies[i].active) continue;
        float d = distance3(marioPosition, gEnemies[i].position);
        float vertical = fabsf(marioPosition[1] - gEnemies[i].position[1]);
        if (d < bestScore && vertical < 900.0f) {
            best = (int)i;
            bestScore = d;
        }
    }
    return best;
}

static void fire_pp7(const float marioPosition[3]) {
    reload_if_needed();
    if (gAmmo <= 0) {
        printf("PP7 empty\n");
        fflush(stdout);
        return;
    }
    gAmmo--;
    gShotFlash = 5;
    sm64_play_sound(GE_GUN_SOUND, (float *)marioPosition);

    int target = nearest_target(marioPosition);
    if (target >= 0) {
        struct MashupEnemy *enemy = &gEnemies[target];
        enemy->health--;
        sm64_play_sound(GE_HIT_SOUND, enemy->position);
        if (enemy->health <= 0) {
            enemy->active = 0;
            sm64_play_sound(GE_GUARD_DOWN_SOUND, enemy->position);
            printf("%s down - enemies left %d\n", enemy->type == ENEMY_GUARD ? "Guard" : "Goomba", mario_goldeneye_gameplay_enemies_left());
        } else {
            printf("%s hit - hp %d\n", enemy->type == ENEMY_GUARD ? "Guard" : "Goomba", enemy->health);
        }
    } else {
        printf("PP7 fired - ammo %d / %d\n", gAmmo, gReserve);
    }
    fflush(stdout);
}

void mario_goldeneye_gameplay_tick(
    int32_t marioId,
    const float marioPosition[3],
    const float cameraPosition[3],
    int fireDown
) {
    (void)cameraPosition;
    gFrame++;
    if (gShotFlash > 0) gShotFlash--;

    if (fireDown && !gPrevFire) fire_pp7(marioPosition);
    gPrevFire = fireDown;

    for (unsigned int i = 0; i < sizeof(gEnemies) / sizeof(gEnemies[0]); ++i) {
        struct MashupEnemy *enemy = &gEnemies[i];
        if (!enemy->active) continue;
        enemy->phase += 0.045f + (enemy->type == ENEMY_GUARD ? 0.015f : 0.0f);
        enemy->position[1] = enemy->floorY + (enemy->type == ENEMY_GOOMBA ? 45.0f : 95.0f) + sinf(enemy->phase) * 12.0f;
        if (enemy->hurtCooldown > 0) enemy->hurtCooldown--;

        if (sm64_mario_attack(marioId, enemy->position[0], enemy->position[1], enemy->position[2], enemy->type == ENEMY_GUARD ? 170.0f : 90.0f)) {
            enemy->active = 0;
            sm64_play_sound(GE_GUARD_DOWN_SOUND, enemy->position);
            printf("Mario defeated %s - enemies left %d\n", enemy->type == ENEMY_GUARD ? "guard" : "goomba", mario_goldeneye_gameplay_enemies_left());
            fflush(stdout);
            continue;
        }

        float d = distance_xz(marioPosition, enemy->position);
        if (d < (enemy->type == ENEMY_GUARD ? 210.0f : 155.0f) && enemy->hurtCooldown == 0) {
            enemy->hurtCooldown = 65;
            sm64_mario_take_damage(marioId, enemy->type == ENEMY_GUARD ? 2 : 1, 0, enemy->position[0], enemy->position[1], enemy->position[2]);
            printf("Mario hit by %s\n", enemy->type == ENEMY_GUARD ? "guard" : "goomba");
            fflush(stdout);
        }
    }
}

static void draw_billboard(float x, float y, float z, float w, float h) {
    GLfloat matrix[16];
    glTranslatef(x, y, z);
    glGetFloatv(GL_MODELVIEW_MATRIX, matrix);
    matrix[0] = 1.0f; matrix[1] = 0.0f; matrix[2] = 0.0f;
    matrix[4] = 0.0f; matrix[5] = 1.0f; matrix[6] = 0.0f;
    matrix[8] = 0.0f; matrix[9] = 0.0f; matrix[10] = 1.0f;
    glLoadMatrixf(matrix);
    glBegin(GL_QUADS);
    glVertex3f(-w * 0.5f, 0.0f, 0.0f);
    glVertex3f( w * 0.5f, 0.0f, 0.0f);
    glVertex3f( w * 0.5f, h, 0.0f);
    glVertex3f(-w * 0.5f, h, 0.0f);
    glEnd();
}

static void draw_world_enemies(void) {
    glDisable(GL_TEXTURE_2D);
    for (unsigned int i = 0; i < sizeof(gEnemies) / sizeof(gEnemies[0]); ++i) {
        struct MashupEnemy *enemy = &gEnemies[i];
        if (!enemy->active) continue;
        glPushMatrix();
        if (enemy->type == ENEMY_GUARD) {
            glColor4ub(30, 135, 70, 255);
            draw_billboard(enemy->position[0], enemy->floorY + 35.0f, enemy->position[2], 110.0f, 210.0f);
            glColor4ub(220, 190, 130, 255);
            draw_billboard(enemy->position[0], enemy->floorY + 205.0f, enemy->position[2], 72.0f, 72.0f);
        } else {
            glColor4ub(120, 72, 26, 255);
            draw_billboard(enemy->position[0], enemy->floorY + 15.0f, enemy->position[2], 120.0f, 92.0f);
            glColor4ub(255, 255, 255, 255);
            draw_billboard(enemy->position[0] - 24.0f, enemy->floorY + 70.0f, enemy->position[2], 18.0f, 18.0f);
            draw_billboard(enemy->position[0] + 24.0f, enemy->floorY + 70.0f, enemy->position[2], 18.0f, 18.0f);
        }
        glPopMatrix();
    }
    glEnable(GL_TEXTURE_2D);
}

static void begin_2d(void) {
    GLint viewport[4];
    glGetIntegerv(GL_VIEWPORT, viewport);
    glMatrixMode(GL_PROJECTION);
    glPushMatrix();
    glLoadIdentity();
    glOrtho(0.0, viewport[2], viewport[3], 0.0, -1.0, 1.0);
    glMatrixMode(GL_MODELVIEW);
    glPushMatrix();
    glLoadIdentity();
}

static void end_2d(void) {
    glMatrixMode(GL_MODELVIEW);
    glPopMatrix();
    glMatrixMode(GL_PROJECTION);
    glPopMatrix();
    glMatrixMode(GL_MODELVIEW);
}

static void draw_rect(float x0, float y0, float x1, float y1, unsigned char r, unsigned char g, unsigned char b, unsigned char a) {
    glColor4ub(r, g, b, a);
    glBegin(GL_QUADS);
    glVertex2f(x0, y0); glVertex2f(x1, y0); glVertex2f(x1, y1); glVertex2f(x0, y1);
    glEnd();
}

static void draw_line_rect(float x0, float y0, float x1, float y1, unsigned char r, unsigned char g, unsigned char b, unsigned char a) {
    glColor4ub(r, g, b, a);
    glBegin(GL_LINE_LOOP);
    glVertex2f(x0, y0); glVertex2f(x1, y0); glVertex2f(x1, y1); glVertex2f(x0, y1);
    glEnd();
}

static void draw_gun_hud(void) {
    GLint viewport[4];
    glGetIntegerv(GL_VIEWPORT, viewport);
    float w = (float)viewport[2];
    float h = (float)viewport[3];
    glDisable(GL_TEXTURE_2D);
    draw_rect(w - 172.0f, h - 84.0f, w - 30.0f, h - 28.0f, 0, 0, 0, 150);
    draw_line_rect(w - 172.0f, h - 84.0f, w - 30.0f, h - 28.0f, 0, 255, 0, 180);
    draw_rect(w - 150.0f, h - 62.0f, w - 70.0f, h - 49.0f, 70, 70, 70, 255);
    draw_rect(w - 83.0f, h - 49.0f, w - 55.0f, h - 34.0f, 45, 45, 45, 255);
    if (gShotFlash > 0) draw_rect(w - 58.0f, h - 66.0f, w - 24.0f, h - 44.0f, 255, 210, 70, 220);
    glColor4ub(255, 255, 255, 180);
    glBegin(GL_LINES);
    glVertex2f(w * 0.5f - 10.0f, h * 0.5f); glVertex2f(w * 0.5f + 10.0f, h * 0.5f);
    glVertex2f(w * 0.5f, h * 0.5f - 10.0f); glVertex2f(w * 0.5f, h * 0.5f + 10.0f);
    glEnd();
    glEnable(GL_TEXTURE_2D);
}

void mario_goldeneye_gameplay_draw_gl20(void) {
    GLint previousMatrixMode = GL_MODELVIEW;
    glGetIntegerv(GL_MATRIX_MODE, &previousMatrixMode);
    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glMatrixMode(GL_TEXTURE);
    glPushMatrix();
    glLoadIdentity();
    glMatrixMode(GL_MODELVIEW);

    draw_world_enemies();

    begin_2d();
    draw_gun_hud();
    end_2d();

    glMatrixMode(GL_TEXTURE);
    glPopMatrix();
    glPopAttrib();
    glMatrixMode(previousMatrixMode);
}
'''.replace("__ENEMIES__", _rows(enemies))


def patch_main(source: str) -> str:
    if MARKER in source:
        return source

    if '#include "mario_goldeneye_ui.h"' in source:
        source = source.replace(
            '#include "mario_goldeneye_ui.h"',
            '#include "mario_goldeneye_ui.h"\n#include "mario_goldeneye_gameplay.h"\n' + MARKER,
            1,
        )
    else:
        source = source.replace(
            '#include "goldeneye_intro.h"',
            '#include "goldeneye_intro.h"\n#include "mario_goldeneye_gameplay.h"\n' + MARKER,
            1,
        )

    if "int gameplayFireDown = 0;" not in source:
        source = source.replace(
            "int uiPauseDown = 0, uiLeftDown = 0, uiRightDown = 0;",
            "int uiPauseDown = 0, uiLeftDown = 0, uiRightDown = 0;\n        int gameplayFireDown = 0;",
            1,
        )
    if "gameplayFireDown = state[SDL_SCANCODE_F]" not in source:
        source = source.replace(
            "uiRightDown = state[SDL_SCANCODE_RIGHTBRACKET];",
            "uiRightDown = state[SDL_SCANCODE_RIGHTBRACKET];\n            gameplayFireDown = state[SDL_SCANCODE_F] || state[SDL_SCANCODE_RCTRL];",
            1,
        )
    if "SDL_CONTROLLER_BUTTON_RIGHTSHOULDER" in source and "gameplayFireDown = gameplayFireDown || SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER);" not in source:
        source = source.replace(
            "uiRightDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_RIGHT);",
            "uiRightDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_RIGHT);\n            gameplayFireDown = gameplayFireDown || SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER);",
            1,
        )

    tick_options = [
        "if (!mario_goldeneye_ui_paused()) mario_goldeneye_coins_tick(marioId, marioState.position);",
        "mario_goldeneye_coins_tick(marioId, marioState.position);",
    ]
    for tick in tick_options:
        if tick in source:
            source = source.replace(
                tick,
                tick + "\n            if (!mario_goldeneye_ui_paused()) mario_goldeneye_gameplay_tick(marioId, marioState.position, cameraPos, gameplayFireDown);",
                1,
            )
            break
    else:
        raise ValueError("Could not find coin tick anchor for gameplay")

    draw_options = [
        "mario_goldeneye_ui_draw_gl20(&marioState);",
        "mario_goldeneye_coins_draw_gl20();",
    ]
    for draw in draw_options:
        if draw in source:
            source = source.replace(
                draw,
                draw + "\n        mario_goldeneye_gameplay_draw_gl20();",
                1,
            )
            break
    else:
        raise ValueError("Could not find draw anchor for gameplay")

    return source


def patch_makefile(source: str) -> str:
    object_line = "TEST_OBJS += $(BUILD_DIR)/test/mario_goldeneye_gameplay.o"
    dependency_line = "$(TEST_FILE): $(BUILD_DIR)/test/mario_goldeneye_gameplay.o"
    additions = []
    if object_line not in source:
        additions.append(object_line)
    if dependency_line not in source:
        additions.append(dependency_line)
    if not additions:
        return source
    suffix = "" if source.endswith("\n") else "\n"
    marker = "" if "# MARIO_GOLDENEYE_GAMEPLAY_V1" in source else "\n# MARIO_GOLDENEYE_GAMEPLAY_V1\n"
    return source + suffix + marker + "\n".join(additions) + "\n"


def choose_enemies(goldeneye_bytes: bytes, level: str):
    _triangles, _colors, _spawn, _room, transform_data = extract(
        goldeneye_bytes, level, include_transform=True
    )
    if level != "dam":
        raise ValueError("Gameplay enemy placement currently supports Dam only")
    tiles = extract_dam_stan(goldeneye_bytes)
    spawn = dam_mission_start(transform_data["origin"], transform_data["scale"])
    candidates, reachable = safe_candidates(tiles, transform_data["origin"], transform_data["scale"], spawn)
    usable = [item for item in candidates if item["spawn_distance"] > 1200.0]
    guards = select_distributed(usable, GUARD_COUNT, (), 1600.0, first="far")
    goombas = select_distributed(usable, GOOMBA_COUNT, guards, 1200.0, first="near")
    enemies = []
    for item in goombas:
        enemies.append({"point": item["point"], "type": 0, "health": 1, "height_offset": 45.0})
    for item in guards:
        enemies.append({"point": item["point"], "type": 1, "health": 2, "height_offset": 95.0})
    return enemies, {"safe_candidates": len(candidates), "reachable_stan_tiles": reachable}


def install(root: Path, rom: Path, level: str):
    main_path = root / "test/main.cpp"
    makefile_path = root / "Makefile"
    if not main_path.is_file() or not makefile_path.is_file():
        raise ValueError("libsm64 prototype checkout was not found")

    enemies, metadata = choose_enemies(rom.read_bytes(), level)

    backup = root / BACKUP
    main_source = main_path.read_text(encoding="utf-8")
    first_install = MARKER not in main_source
    if first_install:
        if backup.exists():
            shutil.rmtree(backup)
        backup.mkdir()
        shutil.copy2(main_path, backup / "main.cpp")
        shutil.copy2(makefile_path, backup / "Makefile")

    (root / "test/mario_goldeneye_gameplay.h").write_text(header_source(), encoding="utf-8")
    (root / "test/mario_goldeneye_gameplay.c").write_text(c_source(enemies), encoding="utf-8")
    main_path.write_text(patch_main(main_source), encoding="utf-8")
    makefile_path.write_text(patch_makefile(makefile_path.read_text(encoding="utf-8")), encoding="utf-8")

    state = {
        "version": 2,
        "level": level,
        "goombas": GOOMBA_COUNT,
        "guards": GUARD_COUNT,
        "placement": metadata,
        "controls": {"keyboard_fire": "F or Right Control", "controller_fire": "Right shoulder"},
        "barrel_overlay": False,
    }
    backup.mkdir(exist_ok=True)
    (backup / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"Merged gameplay ready: {GOOMBA_COUNT} Mario enemies, {GUARD_COUNT} Bond guards, PP7-style fire control.")
    print("Fire: F / Right Control / controller right shoulder. Barrel overlay is disabled for playable default build.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libsm64", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--level", choices=("dam", "facility"), default="dam")
    args = parser.parse_args()
    install(args.libsm64.expanduser().resolve(), args.rom.expanduser().resolve(), args.level)
