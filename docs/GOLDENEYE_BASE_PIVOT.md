# GoldenEye-base pivot

The earlier prototype direction was backwards: it used libsm64 as the runtime, imported GoldenEye geometry into it, then tried to recreate GoldenEye systems with custom code. That makes almost every feature fake or fragile: guards, weapons, props, intro, music, objectives, UI, doors, collision quirks, and mission scripting all have to be rebuilt.

The correct merge direction is now:

> Run GoldenEye as the base game, then replace/augment Bond's player actor with Mario rendering and Mario-style movement/physics.

## Why this is the right base

GoldenEye already owns the systems we want to keep:

- real Dam/Facility/level setup data
- real guards and AI lists
- real props, doors, objectives, pads, paths, intro cameras, music, and mission scripts
- real weapons, hit detection, ammo, watch UI, pause screens, and Bond HUD
- real texture/material behavior

SM64 should contribute the Mario-controlled character layer:

- Mario model/animation data extracted locally from the user's SM64 ROM or built from a decomp-compatible local checkout
- Mario movement states: walk, run, jump, long jump, crouch, slide, wall collision response
- Mario health/damage reactions adapted to GoldenEye damage sources
- optional stars/coins as mission pickups, only after the base game loop is stable

## What the current libsm64 prototype is now for

The libsm64 prototype should be treated as an asset/collision sandbox only. It is useful for:

- checking GoldenEye map extraction
- checking texture decode quality
- checking Mario movement scale against GoldenEye geometry
- testing SM64 asset extraction from the local ROM

It should not be the main merged game runtime.

## Placeholder systems are no longer default

`setup_local.py` now skips `install_gameplay.py` unless `--debug-gameplay` is passed. The temporary billboard guards, Goombas, fake gun HUD, and fake shooting layer are for testing only and should not be confused with real merged game systems.

## Next implementation path

1. Add a GoldenEye-native workspace target.
   - Use a source-compatible GoldenEye decomp/PC-port style tree as the base.
   - Keep ROM assets local; do not commit ROM-derived binary assets.

2. Build and launch unmodified GoldenEye Dam locally.
   - First goal is the real GoldenEye level with real guards, props, music, UI, and weapons.
   - No Mario changes until the base game boots reliably.

3. Add a Mario player adapter.
   - Replace Bond's rendered body/player representation with Mario asset output.
   - Keep GoldenEye camera, map, guard AI, weapons, objectives, and scripts active.

4. Add Mario movement in Bond's player slot.
   - Translate Mario physics into GoldenEye collision/world units.
   - Keep GoldenEye damage/weapon interactions connected.

5. Only then add optional Mario systems.
   - Stars, coins, and Mario enemies should be added after the GoldenEye base loop is stable.
   - Prefer real SM64 assets/behaviors where possible, not new placeholder drawings.

## Practical rule

When choosing between recreating a system and using an existing game system, use the existing system first. Custom code should adapt between the two games, not replace either game with fake stand-ins.
