# ytdl-gui

A small PySide6 desktop GUI over [yt-dlp](https://github.com/yt-dlp/yt-dlp).
Search by title or paste a URL, browse results as **thumbnail cards**, pick a
format, and download — with a live progress bar — instead of fiddling with CLI
flags. Ships with a dark theme.

## How it works

- `engine.py` — all yt-dlp interaction. Uses the in-process API
  (`YoutubeDL.extract_info` for querying/searching, `YoutubeDL.download` for
  downloading) rather than shelling out, so the UI gets real progress hooks.
- `app.py` — the GUI. Searches, queries, downloads, and thumbnail-image fetches
  all run on `QThreadPool` workers so the window never freezes. Thumbnails are
  fetched once and cached.
- `style.qss` — the dark theme, loaded at startup.

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) on your PATH (needed to merge separate
  video+audio streams and to convert formats).

## Setup

```bash
cd ytdl-gui
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Usage

You can start from either a link or a title:

- **Paste a URL** → press Enter (or click **Go**) to load its formats directly.
- **Type a title** (e.g. `daft punk one more time`) → it searches and shows
  results as thumbnail cards; click a card to load its formats. Use the dropdown
  to search **YouTube** (videos) or **SoundCloud** (music).

Then just hit one of the one-click buttons — no need to read the format list:

- **🎬 Best video** — highest-quality video + audio, merged to mp4.
- **🎵 Best audio** — highest-quality audio in the format chosen from the
  dropdown next to it: **MP3**, **M4A**, **Opus**, **FLAC**, **WAV**, or
  **Original (no re-encode)** to keep the source stream losslessly.

Or, for full control, pick a row in the formats table and hit **Download
selected** (a "video only" row is automatically paired with the best audio).

Choose a save folder if you don't want `~/Downloads`. The progress bar and
status line show speed/ETA and post-processing (merge / mp3 conversion).

URL vs. search is auto-detected: anything starting with `http(s)://` (or a bare
`domain.com/path`) is treated as a link; everything else is a search query.

## Downloads (prebuilt binaries)

Grab a self-contained binary from the [Releases](../../releases) page — no
Python or ffmpeg install needed, both are bundled:

- **Windows:** `ytdl-gui-windows.exe`
- **Linux:** `ytdl-gui-linux` (`chmod +x ytdl-gui-linux && ./ytdl-gui-linux`)

## Building a binary yourself

```bash
pip install -r requirements.txt pyinstaller
# optionally bundle ffmpeg so merging/mp3 work without a system ffmpeg:
export FFMPEG_BIN=$(command -v ffmpeg)      # Windows: set FFMPEG_BIN=C:\path\ffmpeg.exe
pyinstaller --noconfirm ytdl-gui.spec
# -> dist/ytdl-gui (or dist/ytdl-gui.exe on Windows)
```

## Cutting a release

Releases are built automatically by GitHub Actions
(`.github/workflows/release.yml`). Push a version tag and it builds Windows +
Linux binaries and attaches them to a new GitHub Release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

You can also trigger the workflow manually from the Actions tab (it builds the
binaries without publishing a release).

## Notes

- Playlist/channel URLs are reduced to their first entry (`noplaylist`).
- Merged output defaults to `.mp4`.
- Search uses yt-dlp's `ytsearch` / `scsearch` with fast flat extraction; the
  full format list is only fetched once you pick a result.
