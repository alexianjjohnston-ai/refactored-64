#!/usr/bin/env python3
"""Versioned local data format for Mario/GoldenEye levels.

Only metadata and user-generated geometry are written to the local output
directory. ROMs and extracted game files are never copied into the repository.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
GAME = "goldeneye"
WORLD_SCALE = 3.0


def facility_manifest(triangles, colors, spawn, spawn_room, level="facility", materials=None):
    """Build the portable representation returned by the Facility extractor."""
    return {
        "schema": SCHEMA_VERSION,
        "game": GAME,
        "level": level,
        "source": {
            "kind": "goldeneye-rom",
            "region": "US",
            "rom_stays_local": True,
        },
        "geometry": {
            "coordinate_scale": WORLD_SCALE,
            "triangles": [
                {
                    "vertices": [list(vertex) for vertex in triangle],
                    "colors": [list(color) for color in triangle_colors],
                    "material_id": (materials[index] if materials is not None else 0),
                }
                for index, (triangle, triangle_colors) in enumerate(zip(triangles, colors))
            ],
        },
        "spawn": {"position": list(spawn), "room": spawn_room},
        "rooms": {"count": 77, "visibility": "room-table"},
        "interactables": [],
        "actors": [],
        "mission": {
            "id": f"{level}-00",
            "objectives": [],
            "completion": None,
        },
    }


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors = []
    if manifest.get("schema") != SCHEMA_VERSION:
        errors.append(f"schema must be {SCHEMA_VERSION}")
    if manifest.get("game") != GAME:
        errors.append("game must be goldeneye")
    if not isinstance(manifest.get("level"), str) or not manifest["level"]:
        errors.append("level must be a non-empty string")
    geometry = manifest.get("geometry")
    triangles = geometry.get("triangles") if isinstance(geometry, dict) else None
    if not isinstance(triangles, list) or not triangles:
        errors.append("geometry.triangles must be a non-empty list")
    else:
        for index, triangle in enumerate(triangles):
            vertices = triangle.get("vertices") if isinstance(triangle, dict) else None
            if not isinstance(vertices, list) or len(vertices) != 3:
                errors.append(f"triangle {index} must have three vertices")
                continue
            if any(not isinstance(vertex, list) or len(vertex) != 3 for vertex in vertices):
                errors.append(f"triangle {index} vertices must be 3D lists")
            elif any(not isinstance(value, (int, float)) or not math.isfinite(value)
                     for vertex in vertices for value in vertex):
                errors.append(f"triangle {index} contains a non-finite coordinate")
            colors = triangle.get("colors") if isinstance(triangle, dict) else None
            if not isinstance(colors, list) or len(colors) != 3:
                errors.append(f"triangle {index} must have three colors")
            elif any(not isinstance(color, list) or len(color) != 3 for color in colors):
                errors.append(f"triangle {index} colors must be RGB lists")
            elif any(not isinstance(value, (int, float)) or not math.isfinite(value)
                     or value < 0 or value > 1 for color in colors for value in color):
                errors.append(f"triangle {index} colors must be finite values from 0 to 1")
    spawn = manifest.get("spawn")
    if not isinstance(spawn, dict) or not isinstance(spawn.get("position"), list) or len(spawn["position"]) != 3:
        errors.append("spawn.position must be a 3D list")
    elif any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in spawn["position"]):
        errors.append("spawn.position must contain finite numbers")
    rooms = manifest.get("rooms")
    if not isinstance(rooms, dict) or not isinstance(rooms.get("count"), int) or rooms["count"] < 1:
        errors.append("rooms.count must be a positive integer")
    if not isinstance(manifest.get("interactables"), list):
        errors.append("interactables must be a list")
    if not isinstance(manifest.get("actors"), list):
        errors.append("actors must be a list")
    mission = manifest.get("mission")
    if not isinstance(mission, dict) or not isinstance(mission.get("objectives"), list):
        errors.append("mission.objectives must be a list")
    return errors


def write_manifest(manifest: dict[str, Any], destination: Path) -> None:
    errors = validate_manifest(manifest)
    if errors:
        raise ValueError("Invalid level manifest: " + "; ".join(errors))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def read_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_manifest(manifest)
    if errors:
        raise ValueError("Invalid level manifest: " + "; ".join(errors))
    return manifest
