"""Steam game clip processor — DASH segments → MP4, optionally upload."""

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ...core import (
    STEAM_DECK,
    MediaMetadata,
    get_immich_config,
    set_file_timestamps,
    set_video_metadata,
    upload_to_immich,
)
from .utils import GetAccountId, steamdir

TRACKING_FILE = "clips_tracker.json"


def get_clips_directory(
    steam_dir: str | os.PathLike[str] | None = None,
) -> Optional[str]:
    try:
        user = GetAccountId(steam_dir)
        if user is None:
            return None
        base = Path(steam_dir or steamdir).expanduser()
        clips_dir = base / "userdata" / str(user) / "gamerecordings" / "clips"
        if clips_dir.exists():
            return str(clips_dir)
    except Exception:
        pass
    return None


def discover_clips(steam_dir: str | os.PathLike[str] | None = None) -> List[Dict]:
    clips_dir = get_clips_directory(steam_dir)
    if not clips_dir:
        return []

    clips = []
    clip_pattern = re.compile(r"^clip_(\d+)_(\d{8})_(\d{6})$")

    try:
        for item in os.listdir(clips_dir):
            item_path = os.path.join(clips_dir, item)
            if not os.path.isdir(item_path):
                continue

            match = clip_pattern.match(item)
            if not match:
                continue

            game_id, date_str, time_str = match.groups()
            try:
                creation_time = datetime.strptime(
                    f"{date_str}_{time_str}", "%Y%m%d_%H%M%S"
                ).timestamp()
            except ValueError:
                creation_time = os.path.getmtime(item_path)

            session_mpd = None
            video_dir = os.path.join(item_path, "video")
            if os.path.exists(video_dir):
                for subdir in os.listdir(video_dir):
                    mpd = os.path.join(video_dir, subdir, "session.mpd")
                    if os.path.isfile(mpd):
                        session_mpd = mpd
                        break

            thumbnail = os.path.join(item_path, "thumbnail.jpg")

            clips.append(
                {
                    "clip_path": item_path,
                    "game_id": int(game_id),
                    "creation_time": int(creation_time),
                    "session_mpd": session_mpd,
                    "thumbnail": thumbnail if os.path.exists(thumbnail) else None,
                    "clip_name": item,
                }
            )
    except Exception as e:
        print(f"Error discovering clips: {e}")

    clips.sort(key=lambda x: x["creation_time"])
    return clips


def convert_clip_to_mp4(session_mpd_path: str, output_path: str) -> bool:
    try:
        if not shutil.which("ffmpeg"):
            return False

        mpd_dir = os.path.dirname(session_mpd_path)
        all_files = os.listdir(mpd_dir)

        video_init = audio_init = None
        video_chunks: list[str] = []
        audio_chunks: list[str] = []

        for f in all_files:
            fp = os.path.join(mpd_dir, f)
            if f == "init-stream0.m4s":
                video_init = fp
            elif f == "init-stream1.m4s":
                audio_init = fp
            elif f.startswith("chunk-stream0-") and f.endswith(".m4s"):
                video_chunks.append(fp)
            elif f.startswith("chunk-stream1-") and f.endswith(".m4s"):
                audio_chunks.append(fp)

        video_chunks.sort()
        audio_chunks.sort()

        if video_init:
            video_chunks.insert(0, video_init)
        if audio_init:
            audio_chunks.insert(0, audio_init)

        if not video_chunks:
            return False

        with tempfile.NamedTemporaryFile(suffix="_v.mp4", delete=False) as tv:
            tv_path = tv.name
        with tempfile.NamedTemporaryFile(suffix="_a.mp4", delete=False) as ta:
            ta_path = ta.name

        try:
            _concat_chunks(video_chunks, tv_path)
            if audio_chunks:
                _concat_chunks(audio_chunks, ta_path)

            inputs = ["-i", tv_path]
            if audio_chunks:
                inputs += ["-i", ta_path]

            cmd = [
                "ffmpeg",
                "-y",
                *inputs,
                "-c",
                "copy",
                "-analyzeduration",
                "100M",
                "-probesize",
                "50M",
                output_path,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return r.returncode == 0 and os.path.exists(output_path)
        finally:
            for p in (tv_path, ta_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass
    except Exception:
        return False


def _concat_chunks(chunks: list[str], dest: str) -> None:
    with open(dest, "wb") as out:
        for c in chunks:
            if os.path.exists(c):
                with open(c, "rb") as f:
                    out.write(f.read())


def process_clip(
    clip: Dict,
    game_name: Optional[str],
    cfg,
    *,
    output_dir: str | None = None,
    upload: bool = True,
) -> dict | None:
    """Process a clip. Returns Immich response dict, or None if not uploaded."""
    if not clip["session_mpd"]:
        raise ValueError("no session.mpd")

    with tempfile.NamedTemporaryFile(suffix="_raw.mp4", delete=False) as f:
        raw_path = f.name

    if output_dir:
        subfolder = game_name or "Unknown"
        dest = os.path.join(output_dir, subfolder)
        os.makedirs(dest, exist_ok=True)
        final_path = os.path.join(dest, f"{clip['clip_name']}.mp4")
    else:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            final_path = f.name

    try:
        if not convert_clip_to_mp4(clip["session_mpd"], raw_path):
            raise RuntimeError("ffmpeg conversion failed")

        creation_dt = datetime.fromtimestamp(clip["creation_time"])
        meta = MediaMetadata(
            creation_date=creation_dt, device=STEAM_DECK, game_name=game_name
        )

        if not set_video_metadata(raw_path, final_path, meta, container="mp4"):
            shutil.copy2(raw_path, final_path)

        set_file_timestamps(final_path, creation_dt)

        if upload and cfg:
            return upload_to_immich(
                final_path,
                cfg.api_key,
                cfg.server_url,
                device=STEAM_DECK,
                creation_date=creation_dt,
            )
        return None
    finally:
        try:
            os.unlink(raw_path)
        except OSError:
            pass
        if not output_dir:
            try:
                if os.path.exists(final_path):
                    os.unlink(final_path)
            except OSError:
                pass


def main(
    *,
    output_dir: str | None = None,
    upload: bool = True,
):
    from .service import print_cli_summary, sync_steam_clips

    cfg = get_immich_config() if upload else None
    summary = sync_steam_clips(output_dir=output_dir, upload=upload, cfg=cfg)
    print_cli_summary(summary)
