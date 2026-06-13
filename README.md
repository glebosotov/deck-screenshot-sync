# game-media-sync

[![Lint](https://github.com/glebosotov/game-media-sync/actions/workflows/lint.yml/badge.svg)](https://github.com/glebosotov/game-media-sync/actions/workflows/lint.yml)

Sync screenshots and clips from **Steam**, **PS5**, and **Nintendo Switch 2** to [Immich](https://immich.app/).

<img src="img/sync-media-to-immich.webp" alt="Sync media to Immich" width="600">

> **⚠️ Warning**  
> This project was made with heavy AI assiatance. Although it works for me it may require some tweaks for you. Feel free to open an issue in case of troubles, but keep in mind that you are responsible for your files.

## Setup

```bash
cp .env.example .env   # fill in values
uv sync
```

### Nix + direnv development

```bash
direnv allow
uv sync --extra dev
```

The flake dev shell includes Python, `uv`, `ruff`, Node.js, `pnpm`, `ffmpeg`,
`exiftool`, and ZIP tooling. The `.envrc` only runs `use flake`; it does not
source `.env`.

Common dev tasks are wrapped by `make`:

```bash
make help
make check
make decky-release-check
make ci
```

## Usage

All platforms upload to Immich by default. Add `--no-upload` to skip.

```bash
# Steam screenshots (auto-detects Steam directory)
gmedia steam
gmedia steam --output /path/to/output --no-upload

# Steam game clips
gmedia steam-clips
gmedia steam-clips --output /path/to/clips

# PS5
gmedia ps5 --source /path/to/ps5 --output /path/to/output

# Nintendo Switch 2
gmedia switch --source /path/to/switch --output /path/to/output
```

Environment variables (`.env`):

| Variable | Description |
| --- | --- |
| `IMMICH_SERVER_URL` | Immich server URL |
| `IMMICH_API_KEY` | Immich API key |
| `EXIFTOOL_PATH` | Custom exiftool path (optional) |

## Decky Loader plugin

Build the Decky frontend:

```bash
pnpm --dir decky install
pnpm --dir decky run build
```

Create a sideloadable Decky ZIP:

```bash
python scripts/package_decky.py
```

The ZIP is written to `build/decky/game-media-sync-decky.zip`. Install it from
Decky Loader's Developer settings. The Decky plugin stores Immich credentials in
Decky's plugin settings directory and does not read this repo's `.env`.

Publish a Decky release ZIP by pushing a version tag:

```bash
git tag v0.2.0
git push origin v0.2.0
```

The `Decky Plugin Release` GitHub Actions workflow builds and verifies the ZIP,
then attaches it to the GitHub Release. It can also be run manually for an
existing tag from GitHub's workflow dispatch UI.

Decky settings live at
`/home/deck/homebrew/settings/game-media-sync/settings.json`:

```json
{
  "server_url": "https://immich.example",
  "api_key": "immich-api-key",
  "exiftool_path": "/usr/bin/exiftool"
}
```

`exiftool_path` may be either the exact executable path or a directory that
contains `exiftool`. Leave it blank to use `exiftool` from Decky's `PATH`.
