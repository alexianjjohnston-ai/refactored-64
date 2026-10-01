# Project instructions

- Make and test one gameplay feature at a time. Keep each addition in its own commit.
- Preserve the existing working Facility prototype and WASD movement.
- Use original Super Mario 64 and GoldenEye layouts, fonts, graphics, and behavior for game UI. Do not introduce custom replacement menus or a merely Bond-inspired design.
- Extract required original assets locally from user-supplied ROMs; keep ROMs, extracted game data, and binaries out of this repository.
- The previously supplied custom mission menu is withdrawn. Do not make it the default or build on its design.
- Every installer must validate the expected source before writing and provide a backup and rollback path.
- Do not claim a Mac runtime test from a Linux build or offscreen render. Report the actual checks and any remaining manual test.
- Save completed source changes to this GitHub repository once it is connected. Do not publish a new feature as tested until the user has checked it on their Mac.

## Layout

This repository contains reproducible patch tools for an upstream libsm64 checkout. The checkout and locally extracted Facility geometry remain on the user's computer.

Known upstream revision: `fd11813208272b4271d92bd92feb8f3fdbe61be5`.
