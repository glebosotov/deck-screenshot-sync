import os
import platform
import sys
from pathlib import Path

import vdf


def get_default_steam_dir(home: str | os.PathLike[str] | None = None) -> str:
    operating_system = platform.system()
    if operating_system in ("Linux", "Darwin"):
        base_home = Path(home or os.getenv("HOME") or "")
        if not str(base_home):
            sys.exit("Cannot determine HOME for Steam directory")
        return str(base_home / ".local" / "share" / "Steam")
    if operating_system == "Windows":
        return "C:/Program Files (x86)/Steam"
    sys.exit(f"Cannot handle operating system: {operating_system}")


steamdir = get_default_steam_dir() + os.sep


def _steam_path(steam_dir: str | os.PathLike[str] | None = None) -> Path:
    return Path(steam_dir or steamdir).expanduser()


def GetSteamId(steam_dir: str | os.PathLike[str] | None = None):
    loginusers = _steam_path(steam_dir) / "config" / "loginusers.vdf"
    d = vdf.parse(open(loginusers, encoding="utf-8"))
    users = d["users"]
    for id64 in users:
        if users[id64]["MostRecent"] == "1":
            return int(id64)
    return None


def GetAccountId(steam_dir: str | os.PathLike[str] | None = None):
    steam_id = GetSteamId(steam_dir)
    if steam_id is None:
        return None
    return steam_id & 0xFFFFFFFF
