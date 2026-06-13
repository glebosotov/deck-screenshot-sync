#!/usr/bin/env python3
"""Verify the sideloadable Decky Loader ZIP layout."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

PLUGIN_DIR_NAME = "game-media-sync"
NATIVE_ARTIFACT_SUFFIXES = (".so", ".dylib", ".pyd")
REQUIRED_FILES = {
    f"{PLUGIN_DIR_NAME}/plugin.json",
    f"{PLUGIN_DIR_NAME}/package.json",
    f"{PLUGIN_DIR_NAME}/main.py",
    f"{PLUGIN_DIR_NAME}/dist/index.js",
    f"{PLUGIN_DIR_NAME}/py_modules/game_media_sync/__init__.py",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "zip_path",
        nargs="?",
        default="build/decky/game-media-sync-decky.zip",
        type=Path,
        help="Path to the Decky ZIP to verify.",
    )
    args = parser.parse_args()

    try:
        count = verify_zip(args.zip_path)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"ok: {args.zip_path} ({count} files)")
    return 0


def verify_zip(zip_path: Path) -> int:
    if not zip_path.exists():
        raise RuntimeError(f"ZIP not found: {zip_path}")

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

    top_level = {name.split("/", 1)[0] for name in names if "/" in name}
    if top_level != {PLUGIN_DIR_NAME}:
        raise RuntimeError(f"unexpected top-level entries: {sorted(top_level)}")

    missing = REQUIRED_FILES.difference(names)
    if missing:
        raise RuntimeError(f"missing required files: {sorted(missing)}")

    native_artifacts = [
        name for name in names if name.endswith(NATIVE_ARTIFACT_SUFFIXES)
    ]
    if native_artifacts:
        raise RuntimeError(f"native artifacts found: {native_artifacts[:5]}")

    pycache = [name for name in names if "__pycache__" in name]
    if pycache:
        raise RuntimeError(f"pycache files found: {pycache[:5]}")

    return len(names)


if __name__ == "__main__":
    raise SystemExit(main())
