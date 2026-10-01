#!/usr/bin/env python3
"""Install a safe GoldenEye intro compatibility stub.

The earlier Dam cinematic/barrel pass made the prototype hard to play: Mario was
sometimes off-camera and the overlay looked worse than the rest of the build.
This installer keeps the intro API and main.cpp hooks available, but the default
build starts gameplay immediately with the normal Mario camera. A proper
Mario-as-Bond intro can be rebuilt later once the core game is stable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

MARKER = "// GOLDENEYE_MARIO_INTRO_V1"
BACKUP = "intro-backup"
MAIN = "test/main.cpp"
CAMERA_HEADER = "test/facility_camera.h"
MAKEFILE = "Makefile"


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


def c_source() -> str:
    return r'''#include "goldeneye_intro.h"

void goldeneye_intro_init(void)
{
}

int goldeneye_intro_active(void)
{
    return 0;
}

void goldeneye_intro_handle_skip(int pressed)
{
    (void)pressed;
}

int goldeneye_intro_camera_target(float target[3])
{
    (void)target;
    return 0;
}

void goldeneye_intro_update(
    float dt, const float marioPosition[3],
    float marioFaceAngle, float cameraPosition[3])
{
    (void)dt;
    (void)marioPosition;
    (void)marioFaceAngle;
    (void)cameraPosition;
}
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
            raise ValueError(f"Could not find unique {name} anchor for GoldenEye intro stub")

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
        + "\n        goldeneye_intro_update(dt, marioState.position, marioState.faceAngle, cameraPos);",
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
    marker = "" if "# GOLDENEYE_MARIO_INTRO_V1" in source else "\n# GOLDENEYE_MARIO_INTRO_V1\n"
    return source + suffix + marker + "\n".join(additions) + "\n"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(root: Path, rom: Path, level: str) -> None:
    main_path = root / MAIN
    camera_path = root / CAMERA_HEADER
    makefile_path = root / MAKEFILE
    for path in (main_path, camera_path, makefile_path):
        if not path.is_file():
            raise ValueError(f"Required prototype file is missing: {path}")

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
            shutil.rmtree(backup)
        backup.mkdir()
        shutil.copy2(main_path, backup / "main.cpp")
        shutil.copy2(camera_path, backup / "facility_camera.h")
        shutil.copy2(makefile_path, backup / "Makefile")

    (root / "test/goldeneye_intro.h").write_text(header_source(), encoding="utf-8")
    (root / "test/goldeneye_intro.c").write_text(c_source(), encoding="utf-8")
    main_path.write_text(patched_main, encoding="utf-8")
    camera_path.write_text(patched_camera, encoding="utf-8")
    makefile_path.write_text(patched_make, encoding="utf-8")

    backup.mkdir(exist_ok=True)
    state = {
        "version": 2,
        "level": level,
        "enabled": False,
        "reason": "disabled until a clean Mario-as-Bond intro is rebuilt",
        "source": "compatibility stub",
        "main_sha256": digest(main_path),
        "camera_sha256": digest(camera_path),
        "makefile_sha256": digest(makefile_path),
    }
    (backup / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    print("GoldenEye intro disabled for playable default build; normal Mario camera starts immediately.")
    print("Intro compatibility stub backup:", backup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libsm64", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--level", choices=("dam", "facility"), default="dam")
    args = parser.parse_args()
    install(args.libsm64.expanduser().resolve(), args.rom.expanduser().resolve(), args.level)
