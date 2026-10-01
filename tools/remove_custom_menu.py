#!/usr/bin/env python3
"""Remove the withdrawn hand-built menu from a local libsm64 checkout."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil

MARKER = "// FACILITY_MISSION_MENU_V1"
END_MARKER = "// END_FACILITY_MISSION_MENU_V1"


def remove(root: Path) -> None:
    main = root / "test/main.cpp"
    if not main.is_file():
        raise ValueError(f"libsm64 checkout not found: {root}")
    source = main.read_text(encoding="utf-8")
    if MARKER not in source:
        print("Custom Facility menu is not installed.")
        return
    if source.count(MARKER) != 1 or source.count(END_MARKER) != 1:
        raise ValueError("Custom menu markers are ambiguous; no files changed.")
    backup = root / "ui-backup"
    if backup.exists():
        raise ValueError("ui-backup already exists; refusing to overwrite it.")
    backup.mkdir(parents=True)
    shutil.copy2(main, backup / "main.cpp")
    source = re.sub(
        rf"\n{re.escape(MARKER)}.*?{re.escape(END_MARKER)}\n",
        "\n",
        source,
        count=1,
        flags=re.DOTALL,
    )
    source = source.replace("\n    if (!mission_select_menu()) {\n        sm64_global_terminate();\n        context_terminate();\n        free(texture);\n        return 0;\n    }\n", "\n")
    main.write_text(source, encoding="utf-8")
    print("Removed the withdrawn custom Facility menu.")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--libsm64", type=Path, required=True)
    args = parser.parse_args()
    remove(args.libsm64.expanduser().resolve())
