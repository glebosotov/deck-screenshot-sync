from __future__ import annotations

import json
import os
from pathlib import Path

from game_media_sync.core.metadata import get_exiftool_path
from game_media_sync.platforms.steam import service


def test_scan_steam_media_uses_state_dir_trackers(tmp_path: Path) -> None:
    steam_dir = _steam_tree(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "upload_tracker.json").write_text(
        json.dumps({"last_upload_time": 150, "uploaded_items": []}),
        encoding="utf-8",
    )
    (state_dir / "clips_tracker.json").write_text(
        json.dumps({"last_upload_time": 0, "uploaded_items": []}),
        encoding="utf-8",
    )

    result = service.scan_steam_media(steam_dir=steam_dir, state_dir=state_dir)

    assert result["screenshots"]["total"] == 2
    assert result["screenshots"]["new"] == 1
    assert result["clips"]["total"] == 1
    assert result["clips"]["new"] == 1


def test_sync_steam_screenshots_records_summary_and_tracker(
    tmp_path: Path, monkeypatch
) -> None:
    steam_dir = _steam_tree(tmp_path)
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "out"

    monkeypatch.setattr(service, "get_game_name", lambda *_args, **_kwargs: "Game")
    monkeypatch.setattr(
        service,
        "process_screenshot",
        lambda *_args, **_kwargs: {"status": "created"},
    )

    summary = service.sync_steam_screenshots(
        output_dir=output_dir,
        upload=False,
        steam_dir=steam_dir,
        state_dir=state_dir,
    )

    assert summary["status"] == "processed"
    assert summary["ok"] == 2
    assert summary["failed"] == 0

    tracker = json.loads((state_dir / "upload_tracker.json").read_text())
    assert tracker["last_upload_time"] == 200
    assert len(tracker["uploaded_items"]) == 2


def test_sync_steam_clips_reports_missing_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    steam_dir = _steam_tree(tmp_path)
    state_dir = tmp_path / "state"

    monkeypatch.setattr(
        service,
        "check_steam_dependencies",
        lambda: {"ffmpeg": False, "exiftool": True},
    )

    summary = service.sync_steam_clips(
        output_dir=tmp_path / "clips",
        upload=False,
        steam_dir=steam_dir,
        state_dir=state_dir,
    )

    assert summary["status"] == "dependency_error"
    assert "ffmpeg" in summary["message"]


def test_success_after_failure_does_not_skip_failed_media(
    tmp_path: Path, monkeypatch
) -> None:
    steam_dir = _steam_tree(tmp_path)
    state_dir = tmp_path / "state"

    monkeypatch.setattr(service, "get_game_name", lambda *_args, **_kwargs: "Game")

    def fake_process_screenshot(filepath: str, *_args, **_kwargs):
        if filepath.endswith("one.jpg"):
            raise RuntimeError("temporary upload failure")
        return {"status": "created"}

    monkeypatch.setattr(service, "process_screenshot", fake_process_screenshot)

    summary = service.sync_steam_screenshots(
        output_dir=tmp_path / "out",
        upload=False,
        steam_dir=steam_dir,
        state_dir=state_dir,
    )

    assert summary["status"] == "partial"
    assert summary["ok"] == 1
    assert summary["failed"] == 1

    tracker = json.loads((state_dir / "upload_tracker.json").read_text())
    assert tracker["last_upload_time"] == 0
    assert [item["filename"] for item in tracker["uploaded_items"]] == [
        "123/screenshots/two.jpg"
    ]

    scan = service.scan_steam_media(steam_dir=steam_dir, state_dir=state_dir)
    assert scan["screenshots"]["new"] == 1


def test_sync_without_upload_or_output_is_noop(tmp_path: Path) -> None:
    summary = service.sync_steam_screenshots(
        upload=False,
        steam_dir=tmp_path / "missing-steam",
        state_dir=tmp_path / "state",
    )

    assert summary["status"] == "noop"


def test_custom_exiftool_path_can_be_executable(tmp_path: Path, monkeypatch) -> None:
    exiftool = tmp_path / "exiftool-custom"
    exiftool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exiftool.chmod(exiftool.stat().st_mode | 0o111)

    monkeypatch.setenv("EXIFTOOL_PATH", os.fspath(exiftool))

    assert get_exiftool_path() == os.fspath(exiftool)
    assert service.check_steam_dependencies()["exiftool"] is True


def _steam_tree(tmp_path: Path) -> Path:
    steam_dir = tmp_path / "Steam"
    user_dir = steam_dir / "userdata" / "1"
    remote_dir = user_dir / "760" / "remote" / "123" / "screenshots"
    remote_dir.mkdir(parents=True)
    (steam_dir / "config").mkdir(parents=True)

    (steam_dir / "config" / "loginusers.vdf").write_text(
        """
"users"
{
    "1"
    {
        "MostRecent" "1"
    }
}
""".strip(),
        encoding="utf-8",
    )
    (user_dir / "760").mkdir(exist_ok=True)
    (user_dir / "760" / "screenshots.vdf").write_text(
        """
"screenshots"
{
    "123"
    {
        "0"
        {
            "filename" "123/screenshots/one.jpg"
            "creation" "100"
        }
        "1"
        {
            "filename" "123/screenshots/two.jpg"
            "creation" "200"
        }
    }
}
""".strip(),
        encoding="utf-8",
    )
    (remote_dir / "one.jpg").write_bytes(b"one")
    (remote_dir / "two.jpg").write_bytes(b"two")

    clip_dir = (
        user_dir
        / "gamerecordings"
        / "clips"
        / "clip_123_20240102_030405"
        / "video"
        / "stream"
    )
    clip_dir.mkdir(parents=True)
    (clip_dir / "session.mpd").write_text("<MPD />", encoding="utf-8")
    return steam_dir
