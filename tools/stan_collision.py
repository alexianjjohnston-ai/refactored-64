#!/usr/bin/env python3
"""Generate libsm64 collision from GoldenEye's original STAN walkable tiles.

STAN and background room geometry are both kept in GoldenEye's stored stage
coordinate space here. The project's canonical 4x transform is applied to both
after extraction, so the physics mesh stays aligned with the rendered level.
"""
from __future__ import annotations

import hashlib
import math
import struct
import zlib

EXPECTED_SHA1 = "abe01e4aeb033b6c0836819f549c791b26cfde83"

# US GoldenEye ROM offset of Tbg_dam_all_p_stanZ's 0x1172 raw-deflate stream.
DAM_STAN_OFFSET = 0x850FB0

# libsm64/Mario world units after the project's 4x conversion.
BOUNDARY_BELOW = 800
BOUNDARY_ABOVE = 1200
SPAWN_CLEARANCE = 60
FALL_MARGIN = 3000

# Dam's first single-player Spawn command in GoldenEye's original intro uses
# pad 33. Its pad position is the canonical mission-start position.
DAM_MISSION_START_RAW = (4719.0, -18.0, 3949.0)


def _area2(points):
    return sum(
        points[i][0] * points[(i + 1) % len(points)][2]
        - points[(i + 1) % len(points)][0] * points[i][2]
        for i in range(len(points))
    )


def _cross2(a, b, c):
    return (b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0])


def _point_in_triangle(point, a, b, c, orientation):
    epsilon = 1e-7
    return (
        _cross2(a, b, point) * orientation >= -epsilon
        and _cross2(b, c, point) * orientation >= -epsilon
        and _cross2(c, a, point) * orientation >= -epsilon
    )


def triangulate_polygon(points):
    """Ear-clip one STAN polygon in X/Z while retaining each point's Y."""
    if len(points) < 3 or abs(_area2(points)) < 1:
        return []
    orientation = 1 if _area2(points) > 0 else -1
    remaining = list(range(len(points)))
    triangles = []
    guard = len(points) * len(points) + 8

    while len(remaining) > 3 and guard > 0:
        guard -= 1
        clipped = False
        for position, current in enumerate(remaining):
            previous = remaining[position - 1]
            following = remaining[(position + 1) % len(remaining)]
            a, b, c = points[previous], points[current], points[following]
            if _cross2(a, b, c) * orientation <= 0:
                continue
            if any(
                _point_in_triangle(points[index], a, b, c, orientation)
                for index in remaining
                if index not in (previous, current, following)
            ):
                continue
            triangles.append((previous, current, following))
            del remaining[position]
            clipped = True
            break

        if clipped:
            continue

        # Release STAN can contain collinear polygon points. Removing one does
        # not change the X/Z footprint and lets ear clipping continue.
        for position, current in enumerate(remaining):
            previous = remaining[position - 1]
            following = remaining[(position + 1) % len(remaining)]
            if _cross2(points[previous], points[current], points[following]) == 0:
                del remaining[position]
                clipped = True
                break
        if not clipped:
            raise ValueError("Could not triangulate GoldenEye STAN polygon")

    if len(remaining) == 3:
        triangles.append(tuple(remaining))
    return triangles


def parse_stan(blob):
    if len(blob) < 40:
        raise ValueError("GoldenEye STAN data is truncated")
    first_tile = struct.unpack_from(">I", blob, 4)[0]
    if first_tile < 8 or first_tile >= len(blob):
        raise ValueError("GoldenEye STAN tile offset is invalid")

    tiles = []
    offset = first_tile
    while offset + 8 <= len(blob):
        if blob[offset : offset + 4] == b"\0\0\0\0":
            break
        room = blob[offset + 3]
        mid = struct.unpack_from(">H", blob, offset + 4)[0]
        tail = struct.unpack_from(">H", blob, offset + 6)[0]
        point_count = (tail >> 12) & 0xF
        if point_count < 3 or point_count > 10:
            raise ValueError(f"Invalid STAN point count {point_count} at {offset:#x}")
        end = offset + 8 + point_count * 8
        if end > len(blob):
            raise ValueError("GoldenEye STAN tile runs past end of file")
        points = [
            struct.unpack_from(">hhhH", blob, offset + 8 + index * 8)
            for index in range(point_count)
        ]
        tiles.append(
            {
                "room": room,
                "special": (mid >> 12) & 0xF,
                "points": points,
                # STAN point links are byte offsets in units of 8 from a
                # virtual base 0x80 bytes before ptr_firstroom. Keeping these
                # offsets lets later systems reproduce GoldenEye reachability.
                "offset": offset,
                "link_base": first_tile - 0x80,
            }
        )
        offset = end

    if not tiles or blob[offset : offset + 8] != b"\0" * 8:
        raise ValueError("GoldenEye STAN terminator is missing")
    if b"unstric\0" not in blob[offset : offset + 32]:
        raise ValueError("GoldenEye STAN footer is missing")
    return tiles


