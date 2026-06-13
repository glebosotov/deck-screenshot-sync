from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
package_decky = None


def test_decky_package_declares_frontend_entrypoint() -> None:
    package_json = json.loads((ROOT / "decky" / "package.json").read_text())

    assert package_json["main"] == "dist/index.js"


def test_decky_settings_are_private(tmp_path: Path, monkeypatch) -> None:
    settings_dir = tmp_path / "settings"
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(settings_dir))
    monkeypatch.setenv("DECKY_PLUGIN_RUNTIME_DIR", str(runtime_dir))

    module = _load_decky_main()
    plugin = module.Plugin()

    plugin._save_settings(
        {
            "server_url": "https://immich.example",
            "api_key": "secret",
            "exiftool_path": "/usr/bin/exiftool",
        }
    )

    settings_file = settings_dir / "settings.json"
    assert stat.S_IMODE(settings_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(settings_file.stat().st_mode) == 0o600


def test_strip_native_artifacts_removes_host_extension_modules(tmp_path: Path) -> None:
    package_dir = tmp_path / "py_modules" / "package"
    package_dir.mkdir(parents=True)
    native_files = [
        package_dir / "speedup.cpython-314-darwin.so",
        package_dir / "speedup.dylib",
        package_dir / "speedup.pyd",
    ]
    keep_file = package_dir / "fallback.py"
    keep_file.write_text("VALUE = 1\n", encoding="utf-8")
    for native_file in native_files:
        native_file.write_bytes(b"native")

    _load_package_decky()._strip_native_artifacts(tmp_path / "py_modules")

    assert keep_file.exists()
    assert not any(native_file.exists() for native_file in native_files)


def _load_decky_main():
    spec = importlib.util.spec_from_file_location(
        "decky_main_test", ROOT / "decky" / "main.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_package_decky():
    global package_decky
    if package_decky is None:
        spec = importlib.util.spec_from_file_location(
            "package_decky_test", ROOT / "scripts" / "package_decky.py"
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        package_decky = module
    return package_decky
