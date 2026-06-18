# ytdl-gui

A small PySide6 desktop GUI over [yt-dlp](https://github.com/yt-dlp/yt-dlp).
Search by title or paste a URL, browse thumbnail results, and download best
video or audio — no CLI flags. Graphite dark theme.

## Install

Grab a self-contained binary from the [Releases](../../releases) page (Python
and ffmpeg bundled — nothing else to install):

- **Windows:** download and run `ytdl-gui-windows.exe`.
- **Linux:** download `ytdl-gui-linux`, then:

  ```bash
  chmod +x ytdl-gui-linux
  ./ytdl-gui-linux
  ```

## Usage

1. **Find something.** Paste a URL and press Enter, or type a title to search
   (YouTube or SoundCloud, selectable from the dropdown) and click a result.
2. **Download it.** Use **Best video** (mp4) or **Best audio** in your chosen
   format (MP3, M4A, Opus, FLAC, WAV, or Original). For a specific stream, pick
   a row in the table and use **Download selected**.

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
pyinstaller --noconfirm ytdl-gui.spec    # output in dist/
```

Pushing a `v*` tag builds Windows + Linux binaries via GitHub Actions and
attaches them to a release:

```bash
git tag v1.0.0 && git push origin v1.0.0
```
