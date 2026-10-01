#!/usr/bin/env python3
"""Install one reversible camera update in the existing Facility prototype.

Keeps movement and menus intact. --undo restores camera-specific backups.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

MARKER = "// FACILITY_CAMERA_V1"
HEADER_PATH = "test/facility_camera.h"
BACKUP_PATH = "camera-backup"
FILES = ("test/main.cpp", "test/gl20/gl20_renderer.c", "test/gl33core/gl33core_renderer.c")

HEADER = r'''#pragma once
// FACILITY_CAMERA_V1
#include <math.h>
#include "../src/libsm64.h"

struct FacilityCamera {
    float fraction;
    int initialized;
};

static void facility_camera_target(const float position[3], float target[3])
{
    target[0] = position[0];
    target[1] = position[1] + 100.0f;
    target[2] = position[2];
}

static float facility_camera_dot(const float a[3], const float b[3])
{
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}

static void facility_camera_cross(const float a[3], const float b[3], float out[3])
{
    out[0] = a[1]*b[2] - a[2]*b[1];
    out[1] = a[2]*b[0] - a[0]*b[2];
    out[2] = a[0]*b[1] - a[1]*b[0];
}

// Find the first intersection along a segment. Both triangle windings work.
static float facility_camera_ray(const float origin[3], const float delta[3],
                                const struct SM64Surface *geometry, size_t count)
{
    float nearest = 1.0f;
    for (size_t i=0; i<count; ++i) {
        const struct SM64Surface *surface = geometry+i;
        int outside = 0;
        for (int axis=0; axis<3; ++axis) {
            float lo = (float)surface->vertices[0][axis];
            float hi = lo;
            for (int vertex=1; vertex<3; ++vertex) {
                float value = (float)surface->vertices[vertex][axis];
                lo = fminf(lo, value); hi = fmaxf(hi, value);
            }
            float end = origin[axis] + delta[axis]*nearest;
            if (fmaxf(origin[axis], end)<lo || fminf(origin[axis], end)>hi) {
                outside = 1; break;
            }
        }
        if (outside) continue;
        float edge1[3], edge2[3], relative[3], p[3], q[3];
        for (int axis=0; axis<3; ++axis) {
            edge1[axis] = (float)surface->vertices[1][axis] - surface->vertices[0][axis];
            edge2[axis] = (float)surface->vertices[2][axis] - surface->vertices[0][axis];
            relative[axis] = origin[axis] - surface->vertices[0][axis];
        }
        facility_camera_cross(delta, edge2, p);
        float determinant = facility_camera_dot(edge1, p);
        if (fabsf(determinant)<0.00001f) continue;
        float inverse = 1.0f / determinant;
        float u = facility_camera_dot(relative, p)*inverse;
        if (u<0.0f || u>1.0f) continue;
        facility_camera_cross(relative, edge1, q);
        float v = facility_camera_dot(delta, q)*inverse;
        if (v<0.0f || u+v>1.0f) continue;
        float t = facility_camera_dot(edge2, q)*inverse;
        if (t>0.00001f && t<nearest) nearest = t;
    }
    return nearest;
}

static void facility_camera_update(struct FacilityCamera *camera, const float position[3],
                                   float angle, float dt, float eye[3],
                                   const struct SM64Surface *geometry, size_t count)
{
    float target[3];
    facility_camera_target(position, target);
    float delta[3] = {650.0f*cosf(angle), 100.0f, 650.0f*sinf(angle)};
    // Check the lens edges too, with 20 units of clearance at the near plane.
    float right[3] = {-sinf(angle)*20.0f, 0.0f, cosf(angle)*20.0f};
    float fraction = facility_camera_ray(target, delta, geometry, count);
    for (int side=-1; side<=1; side+=2) {
        float horizontal[3] = {target[0]+side*right[0], target[1], target[2]+side*right[2]};
        float vertical[3] = {target[0], target[1]+side*20.0f, target[2]};
        fraction = fminf(fraction, facility_camera_ray(horizontal, delta, geometry, count));
        fraction = fminf(fraction, facility_camera_ray(vertical, delta, geometry, count));
    }
    if (fraction<1.0f) fraction = fmaxf(0.001f, fraction - 24.0f/657.6473f);
    if (!camera->initialized || fraction<camera->fraction) {
        // Snap inward so interpolation cannot put the camera through a wall.
        camera->fraction = fraction;
        camera->initialized = 1;
    } else {
        // Ease back out when the room opens up; independent of frame rate.
        float blend = 1.0f - expf(-6.0f*fminf(fmaxf(dt, 0.0f), 0.1f));
        camera->fraction += (fraction-camera->fraction)*blend;
    }
    for (int axis=0; axis<3; ++axis) eye[axis] = target[axis] + delta[axis]*camera->fraction;
}
'''

OLD_ORBIT = '''        cameraPos[0] = marioState.position[0] + 300.0f * cosf( cameraRot );
        cameraPos[1] = marioState.position[1] + 180.0f;
        cameraPos[2] = marioState.position[2] + 300.0f * sinf( cameraRot );

        marioInputs.camLookX = marioState.position[0] - cameraPos[0];
        marioInputs.camLookZ = marioState.position[2] - cameraPos[2];'''

NEW_ORBIT = '''        marioInputs.camLookX = -cosf(cameraRot);
        marioInputs.camLookZ = -sinf(cameraRot);'''

OLD_LOOK = 'glm_lookat( (float*)camPos, (float*)marioState->position, (vec3){0,1,0}, view );'
NEW_LOOK = '''vec3 cameraTarget;
\tfacility_camera_target(marioState->position, cameraTarget);
\tglm_lookat( (float*)camPos, cameraTarget, (vec3){0,1,0}, view );'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(source, before, after, name):
    if source.count(before) != 1:
        raise ValueError(f'{name} differs from the expected Facility version. No files changed.')
    return source.replace(before, after, 1)


def update(root, undo=False, check=False):
    backup = root / BACKUP_PATH
    header = root / HEADER_PATH
    if undo:
        manifest_path = backup / 'manifest.json'
        if not manifest_path.is_file():
            raise ValueError('Camera backup not found. No files changed.')
        manifest = json.loads(manifest_path.read_text())
        for name, expected in manifest['patched_sha256'].items():
            current = root / name
            if not current.is_file() or digest(current) != expected:
                raise ValueError(f'{name} changed after this patch. Undo stopped to preserve later changes.')
        for name in FILES:
            shutil.copy2(backup / name, root / name)
        header.unlink()
        shutil.rmtree(backup)
        print('Camera update undone. Rebuild with make test.')
        return

    sources = {name: (root / name).read_text() for name in FILES}
    if MARKER in sources[FILES[0]]:
        print('Camera update is already installed.')
        return
    if backup.exists() or header.exists():
        raise ValueError('A camera backup or header already exists. No files changed.')
    main = sources[FILES[0]]
    if 'Mario in GoldenEye Facility' not in main:
        raise ValueError('Install the Facility prototype first. No files changed.')
    main = replace_once(main, '#include "audio.h"', '#include "audio.h"\n#include "facility_camera.h"\n'+MARKER, FILES[0])
    main = replace_once(main, 'float cameraRot = 0.0f;',
                        'float cameraRot = -1.570796327f;\n    struct FacilityCamera facilityCamera = {};', FILES[0])
    main = replace_once(main, OLD_ORBIT, NEW_ORBIT, FILES[0])
    hook = '        renderer->draw( &renderState, cameraPos, &marioState, &marioGeometry );'
    main = replace_once(main, hook,
                        '        facility_camera_update(&facilityCamera, marioState.position, cameraRot, dt,\n'
                        '                               cameraPos, surfaces, surfaces_count);\n'+hook, FILES[0])
    sources[FILES[0]] = main
    for name in FILES[1:]:
        renderer = sources[name]
        renderer = replace_once(renderer, '#include "../level.h"',
                                '#include "../level.h"\n#include "../facility_camera.h"', name)
        renderer = replace_once(renderer, OLD_LOOK, NEW_LOOK, name)
        # Both original renderer variants accept radians, not degrees.
        if name == FILES[1]:
            old_projection = 'glm_perspective( 0.785398f,'
        else:
            old_projection = 'glm_perspective( 45.0f,'
        renderer = replace_once(renderer, old_projection, 'glm_perspective( 1.047197551f,', name)
        # Remove a read of an uninitialized matrix, overwritten immediately by lookat.
        renderer = replace_once(renderer, '\tglm_translate( view, (float*)camPos );\n', '', name)
        sources[name] = renderer
    if check:
        print('Camera patch is compatible. No files changed.')
        return
    for name in FILES:
        destination = backup / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, destination)
    try:
        header.write_text(HEADER)
        for name, source in sources.items():
            (root / name).write_text(source)
        manifest = {'patched_sha256': {name: digest(root / name) for name in (*FILES, HEADER_PATH)}}
        (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    except Exception:
        for name in FILES:
            shutil.copy2(backup / name, root / name)
        header.unlink(missing_ok=True)
        shutil.rmtree(backup)
        raise
    print('Camera update installed: torso aim, wider view, and wall checks.')
    print('WASD, jump, Shift rotation, and menus are unchanged.')
    print('Backup:', backup)
    print('Rebuild with make test, then run ./run-test.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--libsm64', type=Path, default=Path.home()/'Projects/n64-mashup/libsm64')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--undo', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        update(args.libsm64.expanduser().resolve(), args.undo, args.check)
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))
