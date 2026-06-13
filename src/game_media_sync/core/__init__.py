"""game_media_sync.core — shared upload / config / metadata helpers."""

from .config import ImmichConfig, get_immich_config
from .metadata import (
    STEAM_DECK,
    PS5,
    SWITCH2,
    DeviceInfo,
    MediaMetadata,
    get_exiftool_path,
    set_file_timestamps,
    set_image_metadata,
    set_video_metadata,
)
from .tracker import UploadTracker
from .upload import upload_to_immich

__all__ = [
    "upload_to_immich",
    "ImmichConfig",
    "get_immich_config",
    "DeviceInfo",
    "MediaMetadata",
    "STEAM_DECK",
    "PS5",
    "SWITCH2",
    "get_exiftool_path",
    "set_image_metadata",
    "set_video_metadata",
    "set_file_timestamps",
    "UploadTracker",
]
