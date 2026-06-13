#!/usr/bin/env python3
"""
Game Name Resolver
Resolves a Steam game's human-readable name from its app ID.

Resolution strategy:
- SteamDB HTML page: https://steamdb.info/app/<app_id>/ (parse <title>)
"""

import html as htmllib
import json
import os
import re
from functools import lru_cache
from typing import Optional

import requests


_CACHE_FILENAME = "steam_app_cache.json"
_DEFAULT_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    _CACHE_FILENAME,
)
_cache_dicts: dict[str, dict[str, str]] = {}


def _try_steamdb(app_id: int, timeout: float = 5.0) -> Optional[str]:
    """Query SteamDB app page and parse the game name from multiple HTML sources."""
    url = f"https://steamdb.info/app/{app_id}/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://steamdb.info/",
        "Connection": "close",
    }

    def _clean_candidate(text: str) -> Optional[str]:
        text = htmllib.unescape(text or "").strip()
        if not text:
            return None
        if "·" in text:
            text = text.split("·", 1)[0].strip()
        for marker in ["· SteamDB", "- SteamDB", "· AppID", "AppID:", "on SteamDB"]:
            idx = text.find(marker)
            if idx > 0:
                text = text[:idx].strip()
        return text or None

    def _parse_html_for_name(html_text: str) -> Optional[str]:
        m = re.search(
            r"<title>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL
        )
        if m:
            cleaned = _clean_candidate(m.group(1))
            if cleaned:
                return cleaned

        m = re.search(
            r"<meta[^>]+property=\"og:title\"[^>]+content=\"(.*?)\"",
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m:
            cleaned = _clean_candidate(m.group(1))
            if cleaned:
                return cleaned

        m = re.search(
            r"<meta[^>]+name=\"twitter:title\"[^>]+content=\"(.*?)\"",
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m:
            cleaned = _clean_candidate(m.group(1))
            if cleaned:
                return cleaned

        m = re.search(
            r"<script[^>]+type=\"application/ld\+json\"[^>]*>(.*?)</script>",
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m:
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict) and isinstance(data.get("name"), str):
                    cleaned = _clean_candidate(data["name"])
                    if cleaned:
                        return cleaned
            except Exception:
                pass

        m = re.search(
            r"<h1[^>]*>(.*?)</h1>", html_text, flags=re.IGNORECASE | re.DOTALL
        )
        if m:
            content = re.sub(r"<[^>]+>", "", m.group(1))
            cleaned = _clean_candidate(content)
            if cleaned:
                return cleaned

        return None

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        html_text = resp.text
        name = _parse_html_for_name(html_text)
        if name:
            return name

        resp2 = requests.get(url + "info/", headers=headers, timeout=timeout)
        resp2.raise_for_status()
        html_text2 = resp2.text
        name2 = _parse_html_for_name(html_text2)
        if name2:
            return name2
    except Exception:
        pass
    return None


def _cache_path(cache_dir: str | os.PathLike[str] | None = None) -> str:
    if cache_dir:
        return os.path.join(os.fspath(cache_dir), _CACHE_FILENAME)
    return _DEFAULT_CACHE_PATH


@lru_cache(maxsize=1024)
def _lookup_remote_game_name(app_id: int) -> Optional[str]:
    name = _try_store_api(app_id)
    if name:
        return name
    return _try_steamdb(app_id)


def get_game_name(
    app_id: int, cache_dir: str | os.PathLike[str] | None = None
) -> Optional[str]:
    """Resolve human-readable game name by app ID.

    Returns the name string if found, else None.
    """
    cache_path = _cache_path(cache_dir)
    cached = _get_cached_name(app_id, cache_path)
    if cached:
        return cached

    name = _lookup_remote_game_name(app_id)
    if name:
        _set_cached_name(app_id, name, cache_path)
        return name
    return None


def _try_store_api(
    app_id: int, timeout: float = 5.0, language: str = "en", country: str = "us"
) -> Optional[str]:
    """Query the public Steam Store API for app details to get the name.

    Docs: https://store.steampowered.com/api/appdetails?appids=<id>
    """
    try:
        resp = requests.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": str(app_id), "cc": country, "l": language},
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        entry = payload.get(str(app_id)) or payload.get(int(app_id))
        if (
            isinstance(entry, dict)
            and entry.get("success")
            and isinstance(entry.get("data"), dict)
        ):
            name = entry["data"].get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    except Exception:
        pass
    return None


def _load_cache(cache_path: str) -> dict[str, str]:
    if cache_path in _cache_dicts:
        return _cache_dicts[cache_path]
    try:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    _cache_dicts[cache_path] = {
                        str(k): v for k, v in data.items() if isinstance(v, str)
                    }
                    return _cache_dicts[cache_path]
    except Exception:
        pass
    _cache_dicts[cache_path] = {}
    return _cache_dicts[cache_path]


def _save_cache(cache_path: str) -> None:
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        tmp_path = cache_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(_load_cache(cache_path), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, cache_path)
    except Exception:
        pass


def _get_cached_name(app_id: int, cache_path: str) -> Optional[str]:
    cache = _load_cache(cache_path)
    value = cache.get(str(app_id))
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _set_cached_name(app_id: int, name: str, cache_path: str) -> None:
    cache = _load_cache(cache_path)
    if cache.get(str(app_id)) == name:
        return
    cache[str(app_id)] = name
    _save_cache(cache_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m game_media_sync.resolvers.game_name <app_id>")
        sys.exit(1)
    try:
        app_id = int(sys.argv[1])
    except ValueError:
        print("App ID must be an integer")
        sys.exit(1)

    result = get_game_name(app_id)
    if result:
        print(json.dumps({"app_id": app_id, "name": result}))
    else:
        print(json.dumps({"app_id": app_id, "name": None}))
