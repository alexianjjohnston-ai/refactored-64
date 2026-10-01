#!/usr/bin/env python3
"""Extract GoldenEye's original Bank Gothic UI font from a US ROM."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

GOLDENEYE_SHA1 = "abe01e4aeb033b6c0836819f549c791b26cfde83"
BANK_KERNING_ROM_OFFSET = 0x2E63F0
BANK_KERNING_BYTES = 676
BANK_CHARTABLE_ROM_OFFSET = 0x2E6694
BANK_CHARTABLE_BYTES = 8716
BANK_GLYPH_COUNT = 94
BANK_KERNING_COUNT = 13 * 13
BANK_FONT_ASSET = Path("ui") / "bank-gothic"


def _signed32(value: int) -> int:
    return value - 0x100000000 if value & 0x80000000 else value


def extract_bank_gothic_blob(rom: bytes) -> bytes:
    if hashlib.sha1(rom).hexdigest() != GOLDENEYE_SHA1:
        raise ValueError("Expected the original US GoldenEye .z64 ROM")
    kerning = rom[
        BANK_KERNING_ROM_OFFSET : BANK_KERNING_ROM_OFFSET + BANK_KERNING_BYTES
    ]
    table = rom[
        BANK_CHARTABLE_ROM_OFFSET : BANK_CHARTABLE_ROM_OFFSET + BANK_CHARTABLE_BYTES
    ]
    if len(kerning) != BANK_KERNING_BYTES or len(table) != BANK_CHARTABLE_BYTES:
        raise ValueError("GoldenEye Bank Gothic resource is truncated")
    blob = kerning + table
    parse_bank_gothic_blob(blob)
    return blob


def parse_bank_gothic_blob(blob: bytes) -> dict:
    expected_size = BANK_KERNING_BYTES + BANK_CHARTABLE_BYTES
    if len(blob) != expected_size:
        raise ValueError(
            f"Bank Gothic blob has wrong size: {len(blob)} != {expected_size}"
        )

    kerning = list(struct.unpack_from(">169i", blob, 0))
    glyphs = []
    record_base = BANK_KERNING_BYTES
    for slot in range(BANK_GLYPH_COUNT):
        values = struct.unpack_from(">6I", blob, record_base + slot * 24)
        index, baseline, height, width, kerning_index, pixel_offset = values
        baseline = _signed32(baseline)
        height = _signed32(height)
        width = _signed32(width)
        kerning_index = _signed32(kerning_index)
        if width <= 0 or height <= 0:
            raise ValueError(f"Bank Gothic glyph {slot} has invalid dimensions")
        if not 0 <= kerning_index < 13:
            raise ValueError(f"Bank Gothic glyph {slot} has invalid kerning index")
        padded_width = (width + 7) & ~7
        pixel_bytes = padded_width * height
        if pixel_offset < record_base + BANK_GLYPH_COUNT * 24:
            raise ValueError(f"Bank Gothic glyph {slot} pixel pointer is invalid")
        if pixel_offset + pixel_bytes > len(blob):
            raise ValueError(f"Bank Gothic glyph {slot} pixels leave font blob")
        glyphs.append(
            {
                "slot": slot,
                "ascii": slot + 0x21,
                "index": index,
                "baseline": baseline,
                "height": height,
                "width": width,
                "padded_width": padded_width,
                "kerning_index": kerning_index,
                "pixel_offset": pixel_offset,
                "pixel_bytes": pixel_bytes,
                "pixels": blob[pixel_offset : pixel_offset + pixel_bytes],
            }
        )

    return {"kerning": kerning, "glyphs": glyphs}


def write_bank_gothic_asset(rom: bytes, root: Path) -> list[Path]:
    directory = Path(root).expanduser().resolve() / BANK_FONT_ASSET
    directory.mkdir(parents=True, exist_ok=True)
    blob = extract_bank_gothic_blob(rom)
    parsed = parse_bank_gothic_blob(blob)

    font_path = directory / "font.bin"
    metadata_path = directory / "font.json"
    font_path.write_bytes(blob)
    metadata_path.write_text(
        json.dumps(
            {
                "source": "GoldenEye 007 (USA) Bank Gothic",
                "format": "I8",
                "ascii_first": 0x21,
                "ascii_last": 0x7E,
                "space_width": 5,
                "glyph_count": len(parsed["glyphs"]),
                "kerning_entries": len(parsed["kerning"]),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return [font_path, metadata_path]


def read_bank_gothic_asset(root: Path) -> dict:
    directory = Path(root).expanduser().resolve() / BANK_FONT_ASSET
    blob = (directory / "font.bin").read_bytes()
    return parse_bank_gothic_blob(blob)
