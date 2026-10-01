#!/usr/bin/env python3
"""Set up the Mario/GoldenEye build from ROMs kept on the local device."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
from project_constants import GOLDENEYE_WORLD_SCALE

LIBSM64_REVISION = "fd11813208272b4271d92bd92feb8f3fdbe61be5"
MARIO_SHA1 = "9bef1128717f958171a4afac3ed78ee2bb4e86ce"
GOLDENEYE_SHA1 = "abe01e4aeb033b6c0836819f549c791b26cfde83"


def sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locate(directory: Path, words: tuple[str, ...]) -> Path:
    for candidate in sorted(directory.glob("*.z64")):
        if all(word.lower() in candidate.name.lower() for word in words):
            return candidate
    raise FileNotFoundError(f"Could not find a .z64 ROM containing: {', '.join(words)}")


def find_rom_directory(requested: Path | None) -> Path:
    candidates = []
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
    if not sys.stdin.isatty():
        raise FileNotFoundError("ROM folder not found; rerun with --rom-dir /path/to/your/ROMs")
    directory = Path(input("Enter the folder containing your Mario 64 and GoldenEye .z64 ROMs: ").strip()).expanduser().resolve()
    locate(directory, ("mario",))
    locate(directory, ("goldeneye",))
    return directory


def run(*command: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True, env=env)


def mac_build_environment() -> dict[str, str]:
    env = os.environ.copy()
    try:
        sdl_prefix = subprocess.check_output(("brew", "--prefix", "sdl2"), text=True).strip()
        glew_prefix = subprocess.check_output(("brew", "--prefix", "glew"), text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("Homebrew packages sdl2 and glew are required to build the Mac test app") from error
    env["CPATH"] = f"{sdl_prefix}/include:{glew_prefix}/include"
    env["LIBRARY_PATH"] = f"{sdl_prefix}/lib:{glew_prefix}/lib"
    return env


def ensure_libsm64(path: Path, clone_url: str) -> None:
    if not (path / ".git").is_dir():
        path.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", clone_url, str(path))
    run("git", "-C", str(path), "fetch", "--tags", "origin")
    revision = subprocess.check_output(("git", "-C", str(path), "rev-parse", "HEAD"), text=True).strip()
    if revision != LIBSM64_REVISION:
        run("git", "-C", str(path), "checkout", LIBSM64_REVISION)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom-dir", type=Path)
    parser.add_argument("--libsm64", type=Path, default=Path.home() / "Projects/n64-mashup/libsm64")
    parser.add_argument("--generated", type=Path, default=Path.home() / "Projects/n64-mashup/generated")
    parser.add_argument("--clone-url", default="https://github.com/libsm64/libsm64.git")
    parser.add_argument("--level", choices=("dam", "facility"), default="dam")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--run", action="store_true", help="Launch run-test after a successful build")
    args = parser.parse_args()

    rom_dir = find_rom_directory(args.rom_dir)
    mario = locate(rom_dir, ("mario",))
    goldeneye = locate(rom_dir, ("goldeneye",))
    if sha1(mario) != MARIO_SHA1:
        parser.error(f"Unexpected Mario 64 ROM: {mario}")
    if sha1(goldeneye) != GOLDENEYE_SHA1:
        parser.error(f"Unexpected GoldenEye ROM: {goldeneye}")
    print(f"Using local Mario ROM: {mario}")
    print(f"Using local GoldenEye ROM: {goldeneye}")

    libsm64 = args.libsm64.expanduser().resolve()
    ensure_libsm64(libsm64, args.clone_url)
    target_rom = libsm64 / "baserom.us.z64"
    if target_rom.exists() and target_rom.resolve() != mario:
        target_rom.unlink()
    if not target_rom.exists():
        target_rom.symlink_to(mario)

    generated = args.generated.expanduser().resolve()
    generated.mkdir(parents=True, exist_ok=True)
    run(sys.executable, str(TOOLS / "prepare_assets.py"), "--goldeneye", str(goldeneye), "--mario", str(mario), "--generated", str(generated), "--level", args.level)

    manifest_path = generated / f"{args.level}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_scale = float(manifest["geometry"].get("coordinate_scale"))
    if actual_scale != float(GOLDENEYE_WORLD_SCALE):
        raise RuntimeError(f"Generated level is not using the required {GOLDENEYE_WORLD_SCALE}x GoldenEye world scale")
    coords = [v for tri in manifest["geometry"]["triangles"] for vertex in tri["vertices"] for v in vertex]
    print(f"Verified GoldenEye world scale: {actual_scale}x (coordinate range {min(coords)}..{max(coords)})")

    level_marker = libsm64 / ".mario-goldeneye-level"
    installed_level = level_marker.read_text().strip() if level_marker.is_file() else None
    has_reversible_backup = (libsm64 / "facility-backup").is_dir()
    if installed_level == args.level and has_reversible_backup:
        run(sys.executable, str(TOOLS / "refresh_level.py"), "--rom", str(goldeneye), "--level", args.level, "--libsm64", str(libsm64))
    elif has_reversible_backup:
        if args.level == "dam" and installed_level != "dam":
            run(sys.executable, str(TOOLS / "switch_level.py"), "--rom", str(goldeneye), "--level", args.level, "--libsm64", str(libsm64))
        else:
            run(sys.executable, str(TOOLS / "refresh_level.py"), "--rom", str(goldeneye), "--level", args.level, "--libsm64", str(libsm64))
    else:
        print("No reversible level backup found; installing level from clean libsm64 checkout.")
        run(sys.executable, str(TOOLS / "install_facility.py"), "--rom", str(goldeneye), "--level", args.level, "--libsm64", str(libsm64))

    if (libsm64 / "camera-backup").is_dir():
        print("Camera patch is already installed; preserving its backup.")
    else:
        run(sys.executable, str(TOOLS / "fix_camera.py"), "--libsm64", str(libsm64))

    run(sys.executable, str(TOOLS / "remove_custom_menu.py"), "--libsm64", str(libsm64))
    texture_command = [sys.executable, str(TOOLS / "install_textures.py"), "--libsm64", str(libsm64), "--manifest", str(generated / f"{args.level}.json"), "--decoded", str(generated / f"{args.level}-textures/decoded")]
    if (libsm64 / "texture-backup").is_dir():
        texture_command.append("--update")
    run(*texture_command)

    run(sys.executable, str(TOOLS / "install_coins.py"), "--libsm64", str(libsm64), "--rom", str(goldeneye), "--coin-assets", str(generated / "sm64"), "--level", args.level)
    run(sys.executable, str(TOOLS / "install_intro.py"), "--libsm64", str(libsm64), "--rom", str(goldeneye), "--level", args.level)
    run(sys.executable, str(TOOLS / "install_ui.py"), "--libsm64", str(libsm64), "--sm64-assets", str(generated / "sm64"), "--goldeneye-assets", str(generated / "goldeneye"))
    run(sys.executable, str(TOOLS / "install_gameplay.py"), "--libsm64", str(libsm64), "--rom", str(goldeneye), "--level", args.level)

    if not args.no_build:
        (libsm64 / "run-test").unlink(missing_ok=True)
        run("make", "test", cwd=libsm64, env=mac_build_environment())
        if args.run:
            run("./run-test", cwd=libsm64, env=mac_build_environment())
    elif args.run:
        parser.error("--run cannot be combined with --no-build")
    print("Local setup complete. ROMs remained on the device and were not copied into this repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
