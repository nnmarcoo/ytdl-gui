# ytdl-gui

A small PySide6 desktop GUI over [yt-dlp](https://github.com/yt-dlp/yt-dlp).
Search by title or paste a URL, browse thumbnail results, and download best
video or audio — no CLI flags. Graphite dark theme.

## Install

Grab a self-contained binary from the [Releases](../../releases) page (Python
and ffmpeg bundled — nothing else to install):

- **Windows:** `ytdl-gui-windows.exe`
- **Linux:** `ytdl-gui-linux` → `chmod +x ytdl-gui-linux && ./ytdl-gui-linux`

## Usage

- **Paste a URL** → Enter to load its formats. **Type a title** → search
  (YouTube or SoundCloud via the dropdown) and click a result card.
- **Best video** (mp4) or **Best audio** in the chosen format (MP3 / M4A /
  Opus / FLAC / WAV / Original). Or pick a row and **Download selected**.

## Run from source

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Requires Python 3.10+ and [ffmpeg](https://ffmpeg.org/) on your PATH.

## Build & release

```bash
pip install -r requirements.txt pyinstaller
export FFMPEG_BIN=$(command -v ffmpeg)   # optional: bundle ffmpeg
pyinstaller --noconfirm ytdl-gui.spec    # -> dist/ytdl-gui[.exe]
```

Pushing a `v*` tag builds Windows + Linux binaries via GitHub Actions and
attaches them to a release:

```bash
git tag v1.0.0 && git push origin v1.0.0
```
