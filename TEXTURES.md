# Local texture implementation status

The Mac OpenGL 2 prototype can now render locally generated RGBA textures.
The extractor retains signed N64 S/T coordinates and maps opcode 0xC0 to
texture IDs. The decoder compiles the reference libpdtex library at revision
`0e8c2ce2135ce56bd09e0c3a0f76a74d2ed6337f` with our RGBA output adapter.
Reference: https://github.com/jkdansereau/goldeneye-pc-port/tree/0e8c2ce2135ce56bd09e0c3a0f76a74d2ed6337f/tools/mktex

Dam extraction currently yields 75 images, each exported as RGBA8 and PNG.
Generated source is installed only in the user's libsm64 checkout. No game
images or generated geometry belong in this repository.

The renderer uses original vertex colors, linear filtering, repeating textures,
and alpha testing. The original renderer and hashes of installed files are
stored in `texture-backup`. Repeat installation preserves that backup.
Rollback refuses to overwrite later edits:

```sh
python3 tools/install_textures.py --libsm64 /path/to/libsm64 --undo
```

Rebuild after installation or rollback. The default Mac renderer builds;
in-game UV scale, material wrap/shift commands, blended transparency ordering,
and reference pixel comparisons still need verification. OpenGL 3 rendering
and separately spawned door/object meshes are not implemented by this patch.
This is an implementation in progress, not full texture-goal acceptance.
