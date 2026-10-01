#!/usr/bin/env python3
"""Read GoldenEye's original stage-intro camera data from the user's US ROM."""
from __future__ import annotations

import hashlib
import struct
import zlib

GOLDENEYE_SHA1 = "abe01e4aeb033b6c0836819f549c791b26cfde83"
DAM_SETUP_OFFSET = 0x8C10D0
DAM_LEVEL_SCALE = 0.23363999

INTRO_SPAWN = 0
INTRO_ITEM = 1
INTRO_AMMO = 2
INTRO_SWIRL = 3
INTRO_ANIM = 4
INTRO_CUFF = 5
INTRO_CAMERA = 6
INTRO_WATCH = 7
INTRO_CREDITS = 8
INTRO_END = 9

RECORD_SIZES = {
    INTRO_SPAWN: 12,
    INTRO_ITEM: 16,
    INTRO_AMMO: 16,
    INTRO_SWIRL: 32,
    INTRO_ANIM: 8,
    INTRO_CUFF: 8,
    INTRO_CAMERA: 40,
    INTRO_WATCH: 12,
    INTRO_CREDITS: 8,
    INTRO_END: 4,
}


def _s32(value: int) -> int:
    return value - 0x100000000 if value & 0x80000000 else value


def decompress_1172(source: bytes) -> bytes:
    if source[:2] != b"\x11\x72":
        raise ValueError("GoldenEye 0x1172 compressed header is missing")
    inflater = zlib.decompressobj(-15)
    blob = inflater.decompress(source[2:])
    if not inflater.eof:
        raise ValueError("GoldenEye compressed setup stream did not terminate")
    return blob


def parse_setup_intro(blob: bytes) -> dict:
    if len(blob) < 40:
        raise ValueError("GoldenEye stage setup is truncated")
    intro_offset = struct.unpack_from(">I", blob, 8)[0]
    if intro_offset < 40 or intro_offset >= len(blob):
        raise ValueError(f"GoldenEye intro offset is invalid: {intro_offset:#x}")

    cameras = []
    swirls = []
    spawns = []
    watch_time = None
    offset = intro_offset
    record_count = 0

    while offset + 4 <= len(blob):
        record_count += 1
        if record_count > 256:
            raise ValueError("GoldenEye intro has too many records")
        kind = struct.unpack_from(">I", blob, offset)[0]
        size = RECORD_SIZES.get(kind)
        if size is None:
            raise ValueError(f"Unknown GoldenEye intro record {kind} at {offset:#x}")
        if offset + size > len(blob):
            raise ValueError("GoldenEye intro record runs past end of setup")

        if kind == INTRO_CAMERA:
            values = struct.unpack_from(">10I", blob, offset)
            cameras.append({
                "coords_cm100": tuple(_s32(value) for value in values[1:4]),
                "yaw_fixed": _s32(values[4]),
                "pitch_fixed": _s32(values[5]),
                "pad": _s32(values[6]),
                "text1": values[7],
                "text2": values[8],
            })
        elif kind == INTRO_SWIRL:
            values = struct.unpack_from(">8I", blob, offset)
            swirls.append({
                "flags": values[1],
                "offset_fixed": tuple(_s32(value) for value in values[2:5]),
                "scale_fixed": _s32(values[5]),
                "duration_fixed": _s32(values[6]),
                "pad": _s32(values[7]),
            })
        elif kind == INTRO_SPAWN:
            _type, pad, demo = struct.unpack_from(">III", blob, offset)
            if demo == 0:
                spawns.append(pad)
        elif kind == INTRO_WATCH:
            _type, hours, minutes = struct.unpack_from(">III", blob, offset)
            watch_time = (hours, minutes)
        elif kind == INTRO_END:
            break

        offset += size
    else:
        raise ValueError("GoldenEye intro terminator was not found")

    if not cameras:
        raise ValueError("GoldenEye intro contains no fixed cameras")
    if len(swirls) < 5:
        raise ValueError("GoldenEye intro contains too few swirl points")
    if not spawns:
        raise ValueError("GoldenEye intro contains no player spawn")

    return {
        "cameras": cameras,
        "swirls": swirls,
        "spawns": spawns,
        "watch_time": watch_time,
        "intro_offset": intro_offset,
    }


def extract_dam_intro(rom: bytes) -> dict:
    if hashlib.sha1(rom).hexdigest() != GOLDENEYE_SHA1:
        raise ValueError("Expected the original US GoldenEye .z64 ROM")
    blob = decompress_1172(rom[DAM_SETUP_OFFSET:])
    intro = parse_setup_intro(blob)
    if intro["spawns"][0] != 33:
        raise ValueError(
            f"Dam intro start changed unexpectedly: pad {intro['spawns'][0]}"
        )
    if len(intro["cameras"]) != 6:
        raise ValueError(
            f"Expected six original Dam fixed cameras, got {len(intro['cameras'])}"
        )
    return intro


def camera_to_project(camera: dict, origin, world_scale: float) -> dict:
    raw = tuple(
        (value / 100.0) * DAM_LEVEL_SCALE
        for value in camera["coords_cm100"]
    )
    position = tuple(
        (raw[axis] - origin[axis]) * world_scale
        for axis in range(3)
    )
    return {
        **camera,
        "position": position,
        "yaw": camera["yaw_fixed"] / 65535.0,
        "pitch": camera["pitch_fixed"] / 65535.0,
    }


def swirl_to_project(swirl: dict, world_scale: float) -> dict:
    # Swirl offsets are already in GoldenEye's runtime (level-scaled) units.
    # Convert runtime delta -> stored background delta -> project's 4x world.
    delta_scale = world_scale / DAM_LEVEL_SCALE
    offsets = tuple(
        (value / 65535.0) * delta_scale
        for value in swirl["offset_fixed"]
    )
    return {
        **swirl,
        "offset": offsets,
        "tangent_scale": swirl["scale_fixed"] / 65535.0,
        "duration_frames": swirl["duration_fixed"] / 65535.0,
    }


def project_dam_intro(rom: bytes, origin, world_scale: float) -> dict:
    intro = extract_dam_intro(rom)
    return {
        "cameras": [
            camera_to_project(camera, origin, world_scale)
            for camera in intro["cameras"]
        ],
        "swirls": [
            swirl_to_project(swirl, world_scale)
            for swirl in intro["swirls"]
        ],
        "spawn_pad": intro["spawns"][0],
        "watch_time": intro["watch_time"],
    }