def extract_dam_stan(rom):
    if hashlib.sha1(rom).hexdigest() != EXPECTED_SHA1:
        raise ValueError("Expected the original US GoldenEye .z64 ROM.")
    source = rom[DAM_STAN_OFFSET:]
    if source[:2] != b"\x11\x72":
        raise ValueError("Dam STAN compressed header was not found")
    inflater = zlib.decompressobj(-15)
    blob = inflater.decompress(source[2:])
    if not inflater.eof:
        raise ValueError("Dam STAN stream did not terminate cleanly")
    return parse_stan(blob)


def _transform(point, origin, scale):
    return tuple(round((point[axis] - origin[axis]) * scale) for axis in range(3))


def _point_in_polygon(x, z, points):
    inside = False
    for index, point in enumerate(points):
        following = points[(index + 1) % len(points)]
        x1, z1 = point[0], point[2]
        x2, z2 = following[0], following[2]
        cross = (x - x1) * (z2 - z1) - (z - z1) * (x2 - x1)
        if (
            abs(cross) < 1e-7
            and min(x1, x2) <= x <= max(x1, x2)
            and min(z1, z2) <= z <= max(z1, z2)
        ):
            return True
        if (z1 > z) != (z2 > z):
            hit_x = x1 + (z - z1) * (x2 - x1) / (z2 - z1)
            if x < hit_x:
                inside = not inside
    return inside


def _segment_distance_squared(x, z, a, b):
    dx, dz = b[0] - a[0], b[2] - a[2]
    denominator = dx * dx + dz * dz
    if denominator == 0:
        return (x - a[0]) ** 2 + (z - a[2]) ** 2
    amount = max(0.0, min(1.0, ((x - a[0]) * dx + (z - a[2]) * dz) / denominator))
    nearest_x = a[0] + amount * dx
    nearest_z = a[2] + amount * dz
    return (x - nearest_x) ** 2 + (z - nearest_z) ** 2


def _polygon_distance_squared(x, z, points):
    if _point_in_polygon(x, z, points):
        return 0.0
    return min(
        _segment_distance_squared(x, z, points[index], points[(index + 1) % len(points)])
        for index in range(len(points))
    )


def _triangle_area_xz(a, b, c):
    return abs(_cross2(a, b, c))


def _safe_spawn(tiles, origin, scale, candidate_spawn):
    candidate_raw = tuple(candidate_spawn[axis] / scale + origin[axis] for axis in range(3))
    best = None

    for tile in tiles:
        raw_points = [point[:3] for point in tile["points"]]
        triangles = triangulate_polygon(raw_points)
        if not triangles:
            continue
        distance = _polygon_distance_squared(candidate_raw[0], candidate_raw[2], raw_points)
        if best is None or distance < best[0]:
            best = (distance, tile, raw_points, triangles)

    if best is None:
        raise ValueError("Dam STAN contains no walkable polygons")

    distance, tile, raw_points, triangles = best
    if distance == 0:
        safe_x, safe_z = candidate_raw[0], candidate_raw[2]
        triangle = max(
            triangles,
            key=lambda item: _triangle_area_xz(*(raw_points[index] for index in item)),
        )
        a, b, c = (raw_points[index] for index in triangle)
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        if ny == 0:
            safe_y = sum(point[1] for point in raw_points) / len(raw_points)
        else:
            safe_y = a[1] - (nx * (safe_x - a[0]) + nz * (safe_z - a[2])) / ny
    else:
        # Use the largest ear's centroid: it is guaranteed to lie safely
        # inside this legal STAN polygon rather than on a boundary.
        triangle = max(
            triangles,
            key=lambda item: _triangle_area_xz(*(raw_points[index] for index in item)),
        )
        chosen = [raw_points[index] for index in triangle]
        safe_x = sum(point[0] for point in chosen) / 3.0
        safe_y = sum(point[1] for point in chosen) / 3.0
        safe_z = sum(point[2] for point in chosen) / 3.0

    world = list(_transform((safe_x, safe_y, safe_z), origin, scale))
    world[1] += SPAWN_CLEARANCE
    return tuple(world), tile["room"], math.sqrt(distance)


