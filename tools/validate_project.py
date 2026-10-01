#!/usr/bin/env python3
"""Validate local ROMs, manifests, and an upstream libsm64 checkout."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from level_manifest import read_manifest  # noqa: E402

LIBSM64_REVISION = "fd11813208272b4271d92bd92feb8f3fdbe61be5"
GOLDENEYE_SHA1 = "abe01e4aeb033b6c0836819f549c791b26cfde83"
MARIO_SHA1 = None  # libsm64's make process performs the Mario ROM validation.


def git_revision(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def check_hash(path: Path, expected: str) -> bool:
    return path.is_file() and hashlib.sha1(path.read_bytes()).hexdigest() == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--libsm64", type=Path)
    parser.add_argument("--goldeneye", type=Path)
    parser.add_argument("--mario", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    failures = []

    if args.libsm64:
        root = args.libsm64.expanduser().resolve()
        revision = git_revision(root)
        if revision != LIBSM64_REVISION:
            failures.append(f"libsm64 revision is {revision or 'missing'}, expected {LIBSM64_REVISION}")
        for required in ("src/libsm64.h", "test/main.cpp", "Makefile"):
            if not (root / required).is_file():
                failures.append(f"missing libsm64 file: {required}")

    if args.goldeneye:
        rom = args.goldeneye.expanduser().resolve()
        if not check_hash(rom, GOLDENEYE_SHA1):
            failures.append("GoldenEye ROM is missing or is not the expected US image")

    if args.mario:
        mario = args.mario.expanduser().resolve()
        if not mario.is_file():
            failures.append("Mario 64 ROM is missing")

    if args.manifest:
        try:
            manifest = read_manifest(args.manifest.expanduser().resolve())
            print(f"manifest: {manifest['level']} ({len(manifest['geometry']['triangles']):,} triangles)")
        except (OSError, ValueError) as error:
            failures.append(str(error))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("Project validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
