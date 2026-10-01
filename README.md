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

## Next steps

1. Correct the camera framing and test it on the Mac.
2. Bring in the original GoldenEye mission selection UI.
3. Add a clear level completion condition and its original game presentation.

Each step must be tested separately before the next is added.

## References

- [libsm64](https://github.com/libsm64/libsm64), which supplies Mario movement, animation, and rendering data.
- [goldeneye-pc-port](https://github.com/jkdansereau/goldeneye-pc-port), whose source and tooling informed the Facility background format reader.
