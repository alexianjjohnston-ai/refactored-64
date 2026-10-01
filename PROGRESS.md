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

## Data pipeline milestone

- Added a versioned local level-manifest format with geometry, spawn, room,
  actor, interactable, and mission fields.
- Added Facility manifest generation from the user's US GoldenEye ROM.
- Added project validation for the pinned libsm64 revision, ROM presence,
  generated manifests, and required checkout files.
- Added Python round-trip and schema validation tests.
- The manifest/runtime integration and Mac build test are still pending.

## Direction for the next gameplay milestone

- The local setup flow now uses the device's ROM folder and the pinned libsm64
  revision without placing ROMs in the repository.
- The game should progress from the opening GoldenEye mission rather than
  treating the Facility warehouse spawn as the final starting experience.
- The next game-facing feature is the first mission/level entry flow, including
  the Mario painting entrance and its short entry jingle before mission play.
