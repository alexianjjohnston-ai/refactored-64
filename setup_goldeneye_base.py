#!/usr/bin/env python3
"""Bootstrap the GoldenEye-native base path for the Mario/GoldenEye merge.

This is the replacement direction for the old libsm64 prototype. Instead of
recreating GoldenEye inside Mario, this prepares a real GoldenEye source-port
workspace and records where Mario assets/physics should be adapted into
GoldenEye's player slot.

No ROMs or derived game assets are copied into this repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
GOLDENEYE_SHA1 = "abe01e4aeb033b6c0836819f549c791b26cfde83"
MARIO_SHA1 = "9bef1128717f958171a4afac3ed78ee2bb4e86ce"
DEFAULT_PORT_URL = "https://github.com/jkdansereau/goldeneye-pc-port.git"
DEFAULT_WORK_ROOT = Path.home() / "Projects/n64-mashup"


def sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locate(directory: Path, words: tuple[str, ...]) -> Path:
    for candidate in sorted(directory.glob("*.z64")):
        name = candidate.name.lower()
        if all(word.lower() in name for word in words):
            return candidate
    raise FileNotFoundError(f"Could not find a .z64 ROM containing: {', '.join(words)}")


def find_rom_directory(requested: Path | None) -> Path:
    candidates: list[Path] = []
    if requested:
        candidates.append(requested.expanduser().resolve())
    candidates.extend(Path.home() / p for p in ("Downloads", "Desktop/N64", "Documents/N64", "Games"))
    for directory in candidates:
        if not directory.is_dir():
            continue
        try:
            locate(directory, ("mario",))
            locate(directory, ("goldeneye",))
            print(f"Found ROM folder: {directory}")
            return directory
        except FileNotFoundError:
            pass
    raise FileNotFoundError("ROM folder not found; rerun with --rom-dir /path/to/your/ROMs")


def run(*command: str, cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def ensure_clone(path: Path, clone_url: str) -> None:
    if (path / ".git").is_dir():
        run("git", "-C", str(path), "pull", "--ff-only")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    run("git", "clone", clone_url, str(path))


def replace_symlink(target: Path, source: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_symlink() and target.resolve() == source.resolve():
            return
        target.unlink()
    target.symlink_to(source)


def write_adapter_manifest(generated_dir: Path, port_dir: Path, goldeneye: Path, mario: Path) -> Path:
    generated_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "architecture": "goldeneye-base",
        "goal": "Run GoldenEye as the base game and adapt Mario into Bond's player slot.",
        "goldeneye_port": str(port_dir),
        "goldeneye_rom_symlink": str(port_dir / "data/ge007.ntsc-final.z64"),
        "goldeneye_rom_source": str(goldeneye),
        "mario_rom_source": str(mario),
        "do_not_copy_roms": True,
        "adapter_targets": {
            "keep_from_goldeneye": [
                "mission flow",
                "guards and AI",
                "props and doors",
                "weapons and inventory",
                "HUD/front-end/briefing UI",
                "music and SFX",
                "objectives and scripts",
                "save/progression logic"
            ],
            "bring_from_sm64": [
                "Mario actor model source/extraction",
                "Mario animation data or animation adapter",
                "Mario movement/physics state machine mapped onto GoldenEye player input",
                "Mario collision/body dimensions adapted to GoldenEye's collision expectations"
            ]
        },
        "next_code_steps": [
            "Build/run the GoldenEye PC port on a supported host first.",
            "Identify the GoldenEye player actor/render path and Bond third-person model slot.",
            "Replace only the player visual with a Mario model adapter while leaving GoldenEye simulation unchanged.",
            "Then map Mario-style movement into GoldenEye's player input/state update layer."
        ]
    }
    output = generated_dir / "goldeneye-base-adapter.json"
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return output


def maybe_launch(port_dir: Path, requested: bool) -> None:
    exe = port_dir / "build-pc/ge007.x86_64"
    exe_windows = port_dir / "build-pc/ge007.x86_64.exe"
    if not requested:
        return
    if exe.is_file():
        run(str(exe), cwd=port_dir)
    elif exe_windows.is_file():
        run(str(exe_windows), cwd=port_dir)
    else:
        print("GoldenEye executable not built yet.")
        print("Build it inside the GoldenEye port workspace on a supported host, then rerun with --run.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-dir", type=Path)
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    parser.add_argument("--goldeneye-port-url", default=DEFAULT_PORT_URL)
    parser.add_argument("--goldeneye-port-dir", type=Path)
    parser.add_argument("--generated", type=Path, default=DEFAULT_WORK_ROOT / "generated/goldeneye-base")
    parser.add_argument("--no-clone", action="store_true")
    parser.add_argument("--run", action="store_true", help="Launch a built GoldenEye executable if one already exists")
    args = parser.parse_args()

    rom_dir = find_rom_directory(args.rom_dir)
    goldeneye = locate(rom_dir, ("goldeneye",))
    mario = locate(rom_dir, ("mario",))
    if sha1(goldeneye) != GOLDENEYE_SHA1:
        parser.error(f"Unexpected GoldenEye ROM: {goldeneye}")
    if sha1(mario) != MARIO_SHA1:
        parser.error(f"Unexpected Mario 64 ROM: {mario}")

    work_root = args.work_root.expanduser().resolve()
    port_dir = (args.goldeneye_port_dir or (work_root / "goldeneye-pc-port")).expanduser().resolve()
    if args.no_clone and not (port_dir / ".git").is_dir():
        parser.error(f"--no-clone was set, but no GoldenEye port checkout exists at {port_dir}")
    if not args.no_clone:
        ensure_clone(port_dir, args.goldeneye_port_url)

    rom_link = port_dir / "data/ge007.ntsc-final.z64"
    replace_symlink(rom_link, goldeneye)
    manifest = write_adapter_manifest(args.generated.expanduser().resolve(), port_dir, goldeneye, mario)

    print("GoldenEye-base workspace ready.")
    print(f"GoldenEye port checkout: {port_dir}")
    print(f"GoldenEye ROM linked at: {rom_link}")
    print(f"Mario adapter manifest: {manifest}")
    print("This path keeps GoldenEye as the game and adapts Mario into the player slot.")

    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        print("Note: the current public GoldenEye PC port release is Windows/Linux-focused; macOS/ARM is not a supported build target yet.")
        print("Use a Linux/Windows machine or VM for the runnable GoldenEye-native build, or keep using ./run-libsm64-prototype for the old sandbox.")
    elif system == "linux":
        print("On Linux, build in the GoldenEye port workspace after installing its dependencies, then rerun with --run.")
    else:
        print("Build in the GoldenEye port workspace on its supported host, then rerun with --run.")

    maybe_launch(port_dir, args.run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
