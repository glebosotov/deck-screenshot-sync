"""Steam screenshot processor and uploader."""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import vdf

from ...core import (
    STEAM_DECK,
    MediaMetadata,
    get_immich_config,
    set_file_timestamps,
    set_image_metadata,
    upload_to_immich,
)
from .utils import GetAccountId, steamdir

TRACKING_FILE = "upload_tracker.json"


def get_all_screenshots(steam_dir: str | os.PathLike[str] | None = None):
    try:
        user = GetAccountId(steam_dir)
        if user is None:
            return []

        base = Path(steam_dir or steamdir).expanduser()
        vdf_path = base / "userdata" / str(user) / "760" / "screenshots.vdf"
        if not vdf_path.exists():
            return []

        with open(vdf_path, "r", encoding="utf-8") as f:
            d = vdf.parse(f)

        screenshots = d.get("screenshots") or d.get("Screenshots")
        if not screenshots:
            return []

        result = []
        for game in screenshots:
            for sid in screenshots[game]:
                s = screenshots[game][sid]
                if "creation" in s and "filename" in s:
                    result.append(
                        {
                            "game_id": int(game),
                            "creation_time": int(s["creation"]),
                            "filename": s["filename"],
                            "full_path": str(
                                base
                                / "userdata"
                                / str(user)
                                / "760"
                                / "remote"
                                / s["filename"]
                            ),
                        }
                    )

        result.sort(key=lambda x: x["creation_time"])
        return result
    except Exception as e:
        print(f"Error reading screenshots: {e}")
        return []


def process_screenshot(
    filepath: str,
    game_name: str | None,
    cfg,
    *,
    output_dir: str | None = None,
    upload: bool = True,
) -> dict | None:
    """Process a screenshot. Returns Immich response dict, or None if not uploaded."""
    creation_date = datetime.fromtimestamp(os.path.getmtime(filepath))
    meta = MediaMetadata(
        creation_date=creation_date, device=STEAM_DECK, game_name=game_name
    )

    if output_dir:
        subfolder = game_name or "Unknown"
        dest = os.path.join(output_dir, subfolder)
        os.makedirs(dest, exist_ok=True)
        dest_path = os.path.join(dest, os.path.basename(filepath))
    else:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            dest_path = tmp.name

    try:
        if not set_image_metadata(filepath, dest_path, meta):
            shutil.copy2(filepath, dest_path)

        set_file_timestamps(dest_path, creation_date)

        if upload and cfg:
            return upload_to_immich(
                dest_path,
                cfg.api_key,
                cfg.server_url,
                device=STEAM_DECK,
                creation_date=creation_date,
            )
        return None
    finally:
        if not output_dir:
            try:
                os.unlink(dest_path)
            except OSError:
                pass


def main(
    *,
    output_dir: str | None = None,
    upload: bool = True,
):
    from .service import print_cli_summary, sync_steam_screenshots

    cfg = get_immich_config() if upload else None
    summary = sync_steam_screenshots(output_dir=output_dir, upload=upload, cfg=cfg)
    print_cli_summary(summary)
