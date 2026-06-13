"""Reusable Steam media sync service for CLI and Decky backends."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ...core import ImmichConfig, UploadTracker, get_exiftool_path, get_immich_config
from ...resolvers.game_name import get_game_name
from .clips import (
    TRACKING_FILE as CLIPS_TRACKING_FILE,
    discover_clips,
    process_clip,
)
from .uploader import (
    TRACKING_FILE as SCREENSHOTS_TRACKING_FILE,
    get_all_screenshots,
    process_screenshot,
)

ProgressCallback = Callable[[dict[str, Any]], None]


def check_steam_dependencies() -> dict[str, bool]:
    return {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "exiftool": shutil.which(get_exiftool_path()) is not None,
    }


def scan_steam_media(
    *,
    steam_dir: str | os.PathLike[str] | None = None,
    state_dir: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    screenshots = get_all_screenshots(steam_dir)
    clips = discover_clips(steam_dir)

    screenshot_tracker = UploadTracker(
        _state_path(state_dir, SCREENSHOTS_TRACKING_FILE)
    )
    clip_tracker = UploadTracker(_state_path(state_dir, CLIPS_TRACKING_FILE))

    return {
        "screenshots": _scan_summary(screenshots, screenshot_tracker, "filename"),
        "clips": _scan_summary(clips, clip_tracker, "clip_name"),
        "dependencies": check_steam_dependencies(),
    }


def sync_steam_screenshots(
    *,
    output_dir: str | os.PathLike[str] | None = None,
    upload: bool = True,
    cfg: ImmichConfig | None = None,
    steam_dir: str | os.PathLike[str] | None = None,
    state_dir: str | os.PathLike[str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not upload and not output_dir:
        return _summary(
            "screenshots",
            status="noop",
            message="Nothing to do: --no-upload without --output",
        )

    cfg = _resolve_config(upload, cfg)
    tracker = UploadTracker(_state_path(state_dir, SCREENSHOTS_TRACKING_FILE))
    all_screenshots = get_all_screenshots(steam_dir)
    uploaded_keys = _uploaded_keys(tracker, "filename")
    new = [
        s
        for s in all_screenshots
        if _is_new_item(s, tracker, uploaded_keys, "filename")
    ]
    summary = _summary("screenshots", total=len(all_screenshots), new=len(new))

    if not all_screenshots:
        summary["status"] = "empty"
        summary["message"] = "Screenshots: no media found"
        return summary
    if not new:
        summary["status"] = "up_to_date"
        summary["message"] = "Screenshots: up to date"
        return summary

    _emit(progress_callback, kind="screenshots", event="start", total=len(new))
    outcomes: list[dict[str, Any]] = []
    for index, screenshot in enumerate(new, start=1):
        name = screenshot["filename"]
        _emit(
            progress_callback,
            kind="screenshots",
            event="item",
            current=index,
            total=len(new),
            filename=name,
        )

        if not os.path.exists(screenshot["full_path"]):
            _record_item(summary, name, "failed", "not found")
            outcomes.append(_outcome(screenshot, "failed"))
            continue

        game_name = get_game_name(screenshot["game_id"], cache_dir=state_dir)
        try:
            result = process_screenshot(
                screenshot["full_path"],
                game_name,
                cfg,
                output_dir=os.fspath(output_dir) if output_dir else None,
                upload=upload,
            )
            status = (
                "duplicate" if result and result.get("status") == "duplicate" else "ok"
            )
            _record_item(summary, name, status)
            outcomes.append(_outcome(screenshot, status))
            tracker.record(
                {
                    "filename": screenshot["filename"],
                    "upload_time": datetime.now().isoformat(),
                    "creation_time": screenshot["creation_time"],
                }
            )
        except Exception as exc:
            _record_item(summary, name, "failed", str(exc))
            outcomes.append(_outcome(screenshot, "failed"))

    _finish_sync_summary(summary, tracker, outcomes, progress_callback)
    return summary


def sync_steam_clips(
    *,
    output_dir: str | os.PathLike[str] | None = None,
    upload: bool = True,
    cfg: ImmichConfig | None = None,
    steam_dir: str | os.PathLike[str] | None = None,
    state_dir: str | os.PathLike[str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not upload and not output_dir:
        return _summary(
            "clips",
            status="noop",
            message="Nothing to do: --no-upload without --output",
        )

    cfg = _resolve_config(upload, cfg)
    tracker = UploadTracker(_state_path(state_dir, CLIPS_TRACKING_FILE))
    all_clips = discover_clips(steam_dir)
    uploaded_keys = _uploaded_keys(tracker, "clip_name")
    new = [c for c in all_clips if _is_new_item(c, tracker, uploaded_keys, "clip_name")]
    summary = _summary("clips", total=len(all_clips), new=len(new))

    if not all_clips:
        summary["status"] = "empty"
        summary["message"] = "Clips: no media found"
        return summary
    if not new:
        summary["status"] = "up_to_date"
        summary["message"] = "Clips: up to date"
        return summary
    if not check_steam_dependencies()["ffmpeg"]:
        summary["status"] = "dependency_error"
        summary["message"] = "Clips: missing ffmpeg; clip conversion is unavailable"
        return summary

    _emit(progress_callback, kind="clips", event="start", total=len(new))
    outcomes: list[dict[str, Any]] = []
    for index, clip in enumerate(new, start=1):
        name = clip["clip_name"]
        _emit(
            progress_callback,
            kind="clips",
            event="item",
            current=index,
            total=len(new),
            filename=name,
        )

        game_name = get_game_name(clip["game_id"], cache_dir=state_dir)
        try:
            result = process_clip(
                clip,
                game_name,
                cfg,
                output_dir=os.fspath(output_dir) if output_dir else None,
                upload=upload,
            )
            status = (
                "duplicate" if result and result.get("status") == "duplicate" else "ok"
            )
            _record_item(summary, name, status)
            outcomes.append(_outcome(clip, status))
            tracker.record(
                {
                    "clip_name": clip["clip_name"],
                    "game_id": clip["game_id"],
                    "upload_time": datetime.now().isoformat(),
                    "creation_time": clip["creation_time"],
                }
            )
        except Exception as exc:
            _record_item(summary, name, "failed", str(exc))
            outcomes.append(_outcome(clip, "failed"))

    _finish_sync_summary(summary, tracker, outcomes, progress_callback)
    return summary


def print_cli_summary(summary: dict[str, Any]) -> None:
    status = summary.get("status")
    if status in {"empty", "up_to_date"}:
        return
    message = summary.get("message")
    if isinstance(message, str) and message:
        print(message)


def _resolve_config(upload: bool, cfg: ImmichConfig | None) -> ImmichConfig | None:
    if upload and cfg is None:
        return get_immich_config()
    return cfg


def _state_path(state_dir: str | os.PathLike[str] | None, filename: str) -> str | Path:
    if state_dir is None:
        return filename
    path = Path(state_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path / filename


def _scan_summary(
    items: list[dict[str, Any]], tracker: UploadTracker, name_key: str
) -> dict[str, Any]:
    uploaded_keys = _uploaded_keys(tracker, name_key)
    new = [
        item for item in items if _is_new_item(item, tracker, uploaded_keys, name_key)
    ]
    return {
        "total": len(items),
        "new": len(new),
        "lastUploadTime": tracker.last_upload_time,
    }


def _summary(
    kind: str,
    *,
    status: str = "pending",
    total: int = 0,
    new: int = 0,
    message: str = "",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": status,
        "total": total,
        "new": new,
        "ok": 0,
        "duplicates": 0,
        "failed": 0,
        "items": [],
        "message": message,
    }


def _record_item(
    summary: dict[str, Any], name: str, status: str, error: str | None = None
) -> None:
    if status == "duplicate":
        summary["duplicates"] += 1
    elif status == "failed":
        summary["failed"] += 1
    else:
        summary["ok"] += 1

    item = {"name": name, "status": status}
    if error:
        item["error"] = error
    summary["items"].append(item)


def _finish_sync_summary(
    summary: dict[str, Any],
    tracker: UploadTracker,
    outcomes: list[dict[str, Any]],
    progress_callback: ProgressCallback | None,
) -> None:
    if summary["ok"] or summary["duplicates"]:
        last_success_time = _last_contiguous_success_time(
            tracker.last_upload_time, outcomes
        )
        if last_success_time > tracker.last_upload_time:
            tracker.update_time(last_success_time)
        tracker.save()

    if summary["failed"] and not (summary["ok"] or summary["duplicates"]):
        summary["status"] = "failed"
    elif summary["failed"]:
        summary["status"] = "partial"
    else:
        summary["status"] = "processed"

    parts = [f"{summary['ok']} ok"]
    if summary["duplicates"]:
        parts.append(f"{summary['duplicates']} duplicates")
    if summary["failed"]:
        parts.append(f"{summary['failed']} failed")
    label = "Screenshots" if summary["kind"] == "screenshots" else "Clips"
    summary["message"] = f"{label}: {', '.join(parts)} / {summary['new']}"
    _emit(progress_callback, kind=summary["kind"], event="complete", summary=summary)


def _emit(progress_callback: ProgressCallback | None, **event: Any) -> None:
    if progress_callback:
        progress_callback(event)


def _uploaded_keys(tracker: UploadTracker, name_key: str) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for entry in tracker.uploaded_items:
        name = _item_name(entry, name_key)
        creation_time = entry.get("creation_time")
        if name and creation_time is not None:
            keys.add((name, int(creation_time)))
    return keys


def _is_new_item(
    item: dict[str, Any],
    tracker: UploadTracker,
    uploaded_keys: set[tuple[str, int]],
    name_key: str,
) -> bool:
    creation_time = int(item["creation_time"])
    if not tracker.is_new(creation_time):
        return False
    return (_item_name(item, name_key), creation_time) not in uploaded_keys


def _item_name(item: dict[str, Any], name_key: str) -> str:
    value = item.get(name_key) or item.get("filename") or item.get("clip_name") or ""
    return str(value)


def _outcome(item: dict[str, Any], status: str) -> dict[str, Any]:
    return {"creation_time": int(item["creation_time"]), "status": status}


def _last_contiguous_success_time(
    current_time: int, outcomes: list[dict[str, Any]]
) -> int:
    last_success_time = current_time
    for outcome in sorted(outcomes, key=lambda item: int(item["creation_time"])):
        if outcome["status"] == "failed":
            break
        last_success_time = int(outcome["creation_time"])
    return last_success_time
