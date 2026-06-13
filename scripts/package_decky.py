#!/usr/bin/env python3
"""Build a sideloadable Decky Loader ZIP for Game Media Sync."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PLUGIN_DIR_NAME = "game-media-sync"
NATIVE_ARTIFACT_SUFFIXES = (".so", ".dylib", ".pyd")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-frontend-build", action="store_true")
    parser.add_argument("--skip-python-deps", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    decky_dir = root / "decky"
    build_root = root / "build" / "decky"
    package_dir = build_root / PLUGIN_DIR_NAME
    zip_path = build_root / f"{PLUGIN_DIR_NAME}-decky.zip"

    if not args.skip_frontend_build:
        _run(["pnpm", "--dir", str(decky_dir), "install", "--frozen-lockfile"], root)
        _run(["pnpm", "--dir", str(decky_dir), "run", "build"], root)

    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    _copy_required_files(root, decky_dir, package_dir)
    _copy_python_package(root, package_dir / "py_modules")

    if not args.skip_python_deps:
        _vendor_python_deps(root, package_dir / "py_modules")
        _strip_native_artifacts(package_dir / "py_modules")
        _verify_python_bundle(root, package_dir)
        _remove_python_caches(package_dir)

    _write_zip(package_dir, zip_path)
    _verify_zip(zip_path)
    print(zip_path)
    return 0


def _copy_required_files(root: Path, decky_dir: Path, package_dir: Path) -> None:
    for name in ("plugin.json", "package.json", "main.py"):
        shutil.copy2(decky_dir / name, package_dir / name)

    shutil.copy2(root / "README.md", package_dir / "README.md")
    shutil.copy2(root / "LICENSE.md", package_dir / "LICENSE.md")
    shutil.copytree(decky_dir / "dist", package_dir / "dist")


def _copy_python_package(root: Path, py_modules: Path) -> None:
    py_modules.mkdir(parents=True, exist_ok=True)
    src_package = root / "src" / "game_media_sync"
    dest_package = py_modules / "game_media_sync"
    if dest_package.exists():
        shutil.rmtree(dest_package)
    shutil.copytree(
        src_package,
        dest_package,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _vendor_python_deps(root: Path, py_modules: Path) -> None:
    uv = shutil.which("uv")
    if uv:
        _run(
            [
                uv,
                "pip",
                "install",
                "--target",
                str(py_modules),
                "-r",
                str(root / "requirements.txt"),
            ],
            root,
        )
        return

    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--target",
            str(py_modules),
            "-r",
            str(root / "requirements.txt"),
        ],
        root,
    )


def _strip_native_artifacts(py_modules: Path) -> None:
    """Remove host-specific extension modules from the sideload bundle.

    Current runtime deps are pure-Python compatible. Some packages, notably
    charset-normalizer, may install optional speedups for the build host; those
    Darwin or local-ABI shared objects are not portable to Steam Deck Linux.
    """
    for path in py_modules.rglob("*"):
        if path.is_file() and path.suffix in NATIVE_ARTIFACT_SUFFIXES:
            path.unlink()


def _verify_python_bundle(root: Path, package_dir: Path) -> None:
    code = f"import sys; sys.path.insert(0, {str(package_dir)!r}); import main"
    _run([sys.executable, "-I", "-S", "-c", code], root)


def _remove_python_caches(root: Path) -> None:
    for path in root.rglob("__pycache__"):
        shutil.rmtree(path)
    for path in root.rglob("*.pyc"):
        path.unlink()


def _write_zip(package_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(package_dir.parent))


def _verify_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    top_level = {name.split("/", 1)[0] for name in names if "/" in name}
    if top_level != {PLUGIN_DIR_NAME}:
        raise RuntimeError(f"ZIP must contain one top-level folder: {top_level}")
    if f"{PLUGIN_DIR_NAME}/plugin.json" not in names:
        raise RuntimeError("ZIP is missing plugin.json")
    if f"{PLUGIN_DIR_NAME}/dist/index.js" not in names:
        raise RuntimeError("ZIP is missing dist/index.js")


def _run(cmd: list[str], cwd: Path) -> None:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
