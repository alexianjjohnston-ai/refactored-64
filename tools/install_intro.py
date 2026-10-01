#!/usr/bin/env python3
"""Install GoldenEye's original Dam intro camera sequence with Mario as Bond."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from goldeneye_intro import project_dam_intro
from install_facility import extract

MARKER = "// GOLDENEYE_MARIO_INTRO_V1"
BACKUP = "intro-backup"
MAIN = "test/main.cpp"
CAMERA_HEADER = "test/facility_camera.h"
MAKEFILE = "Makefile"

FIXED_SECONDS = 8.0


def _fmt(value: float) -> str:
    return f"{value:.6f}f"


def header_source() -> str:
    return r'''#pragma once

#ifdef __cplusplus
extern "C" {
#endif

void goldeneye_intro_init(void);
int goldeneye_intro_active(void);
void goldeneye_intro_handle_skip(int pressed);
void goldeneye_intro_update(float dt, const float marioPosition[3],
                            float marioFaceAngle, float cameraPosition[3]);
int goldeneye_intro_camera_target(float target[3]);

#ifdef __cplusplus
}
#endif
'''


def c_source(data: dict) -> str:
    cameras = ",\n".join(
        "    {{ {%s, %s, %s}, %s, %s }}"
        % (
            _fmt(camera["position"][0]),
            _fmt(camera["position"][1]),
            _fmt(camera["position"][2]),
            _fmt(camera["yaw"]),
            _fmt(camera["pitch"]),
        )
        for camera in data["cameras"]
    )
    swirls = ",\n".join(
        "    {{ %du, {%s, %s, %s}, %s, %s }}"
        % (
            swirl["flags"],
            _fmt(swirl["offset"][0]),
            _fmt(swirl["offset"][1]),
            _fmt(swirl["offset"][2]),
            _fmt(swirl["tangent_scale"]),
            _fmt(swirl["duration_frames"]),
        )
        for swirl in data["swirls"]
    )
    return f'''#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>

#include "goldeneye_intro.h"

#define GE_INTRO_FIXED_SECONDS {_fmt(FIXED_SECONDS)}
#define GE_INTRO_FRAME_RATE 60.0f
#define GE_INTRO_LOOK_HEIGHT 100.0f
#define GE_INTRO_FORWARD_LOOK {_fmt(40.0 * 4.0 / 0.23363999)}

enum GoldenEyeIntroPhase {{
    GE_INTRO_FIXED = 0,
    GE_INTRO_SWIRL = 1,
    GE_INTRO_DONE = 2
}};

struct GoldenEyeFixedCamera {{
    float position[3];
    float yaw;
    float pitch;
}};

struct GoldenEyeSwirlPoint {{
    uint32_t flags;
    float offset[3];
    float tangentScale;
    float durationFrames;
}};

static const struct GoldenEyeFixedCamera gFixedCameras[] = {{
{cameras}
}};

static const struct GoldenEyeSwirlPoint gSwirl[] = {{
{swirls}
}};

static int gPhase = GE_INTRO_FIXED;
static float gTimer = 0.0f;
static int gFixedCamera = 0;
static int gSwirlIndex = 1;
static int gSkip = 0;
static int gTargetOverride = 0;
static float gCameraTarget[3] = {{0.0f, 0.0f, 0.0f}};

static void cubic_spline(
    const float prev[3], const float start[3], const float end[3],
    const float next[3], float fraction, float tangentScale, float result[3])
{{
    float square = fraction * fraction;
    float cube = square * fraction;
    float m0 = ((2.0f * square) - (fraction + cube)) * tangentScale;
    float m1 = (((2.0f - tangentScale) * cube)
              + (square * (tangentScale - 3.0f))) + 1.0f;
    float m2 = (((tangentScale - 2.0f) * cube)
              + (square * (3.0f - (2.0f * tangentScale))))
              + (fraction * tangentScale);
    float m3 = (cube - square) * tangentScale;
    for (int axis = 0; axis < 3; ++axis) {{
        result[axis] =
            m0 * prev[axis] + m1 * start[axis]
            + m2 * end[axis] + m3 * next[axis];
    }}
}}

static int clamp_swirl_index(int index)
{{
    int count = (int)(sizeof(gSwirl) / sizeof(gSwirl[0]));
    if (index < 0) return 0;
    if (index >= count) return count - 1;
    return index;
}}

static int resolve_swirl_point(int segment, int relative)
{{
    int base = clamp_swirl_index(segment);
    int target = clamp_swirl_index(segment + relative);
    int entry = base;

    if (relative < 0) {{
        return target;
    }}

    while (entry < target) {{
        int next = clamp_swirl_index(entry + 1);
        if (gSwirl[next].flags & 1u) break;
        entry++;
    }}
    return entry;
}}

static void swirl_point_world(
    int index, float faceAngle, float point[3])
{{
    const struct GoldenEyeSwirlPoint *entry = &gSwirl[clamp_swirl_index(index)];
    if (entry->flags & 2u) {{
        float thetaX = sinf(faceAngle);
        float thetaZ = cosf(faceAngle);
        point[0] = entry->offset[2] * thetaX + entry->offset[0] * thetaZ;
        point[1] = entry->offset[1];
        point[2] = entry->offset[2] * thetaZ - entry->offset[0] * thetaX;
    }} else {{
        point[0] = entry->offset[0];
        point[1] = entry->offset[1];
        point[2] = entry->offset[2];
    }}
}}

static void finish_intro(void)
{{
    gPhase = GE_INTRO_DONE;
    gTargetOverride = 0;
}}

void goldeneye_intro_init(void)
{{
    unsigned int seed = (unsigned int)time(NULL);
    gPhase = GE_INTRO_FIXED;
    gTimer = 0.0f;
    gSwirlIndex = 1;
    gSkip = 0;
    gTargetOverride = 0;
    gFixedCamera = (int)(seed % (sizeof(gFixedCameras) / sizeof(gFixedCameras[0])));
}}

int goldeneye_intro_active(void)
{{
    return gPhase != GE_INTRO_DONE;
}}

void goldeneye_intro_handle_skip(int pressed)
{{
    if (pressed) gSkip = 1;
}}

int goldeneye_intro_camera_target(float target[3])
{{
    if (!gTargetOverride) return 0;
    target[0] = gCameraTarget[0];
    target[1] = gCameraTarget[1];
    target[2] = gCameraTarget[2];
    return 1;
}}

void goldeneye_intro_update(
    float dt, const float marioPosition[3],
    float marioFaceAngle, float cameraPosition[3])
{{
    if (gPhase == GE_INTRO_DONE) {{
        gTargetOverride = 0;
        return;
    }}

    if (gSkip) {{
        finish_intro();
        return;
    }}

    gTargetOverride = 1;

    if (gPhase == GE_INTRO_FIXED) {{
        const struct GoldenEyeFixedCamera *camera = &gFixedCameras[gFixedCamera];
        cameraPosition[0] = camera->position[0];
        cameraPosition[1] = camera->position[1];
        cameraPosition[2] = camera->position[2];

        float cp = cosf(camera->pitch);
        gCameraTarget[0] = cameraPosition[0] + cp * sinf(camera->yaw) * 1200.0f;
        gCameraTarget[1] = cameraPosition[1] + sinf(camera->pitch) * 1200.0f;
        gCameraTarget[2] = cameraPosition[2] - cp * cosf(camera->yaw) * 1200.0f;

        gTimer += dt;
        if (gTimer >= GE_INTRO_FIXED_SECONDS) {{
            gPhase = GE_INTRO_SWIRL;
            gTimer = 0.0f;
            gSwirlIndex = 1;
        }}
        return;
    }}

    float frameDelta = dt * GE_INTRO_FRAME_RATE;
    gTimer += frameDelta;

    int count = (int)(sizeof(gSwirl) / sizeof(gSwirl[0]));
    while (gSwirlIndex < count - 3
           && gSwirl[gSwirlIndex].durationFrames <= gTimer) {{
        if (!(gSwirl[gSwirlIndex + 3].flags & 1u)) {{
            gTimer -= gSwirl[gSwirlIndex].durationFrames;
            gSwirlIndex++;
        }} else {{
            gTimer = gSwirl[gSwirlIndex].durationFrames;
            break;
        }}
    }}

    float duration = gSwirl[gSwirlIndex].durationFrames;
    float fraction = duration > 0.0f ? gTimer / duration : 0.0f;
    if (fraction < 0.0f) fraction = 0.0f;
    if (fraction > 1.0f) fraction = 1.0f;

    float control[4][3];
    for (int relative = -1; relative < 3; ++relative) {{
        int resolved = resolve_swirl_point(gSwirlIndex, relative);
        swirl_point_world(resolved, marioFaceAngle, control[relative + 1]);
    }}

    float localCamera[3];
    cubic_spline(
        control[0], control[1], control[2], control[3],
        fraction, gSwirl[gSwirlIndex].tangentScale, localCamera
    );

    float playerCenter[3] = {{
        marioPosition[0],
        marioPosition[1] + GE_INTRO_LOOK_HEIGHT,
        marioPosition[2]
    }};

    cameraPosition[0] = playerCenter[0] + localCamera[0];
    cameraPosition[1] = playerCenter[1] + localCamera[1];
    cameraPosition[2] = playerCenter[2] + localCamera[2];

    float lookBlend;
    if (!(gSwirl[gSwirlIndex].flags & 4u)) {{
        lookBlend = (gSwirl[gSwirlIndex + 1].flags & 4u)
            ? 1.0f - fraction : 1.0f;
    }} else {{
        lookBlend = (gSwirl[gSwirlIndex + 1].flags & 4u)
            ? 0.0f : fraction;
    }}

    gCameraTarget[0] = playerCenter[0]
        + sinf(marioFaceAngle) * GE_INTRO_FORWARD_LOOK * lookBlend;
    gCameraTarget[1] = playerCenter[1];
    gCameraTarget[2] = playerCenter[2]
        + cosf(marioFaceAngle) * GE_INTRO_FORWARD_LOOK * lookBlend;

    if (gSwirlIndex >= count - 4
        && (gSwirl[gSwirlIndex + 3].flags & 1u)
        && gTimer >= duration) {{
        finish_intro();
    }}
}}
'''


def patch_main(source: str) -> str:
    if MARKER in source:
        return source

    include_anchor = '#include "facility_camera.h"'
    camera_anchor = "struct FacilityCamera facilityCamera = {};"
    input_anchor = "        marioInputs.stickY = y_axis;"
    update_anchor = (
        "        facility_camera_update(&facilityCamera, marioState.position, cameraRot, dt,\n"
        "                               cameraPos, surfaces, surfaces_count);"
    )

    for anchor, name in (
        (include_anchor, "camera include"),
        (camera_anchor, "camera state"),
        (input_anchor, "input assignment"),
        (update_anchor, "camera update"),
    ):
        if source.count(anchor) != 1:
            raise ValueError(f"Could not find unique {name} anchor for GoldenEye intro")

    source = source.replace(
        include_anchor,
        include_anchor + '\n#include "goldeneye_intro.h"\n' + MARKER,
        1,
    )
    source = source.replace(
        camera_anchor,
        camera_anchor + "\n    goldeneye_intro_init();",
        1,
    )
    source = source.replace(
        input_anchor,
        input_anchor
        + "\n\n        goldeneye_intro_handle_skip("
        + "marioInputs.buttonA || marioInputs.buttonB || marioInputs.buttonZ);"
        + "\n        if (goldeneye_intro_active()) {"
        + "\n            marioInputs.stickX = 0.0f;"
        + "\n            marioInputs.stickY = 0.0f;"
        + "\n            marioInputs.buttonA = 0;"
        + "\n            marioInputs.buttonB = 0;"
        + "\n            marioInputs.buttonZ = 0;"
        + "\n        }",
        1,
    )
    source = source.replace(
        update_anchor,
        update_anchor
        + "\n        goldeneye_intro_update("
        + "dt, marioState.position, marioState.faceAngle, cameraPos);",
        1,
    )
    return source


def patch_camera_header(source: str) -> str:
    marker = "// GOLDENEYE_INTRO_TARGET_OVERRIDE_V1"
    if marker in source:
        return source

    include_anchor = '#include "../src/libsm64.h"'
    function_anchor = (
        "static void facility_camera_target(const float position[3], float target[3])\n"
        "{\n"
    )
    if source.count(include_anchor) != 1 or source.count(function_anchor) != 1:
        raise ValueError("facility_camera.h differs from expected camera patch")

    declaration = r'''
// GOLDENEYE_INTRO_TARGET_OVERRIDE_V1
#ifdef __cplusplus
extern "C" {
#endif
int goldeneye_intro_camera_target(float target[3]);
#ifdef __cplusplus
}
#endif
'''
    source = source.replace(include_anchor, include_anchor + declaration, 1)
    source = source.replace(
        function_anchor,
        function_anchor
        + "    if (goldeneye_intro_camera_target(target)) return;\n",
        1,
    )
    return source


def patch_makefile(source: str) -> str:
    object_line = "TEST_OBJS += $(BUILD_DIR)/test/goldeneye_intro.o"
    dependency_line = "$(TEST_FILE): $(BUILD_DIR)/test/goldeneye_intro.o"
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
        if "# GOLDENEYE_MARIO_INTRO_V1" in source
        else "\n# GOLDENEYE_MARIO_INTRO_V1\n"
    )
    return source + suffix + marker + "\n".join(additions) + "\n"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(root: Path, rom: Path, level: str) -> None:
    if level != "dam":
        print(f"GoldenEye intro: no intro importer installed for {level}; leaving gameplay unchanged.")
        return

    main_path = root / MAIN
    camera_path = root / CAMERA_HEADER
    makefile_path = root / MAKEFILE
    for path in (main_path, camera_path, makefile_path):
        if not path.is_file():
            raise ValueError(f"Required prototype file is missing: {path}")

    rom_bytes = rom.read_bytes()
    _tris, _colors, _spawn, _room, transform = extract(
        rom_bytes, level, include_transform=True
    )
    intro = project_dam_intro(
        rom_bytes, transform["origin"], transform["scale"]
    )

    main_source = main_path.read_text(encoding="utf-8")
    camera_source = camera_path.read_text(encoding="utf-8")
    make_source = makefile_path.read_text(encoding="utf-8")

    patched_main = patch_main(main_source)
    patched_camera = patch_camera_header(camera_source)
    patched_make = patch_makefile(make_source)

    backup = root / BACKUP
    first_install = MARKER not in main_source
    if first_install:
        if backup.exists():
            raise ValueError(
                "intro-backup exists but intro marker is absent; refusing to overwrite"
            )
        backup.mkdir()
        shutil.copy2(main_path, backup / "main.cpp")
        shutil.copy2(camera_path, backup / "facility_camera.h")
        shutil.copy2(makefile_path, backup / "Makefile")

    (root / "test/goldeneye_intro.h").write_text(
        header_source(), encoding="utf-8"
    )
    (root / "test/goldeneye_intro.c").write_text(
        c_source(intro), encoding="utf-8"
    )
    main_path.write_text(patched_main, encoding="utf-8")
    camera_path.write_text(patched_camera, encoding="utf-8")
    makefile_path.write_text(patched_make, encoding="utf-8")

    backup.mkdir(exist_ok=True)
    state = {
        "version": 1,
        "level": level,
        "fixed_cameras": len(intro["cameras"]),
        "swirl_points": len(intro["swirls"]),
        "spawn_pad": intro["spawn_pad"],
        "watch_time": intro["watch_time"],
        "source": "local GoldenEye US ROM setup intro",
        "main_sha256": digest(main_path),
        "camera_sha256": digest(camera_path),
        "makefile_sha256": digest(makefile_path),
    }
    (backup / "state.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"GoldenEye Dam intro ready: {len(intro['cameras'])} original fixed cameras, "
        f"{len(intro['swirls'])} original swirl points, Mario at spawn pad {intro['spawn_pad']}."
    )
    print("A/B/Z skips the intro; normal Mario camera takes over afterward.")
    print("Intro patch backup:", backup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libsm64", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--level", choices=("dam", "facility"), default="dam")
    args = parser.parse_args()
    install(
        args.libsm64.expanduser().resolve(),
        args.rom.expanduser().resolve(),
        args.level,
    )
