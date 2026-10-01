# Merge-first direction

This project should merge the existing Super Mario 64 and GoldenEye 007 systems instead of building long-term replacement artwork, fake UI, or rectangle gameplay.

## Rule going forward

A feature is only considered part of the real mashup when it is sourced from one of these places:

1. The user's local, verified SM64 US ROM.
2. The user's local, verified GoldenEye US ROM.
3. Decompiled/source-compatible behavior used as a reference, then wired into the local build without shipping copyrighted ROM assets.
4. Existing extracted assets under the local generated asset cache.

Temporary debug visuals are allowed only when they prove an input, placement, or collision path. They should be named as debug placeholders and replaced as soon as the real source exists.

## Systems already close to merge-first

- GoldenEye Dam level geometry from the local GoldenEye ROM.
- GoldenEye Dam STAN floor/boundary collision from the local GoldenEye ROM.
- SM64 Mario runtime through libsm64.
- SM64 coins and Power Stars from the local SM64 ROM.
- GoldenEye Bank Gothic font extraction from the local GoldenEye ROM.
- SM64 HUD asset extraction from the local SM64 ROM, although the rendering path still needs cleanup.

## Systems that are currently too placeholder-heavy

- Guards are colored billboards instead of GoldenEye guard models/animations.
- Goombas are colored billboards instead of SM64 actor/object code and model assets.
- PP7 is a simple debug fire action instead of GoldenEye weapon model, animation, HUD, and sound.
- The previous Bond barrel/intro attempt was fake-looking and is disabled by default.
- Some UI rendering is custom OpenGL glue instead of faithful SM64/GoldenEye display behavior.

## Next merge-first milestones

### 1. Replace debug enemies with source-derived actors

- Extract GoldenEye setup actor placements for Dam instead of choosing random STAN points.
- Keep actor metadata such as type, room, pad, rotation, and flags where available.
- Use extracted model/texture data or a referenced decoded asset path before drawing guards permanently.
- Only keep billboard guards behind a debug flag.

### 2. Replace fake PP7 with GoldenEye weapon assets

- Locate PP7 first-person model/sprite/texture data from the local GoldenEye ROM or decoded reference output.
- Add a local extractor/cache entry for the weapon assets.
- Wire fire input to a visible PP7 overlay/model.
- Add real audio only after the GoldenEye sound bank path is understood; do not guess SM64 sound IDs.

### 3. Replace fake Mario enemies with SM64 actor content

- Pull Goomba model/texture data from the SM64 ROM or source-compatible extracted asset path.
- Port a minimal SM64 Goomba behavior loop instead of hand-made rectangle enemies.
- Keep collision interaction through libsm64 attack/damage APIs where possible.

### 4. Rebuild intro only from real GoldenEye intro pieces

- Keep intro disabled until it can be faithful.
- Use GoldenEye's real intro camera data and barrel art/audio when extracted correctly.
- Do not ship a fake barrel overlay as the default intro.

### 5. Clean UI by source family

- SM64 gameplay HUD should use original SM64 glyphs, coin/star icons, and layout.
- GoldenEye menus/watch/objectives should use original GoldenEye font and layout data.
- Do not mix custom debug UI into the normal play path.

## Commit policy

Prefer small commits that each replace one placeholder with one source-derived system. Avoid large random commits that make it harder to tell what broke.
