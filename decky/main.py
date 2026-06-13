import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_PY_MODULES = Path(__file__).resolve().parent / "py_modules"
if str(_PY_MODULES) not in sys.path:
    sys.path.insert(0, str(_PY_MODULES))

try:
    import decky as _decky
except Exception:  # pragma: no cover - only used outside Decky Loader
    _decky = None

if not all(
    hasattr(_decky, attr)
    for attr in ("DECKY_PLUGIN_RUNTIME_DIR", "DECKY_PLUGIN_SETTINGS_DIR", "logger")
):

    class _Logger:
        def info(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def error(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    class _Decky:
        DECKY_PLUGIN_RUNTIME_DIR = str(Path.cwd() / ".decky-runtime")
        DECKY_PLUGIN_SETTINGS_DIR = str(Path.cwd() / ".decky-settings")
        logger = _Logger()

    decky = _Decky()
else:
    decky = _decky

from game_media_sync.core import ImmichConfig  # noqa: E402
from game_media_sync.platforms.steam.service import (  # noqa: E402
    check_steam_dependencies,
    scan_steam_media,
    sync_steam_clips,
    sync_steam_screenshots,
)


class Plugin:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._run_state = self._idle_state()
        self._original_exiftool_path = os.getenv("EXIFTOOL_PATH")

    async def _main(self) -> None:
        self._ensure_dirs()
        decky.logger.info("game-media-sync Decky plugin loaded")

    async def _unload(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        decky.logger.info("game-media-sync Decky plugin unloaded")

    async def get_settings(self) -> dict[str, Any]:
        settings = self._load_settings()
        return {
            "serverUrl": settings.get("server_url", ""),
            "hasApiKey": bool(settings.get("api_key")),
            "exiftoolPath": settings.get("exiftool_path", ""),
        }

    async def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self._load_settings()

        if "serverUrl" in payload:
            settings["server_url"] = str(payload.get("serverUrl") or "").strip()

        if payload.get("clearApiKey"):
            settings["api_key"] = ""
        elif "apiKey" in payload and payload.get("apiKey"):
            settings["api_key"] = str(payload["apiKey"]).strip()

        if "exiftoolPath" in payload:
            settings["exiftool_path"] = str(payload.get("exiftoolPath") or "").strip()

        self._save_settings(settings)
        return await self.get_settings()

    async def scan(self) -> dict[str, Any]:
        self._apply_tool_settings()
        return scan_steam_media(state_dir=self._runtime_dir())

    async def start_sync(self, mode: str = "all") -> dict[str, Any]:
        if self._task and not self._task.done():
            return self._run_state

        self._run_state = self._idle_state()
        self._run_state.update(
            {
                "running": True,
                "mode": mode,
                "phase": "starting",
                "startedAt": datetime.now().isoformat(),
                "lastError": "",
                "lastResult": None,
            }
        )
        self._task = asyncio.create_task(self._run_sync(mode))
        return self._run_state

    async def get_run_state(self) -> dict[str, Any]:
        return self._run_state

    async def get_dependency_status(self) -> dict[str, bool]:
        self._apply_tool_settings()
        return check_steam_dependencies()

    async def _run_sync(self, mode: str) -> None:
        try:
            result = await asyncio.to_thread(self._sync_blocking, mode)
            self._run_state.update(
                {
                    "running": False,
                    "phase": "complete",
                    "progress": 1,
                    "current": self._run_state.get("total", 0),
                    "lastResult": result,
                    "finishedAt": datetime.now().isoformat(),
                }
            )
        except asyncio.CancelledError:
            self._run_state.update(
                {
                    "running": False,
                    "phase": "cancelled",
                    "lastError": "Sync cancelled",
                    "finishedAt": datetime.now().isoformat(),
                }
            )
        except Exception as exc:
            decky.logger.error(f"game-media-sync sync failed: {exc}")
            self._run_state.update(
                {
                    "running": False,
                    "phase": "error",
                    "lastError": str(exc),
                    "finishedAt": datetime.now().isoformat(),
                }
            )

    def _sync_blocking(self, mode: str) -> dict[str, Any]:
        if mode not in {"screenshots", "clips", "all"}:
            raise ValueError(f"Unknown sync mode: {mode}")

        self._apply_tool_settings()
        cfg = self._immich_config()
        summaries = []
        if mode in {"screenshots", "all"}:
            summaries.append(
                sync_steam_screenshots(
                    cfg=cfg,
                    state_dir=self._runtime_dir(),
                    progress_callback=self._progress_callback,
                )
            )
        if mode in {"clips", "all"}:
            summaries.append(
                sync_steam_clips(
                    cfg=cfg,
                    state_dir=self._runtime_dir(),
                    progress_callback=self._progress_callback,
                )
            )

        return {
            "mode": mode,
            "summaries": summaries,
            "scan": scan_steam_media(state_dir=self._runtime_dir()),
        }

    def _progress_callback(self, event: dict[str, Any]) -> None:
        if event.get("event") == "start":
            self._run_state.update(
                {
                    "phase": event.get("kind", "sync"),
                    "current": 0,
                    "total": event.get("total", 0),
                    "filename": "",
                    "progress": 0,
                }
            )
        elif event.get("event") == "item":
            total = int(event.get("total") or 0)
            current = int(event.get("current") or 0)
            self._run_state.update(
                {
                    "phase": event.get("kind", "sync"),
                    "current": current,
                    "total": total,
                    "filename": event.get("filename", ""),
                    "progress": current / total if total else 0,
                }
            )
        elif event.get("event") == "complete":
            self._run_state.update(
                {
                    "phase": event.get("kind", "sync"),
                    "filename": "",
                    "progress": 1,
                }
            )

    def _immich_config(self) -> ImmichConfig:
        settings = self._load_settings()
        server_url = str(settings.get("server_url") or "").strip()
        api_key = str(settings.get("api_key") or "").strip()
        missing = []
        if not server_url:
            missing.append("Immich server URL")
        if not api_key:
            missing.append("Immich API key")
        if missing:
            raise ValueError(f"Missing settings: {', '.join(missing)}")
        return ImmichConfig(server_url=server_url, api_key=api_key)

    def _load_settings(self) -> dict[str, Any]:
        path = self._settings_file()
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            decky.logger.error(f"Could not read settings: {exc}")
        return {"server_url": "", "api_key": "", "exiftool_path": ""}

    def _save_settings(self, settings: dict[str, Any]) -> None:
        self._ensure_dirs()
        path = self._settings_file()
        tmp_path = path.with_suffix(".json.tmp")
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
        os.replace(tmp_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError as exc:
            decky.logger.error(f"Could not restrict settings permissions: {exc}")

    def _settings_file(self) -> Path:
        return self._settings_dir() / "settings.json"

    def _settings_dir(self) -> Path:
        return Path(
            os.getenv("DECKY_PLUGIN_SETTINGS_DIR") or decky.DECKY_PLUGIN_SETTINGS_DIR
        )

    def _runtime_dir(self) -> Path:
        return Path(
            os.getenv("DECKY_PLUGIN_RUNTIME_DIR") or decky.DECKY_PLUGIN_RUNTIME_DIR
        )

    def _ensure_dirs(self) -> None:
        settings_dir = self._settings_dir()
        runtime_dir = self._runtime_dir()
        settings_dir.mkdir(parents=True, exist_ok=True)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(settings_dir, 0o700)
        except OSError as exc:
            decky.logger.error(f"Could not restrict settings directory: {exc}")

    def _apply_tool_settings(self) -> None:
        settings = self._load_settings()
        exiftool_path = str(settings.get("exiftool_path") or "").strip()
        if exiftool_path:
            os.environ["EXIFTOOL_PATH"] = exiftool_path
        elif self._original_exiftool_path:
            os.environ["EXIFTOOL_PATH"] = self._original_exiftool_path
        else:
            os.environ.pop("EXIFTOOL_PATH", None)

    @staticmethod
    def _idle_state() -> dict[str, Any]:
        return {
            "running": False,
            "mode": "",
            "phase": "idle",
            "progress": 0,
            "current": 0,
            "total": 0,
            "filename": "",
            "lastResult": None,
            "lastError": "",
            "startedAt": "",
            "finishedAt": "",
        }
