# Progress

## Confirmed on the user's Mac

- Universal libsm64 builds and runs on Apple Silicon.
- Facility geometry loads and Mario can move using WASD.
- GoldenEye textures have not been added; the temporary surface colors are accepted for now.

## Ready for the next Mac test

- Camera framing, torso target, wider field of view, and wall clearance.
- Automated camera and installer checks pass. An offscreen render confirms the complete Mario model and room geometry are visible.

## UI direction

- Reuse the original Super Mario 64 and GoldenEye UI, including original visual assets and layouts.
- The custom Bond-inspired menu is withdrawn as the proposed direction. It is not included in the current tool set.
- Original mission selection and level completion are separate future changes. No completion trigger exists yet.

## Development approach

- Keep one feature per commit and wait for the Mac test before adding the next feature.
- This repository tracks patch source and instructions. It does not upload the user's local libsm64 checkout automatically.
- Game ROMs and generated game data stay local.
