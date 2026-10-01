"""Shared project constants for GoldenEye-to-libsm64 conversion."""

# All GoldenEye world-space data uses this conversion factor: level geometry,
# spawn positions, actors, doors, props, pickups, collision volumes, and mission
# triggers. Screen-space UI and texture coordinates are intentionally unscaled.
#
# 8x gives Mario more room in GoldenEye corridors than the earlier 4x prototype.
GOLDENEYE_WORLD_SCALE = 8.0
