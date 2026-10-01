# Mario in GoldenEye

A small libsm64 crossover prototype: Mario moves through GoldenEye's Facility geometry. Changes are added one feature at a time so regressions can be isolated.

This repository stores the patch tools and project instructions. It does not contain ROMs, extracted game assets, or compiled binaries. The tools generate the required data locally from the user's US game files.

## Working baseline

The Facility prototype has been tested by the user on an Apple Silicon Mac. WASD movement works. GoldenEye textures, doors, guards, objectives, original menus, and level completion have not been added yet.

Original game UI will be used for the menus and HUD. The earlier custom mission menu prototype is withdrawn.

## Existing Mac checkout

The existing game folder is `~/Projects/n64-mashup/libsm64`. Keep that folder as it is; these tools patch it in place after checking the expected version.

For a fresh checkout, use libsm64 revision `fd11813208272b4271d92bd92feb8f3fdbe61be5`. Build dependencies are SDL2, GLEW, pkg-config, Python 3, and the Xcode command line tools.

```bash
mkdir -p ~/Projects/n64-mashup
cd ~/Projects/n64-mashup
git clone https://github.com/libsm64/libsm64.git
cd libsm64
git checkout fd11813208272b4271d92bd92feb8f3fdbe61be5
brew install sdl2 glew pkg-config
cp "$HOME/Downloads/Super Mario 64 (USA).z64" baserom.us.z64
make lib
install_name_tool -id @executable_path/dist/libsm64.dylib dist/libsm64.dylib
```

From this repository's folder, install the geometry-only Facility prototype:

```bash
python3 tools/install_facility.py --rom "$HOME/Downloads/GoldenEye 007 (USA).z64"
```

Use the actual GoldenEye filename if it differs. The installer checks the US ROM hash and keeps the original source in `facility-backup`.

Compile and run from the game folder:

```bash
cd ~/Projects/n64-mashup/libsm64
export CPATH="$(brew --prefix sdl2)/include:$(brew --prefix glew)/include"
export LIBRARY_PATH="$(brew --prefix sdl2)/lib:$(brew --prefix glew)/lib"
make test && ./run-test
```

Controls: WASD or arrows to move, Space/X to jump, C to punch, Z to crouch, and left/right Shift to rotate the camera.

## Camera update

Close the running game, then run this from the repository folder:

```bash
python3 tools/fix_camera.py
```

The patch starts behind Mario, aims 100 units above his feet, increases the orbit distance from 300 to 650 units, and uses a 60 degree field of view. Camera rays pull it closer when walls or ceilings block the view, then ease it outward as the room opens up. Movement keys and existing menus are unchanged.

Rebuild and run using the commands above. Check that Mario and the room are fully visible, WASD still works, and Shift rotation behaves correctly near a wall. This update is awaiting the user's Mac runtime test.

To restore the preceding camera version, run this from the repository folder and rebuild:

```bash
python3 tools/fix_camera.py --undo
```

Rollback stops if the patched files were edited afterward, so it cannot silently overwrite a later feature. The patch accepts `--check` to validate without writing and `--libsm64 /path/to/libsm64` for another checkout.

The legacy menu installer's `--undo` restores an older copy of `main.cpp`; do not run that rollback after adding the camera patch or other features. The original game UI will be integrated as its own later change.

Validation on Linux: both renderer variants and the updated main loop compile; an offscreen OpenGL 2 compatibility render shows the Facility room and stairs with Mario fully framed; camera tests cover blocked rays, both triangle windings, wall clearance, and easing. Installer checks cover validation before writes, repeat installation, exact rollback, and protection of later edits. This does not replace the Mac play test.

## Next steps

1. Test the camera update on the Mac.
2. Bring in the original GoldenEye mission selection UI.
3. Add a clear level completion condition and its original game presentation.

Each step must be tested separately before the next is added.

## Local level data pipeline

## One-command local setup and run

From this repository, update the project, regenerate the current GoldenEye
level, refresh the local libsm64 checkout, build, and launch with:

```bash
./run
```

The default target is Dam. The launcher keeps ROMs local, uses the canonical
4x GoldenEye world scale, refreshes collision and textures, builds `run-test`,
and starts it. For setup without launching, use `python3 setup_local.py`.

The default target is the first GoldenEye campaign mission, Dam. Use
`--level facility` only when you specifically want the prototype level.

It searches common folders such as `Downloads`, `Desktop/N64`, and
`Documents/N64`. You can also provide a folder explicitly:

```bash
python3 setup_local.py --rom-dir "/Users/alexian/Desktop/N64"
```

Use `--no-build` to prepare files without compiling. The script validates both
US ROM hashes, keeps the ROMs outside Git, uses the pinned libsm64 revision,
and writes generated data under `~/Projects/n64-mashup/generated`.

The first shared data format is a versioned JSON level manifest. It is a
local build output and must not be committed: it contains geometry generated
from the user's ROM, while the ROM itself remains untouched.

### Local asset preparation and cache

`./run` now prepares reusable ROM-derived assets through
`tools/prepare_assets.py`. Generated data stays under
`~/Projects/n64-mashup/generated` and is fingerprinted by the ROM hashes,
relevant extractor code, manifests, and pinned reference revision. Unchanged
GoldenEye textures and shared SM64 assets are reused instead of being decoded
again on every build.

The preparation step also writes `generated/asset-index.json` and a shared
`generated/sm64/` root. Feature installers should consume assets from that
root rather than each implementing their own ROM parser. The first shared
asset is the original four-frame SM64 yellow coin. Stars, HUD glyphs, menu
graphics, particles, and other common assets can be registered in
`tools/sm64_assets.py` as they are added.

To pre-warm both supported GoldenEye levels without patching or building
libsm64:

```bash
python3 tools/prepare_assets.py \
  --goldeneye "$HOME/Downloads/GoldenEye 007 (USA).z64" \
  --mario "$HOME/Downloads/Super Mario 64 (USA).z64" \
  --generated "$HOME/Projects/n64-mashup/generated" \
  --level dam --level facility
```

The setup also removes the withdrawn hand-built Facility menu. Its backup is
kept in the local libsm64 checkout. The original GoldenEye front-end is a
separate local UI-port milestone and is not replaced by a look-alike menu.

Generate and validate the Facility manifest into a local game-data folder:

```bash
mkdir -p "$HOME/Projects/n64-mashup/generated"
python3 tools/generate_level_manifest.py \
  --rom "/path/to/GoldenEye 007 (USA).z64" \
  --out "$HOME/Projects/n64-mashup/generated/facility.json"

python3 tools/validate_project.py \
  --goldeneye "/path/to/GoldenEye 007 (USA).z64" \
  --mario "/path/to/Super Mario 64 (USA).z64" \
  --libsm64 "$HOME/Projects/n64-mashup/libsm64" \
  --manifest "$HOME/Projects/n64-mashup/generated/facility.json"
```

The manifest already has slots for rooms, interactables, actors, and mission
objectives. They are intentionally empty until each gameplay system is added
and tested separately.

Run repository-side checks with:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## References

- [libsm64](https://github.com/libsm64/libsm64), which supplies Mario movement, animation, and rendering data.
- [goldeneye-pc-port](https://github.com/jkdansereau/goldeneye-pc-port), whose source and tooling informed the Facility background format reader.
