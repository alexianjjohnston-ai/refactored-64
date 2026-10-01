#!/usr/bin/env python3
"""Switch the local libsm64 checkout to a generated GoldenEye level safely."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
FILES = (
    "test/main.cpp",
    "test/level.c",
    "test/level.h",
    "test/gl20/gl20_renderer.c",
    "test/gl33core/gl33core_renderer.c",
    "Makefile",
)


def copy_tree_files(source: Path, destination: Path) -> None:
    for name in FILES:
        source_file = source / name
        if source_file.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target)


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def switch(root: Path, level: str, rom: Path) -> None:
    marker = root / ".mario-goldeneye-level"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == level:
        print(f"Local checkout is already on {level}.")
        return
    base_backup = root / "facility-backup"
    if not base_backup.is_dir():
        raise ValueError("facility-backup is required so the level switch can be reversed safely.")

    archive = root / f"level-switch-backup-{level}"
    if archive.exists():
        raise ValueError(f"{archive.name} already exists; refusing to overwrite it.")
    archive.mkdir()
    copy_tree_files(root, archive / "before")
    shutil.copytree(base_backup, archive / "source-base")
    facility_camera = root / "test/facility_camera.h"
    if facility_camera.exists():
        shutil.move(str(facility_camera), str(archive / "old-facility_camera.h"))
    for name in ("camera-backup", "ui-backup"):
        optional = root / name
        if optional.exists():
            shutil.move(str(optional), str(archive / name))

    copy_tree_files(base_backup, root)
    # install_facility only backs up the files it owns. Restore the original
    # GL33 renderer from the camera backup before applying the camera patch.
    original_gl33 = archive / "camera-backup/test/gl33core/gl33core_renderer.c"
    if original_gl33.is_file():
        target = root / "test/gl33core/gl33core_renderer.c"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original_gl33, target)
    shutil.move(str(base_backup), str(archive / "facility-backup"))
    run(sys.executable, str(TOOLS / "install_facility.py"), "--rom", str(rom), "--level", level,
        "--libsm64", str(root))
    run(sys.executable, str(TOOLS / "fix_camera.py"), "--libsm64", str(root))
    marker.write_text(level + "\n", encoding="utf-8")
    print(f"Switched local libsm64 checkout to {level}.")
    print(f"Rollback archive: {archive}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--libsm64", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--level", choices=("dam", "facility"), default="dam")
    args = parser.parse_args()
    switch(args.libsm64.expanduser().resolve(), args.level, args.rom.expanduser().resolve())
