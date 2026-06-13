"""Metadata embedding for images and videos (exiftool / FFmpeg)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class DeviceInfo:
    make: str
    model: str


@dataclass
class MediaMetadata:
    creation_date: datetime
    device: DeviceInfo
    game_name: Optional[str] = None


STEAM_DECK = DeviceInfo(make="Valve", model="Steam Deck")
PS5 = DeviceInfo(make="Sony Interactive Entertainment", model="PlayStation 5")
SWITCH2 = DeviceInfo(make="Nintendo", model="Nintendo Switch 2")


def get_exiftool_path() -> str:
    exiftool_path = os.getenv("EXIFTOOL_PATH")
    if not exiftool_path:
        return "exiftool"

    if os.path.isfile(exiftool_path) and os.access(exiftool_path, os.X_OK):
        return exiftool_path

    for name in ("exiftool", "exiftool.exe"):
        full = os.path.join(exiftool_path, name)
        if os.path.exists(full) and os.access(full, os.X_OK):
            return full
    return "exiftool"


def set_image_metadata(source: str, dest: str, meta: MediaMetadata) -> bool:
    """Copy *source* to *dest* and embed EXIF metadata via exiftool."""
    try:
        shutil.copy2(source, dest)
        exif_dt = meta.creation_date.strftime("%Y:%m:%d %H:%M:%S")
        cmd = [
            get_exiftool_path(),
            "-overwrite_original",
            f"-DateTime={exif_dt}",
            f"-DateTimeOriginal={exif_dt}",
            f"-DateTimeDigitized={exif_dt}",
            f"-Make={meta.device.make}",
            f"-Model={meta.device.model}",
        ]
        if meta.game_name:
            cmd.append(f"-ImageDescription={meta.game_name}")
        cmd.append(dest)

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            print(f"exiftool error on {Path(source).name}: {r.stderr.strip()}")
        return r.returncode == 0
    except Exception as e:
        print(f"image metadata error ({Path(source).name}): {e}")
        return False


def set_video_metadata(
    source: str, dest: str, meta: MediaMetadata, container: str
) -> bool:
    """Copy *source* video to *dest* and embed metadata.

    MP4 → exiftool, WebM/MOV → FFmpeg.
    """
    container = container.lower().lstrip(".")
    if container == "mp4":
        return _set_mp4_metadata(source, dest, meta)
    if container in ("webm", "mov"):
        return _set_video_metadata_ffmpeg(source, dest, meta)
    print(f"unsupported video container: {container}")
    return False


def set_file_timestamps(path: str, dt: datetime) -> None:
    try:
        ts = dt.timestamp()
        os.utime(path, (ts, ts))
    except OSError:
        pass


# -- internal -----------------------------------------------------------------


def _set_mp4_metadata(source: str, dest: str, meta: MediaMetadata) -> bool:
    try:
        shutil.copy2(source, dest)
        dt_str = meta.creation_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        cmd = [
            get_exiftool_path(),
            "-overwrite_original",
            f"-CreateDate={dt_str}",
            f"-ModifyDate={dt_str}",
            f"-MediaCreateDate={dt_str}",
            f"-MediaModifyDate={dt_str}",
            f"-Make={meta.device.make}",
            f"-Model={meta.device.model}",
            f"-CameraModelName={meta.device.model}",
        ]
        if meta.game_name:
            cmd += [
                f"-Description={meta.game_name}",
                f"-Title={meta.game_name}",
                f"-Comment={meta.game_name}",
            ]
        cmd.append(dest)

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            print(f"exiftool error on {Path(source).name}: {r.stderr.strip()}")
        return r.returncode == 0
    except Exception as e:
        print(f"mp4 metadata error ({Path(source).name}): {e}")
        return False


def _set_video_metadata_ffmpeg(source: str, dest: str, meta: MediaMetadata) -> bool:
    try:
        dt_iso = meta.creation_date.isoformat()
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            source,
            "-c",
            "copy",
            "-metadata",
            f"creation_time={dt_iso}",
            "-metadata",
            f"date={dt_iso}",
            "-metadata",
            f"make={meta.device.make}",
            "-metadata",
            f"model={meta.device.model}",
            "-metadata",
            f"manufacturer={meta.device.make}",
        ]
        if meta.game_name:
            cmd += [
                "-metadata",
                f"title={meta.game_name}",
                "-metadata",
                f"comment={meta.game_name}",
                "-metadata",
                f"description={meta.game_name}",
            ]
        cmd.append(dest)

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print(f"ffmpeg error on {Path(source).name}: {r.stderr.strip()}")
        return r.returncode == 0
    except Exception as e:
        print(f"video metadata error ({Path(source).name}): {e}")
        return False