def build_collision_from_tiles(tiles, origin, scale, candidate_spawn):
    floors = []
    walls = []
    seen_boundaries = set()

    for tile in tiles:
        raw_points = [point[:3] for point in tile["points"]]
        area = _area2(raw_points)
        triangle_indices = triangulate_polygon(raw_points)
        if not triangle_indices:
            # Vertical/zero-area STAN entries include ladder metadata and are
            # not a Mario floor. Ladder behavior can be added separately.
            continue

        points = [_transform(point, origin, scale) for point in raw_points]
        for triangle_indices_one in triangle_indices:
            triangle = [points[index] for index in triangle_indices_one]
            a = [triangle[1][axis] - triangle[0][axis] for axis in range(3)]
            b = [triangle[2][axis] - triangle[0][axis] for axis in range(3)]
            normal_y = a[2] * b[0] - a[0] * b[2]
            if normal_y < 0:
                triangle = [triangle[0], triangle[2], triangle[1]]
            floors.append(triangle)

        for index, point in enumerate(points):
            # In GoldenEye, the point's link belongs to edge i -> i+1.
            # A zero high portion means there is no traversable neighboring
            # STAN tile, so this edge is a physical/navigation boundary.
            if tile["points"][index][3] >> 4:
                continue
            following = points[(index + 1) % len(points)]
            if point[0] == following[0] and point[2] == following[2]:
                continue

            raw_a = raw_points[index]
            raw_b = raw_points[(index + 1) % len(raw_points)]
            key = tuple(sorted((raw_a, raw_b)))
            if key in seen_boundaries:
                continue
            seen_boundaries.add(key)

            bottom = min(point[1], following[1]) - BOUNDARY_BELOW
            top = max(point[1], following[1]) + BOUNDARY_ABOVE
            low_a = (point[0], bottom, point[2])
            low_b = (following[0], bottom, following[2])
            high_a = (point[0], top, point[2])
            high_b = (following[0], top, following[2])

            # Wall normals face into the tile so libsm64 pushes Mario back
            # toward legal walkable space.
            if area < 0:
                walls.extend(([low_a, high_a, high_b], [low_a, high_b, low_b]))
            else:
                walls.extend(([low_a, high_b, high_a], [low_a, low_b, high_b]))

    if not floors:
        raise ValueError("Dam STAN produced no walkable collision floors")

    spawn, spawn_room, snap_distance = _safe_spawn(tiles, origin, scale, candidate_spawn)
    floor_min_y = min(point[1] for triangle in floors for point in triangle)
    metadata = {
        "floor_triangles": len(floors),
        "wall_triangles": len(walls),
        "spawn_room": spawn_room,
        "spawn_snap_distance_raw": snap_distance,
        "floor_min_y": floor_min_y,
        "death_y": floor_min_y - FALL_MARGIN,
    }
    return floors + walls, spawn, metadata


def dam_mission_start(origin, scale):
    """Return GoldenEye Dam's canonical first-player mission start in world units."""
    return _transform(DAM_MISSION_START_RAW, origin, scale)


def build_dam_collision(rom, origin, scale, candidate_spawn):
    tiles = extract_dam_stan(rom)
    # Ignore the old render-mesh-derived candidate for Dam. GoldenEye's intro
    # explicitly starts player 0 at pad 33; snap that authentic start onto the
    # nearest legal STAN floor so Mario begins where the mission actually starts.
    mission_start = dam_mission_start(origin, scale)
    return build_collision_from_tiles(tiles, origin, scale, mission_start)
