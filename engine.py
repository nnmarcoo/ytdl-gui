"""Thin wrapper around yt-dlp's in-process API.

Keeping all yt-dlp interaction here means the GUI layer never imports yt_dlp
directly and stays easy to reason about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import yt_dlp

# Maps the GUI source picker to yt-dlp's search prefix.
SEARCH_PREFIXES = {
    "YouTube": "ytsearch",
    "SoundCloud": "scsearch",
}

_URL_RE = re.compile(r"^(https?://|www\.)", re.IGNORECASE)

# Optional directory containing a bundled ffmpeg/ffprobe. Set by the app at
# startup when shipping a self-contained binary; otherwise yt-dlp uses PATH.
FFMPEG_LOCATION: str | None = None


def looks_like_url(text: str) -> bool:
    """Heuristic: is this a link to fetch, or a phrase to search for?"""
    text = text.strip()
    if _URL_RE.match(text):
        return True
    # Bare domain with a path and no spaces, e.g. youtube.com/watch?v=...
    return " " not in text and "." in text and "/" in text


@dataclass
class Format:
    """A single downloadable format, flattened for display."""

    format_id: str
    ext: str
    resolution: str
    fps: str
    vcodec: str
    acodec: str
    filesize: int | None
    note: str

    @property
    def filesize_str(self) -> str:
        if not self.filesize:
            return "?"
        mb = self.filesize / (1024 * 1024)
        if mb >= 1024:
            return f"{mb / 1024:.2f} GB"
        return f"{mb:.1f} MB"

    @property
    def kind(self) -> str:
        has_v = self.vcodec not in ("none", "", None)
        has_a = self.acodec not in ("none", "", None)
        if has_v and has_a:
            return "video+audio"
        if has_v:
            return "video only"
        if has_a:
            return "audio only"
        return "?"


@dataclass
class VideoInfo:
    """Metadata for a queried URL, plus its available formats."""

    title: str
    uploader: str
    duration: int | None
    thumbnail: str | None
    webpage_url: str
    formats: list[Format]

    @property
    def duration_str(self) -> str:
        if not self.duration:
            return "?"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


@dataclass
class SearchResult:
    """A single hit from a title/keyword search."""

    title: str
    uploader: str
    duration: int | None
    url: str
    thumbnail: str | None = None

    @property
    def duration_str(self) -> str:
        if not self.duration:
            return "?"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


def _pick_thumbnail(entry: dict) -> str | None:
    """Choose a reasonably sized thumbnail URL from a search entry."""
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        # yt-dlp orders these small -> large; the first is card-sized (~360w).
        return thumbs[0].get("url")
    return entry.get("thumbnail")


def search(query_text: str, source: str = "YouTube", limit: int = 15) -> list[SearchResult]:
    """Search by title/keywords and return lightweight result rows.

    Uses flat extraction so we get a fast list without resolving every video's
    full format list (that happens later via `query` when one is picked).
    """
    prefix = SEARCH_PREFIXES.get(source, "ytsearch")
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"{prefix}{limit}:{query_text}", download=False)

    results: list[SearchResult] = []
    for e in info.get("entries", []) or []:
        if not e:
            continue
        url = e.get("url") or e.get("webpage_url") or e.get("id")
        results.append(
            SearchResult(
                title=e.get("title", "Untitled"),
                uploader=e.get("uploader") or e.get("channel") or "",
                duration=e.get("duration"),
                url=url,
                thumbnail=_pick_thumbnail(e),
            )
        )
    return results


def query(url: str) -> VideoInfo:
    """Fetch metadata and formats for a URL without downloading anything."""
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # A playlist/channel URL yields entries; just take the first item.
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    formats: list[Format] = []
    for f in info.get("formats", []):
        formats.append(
            Format(
                format_id=f.get("format_id", "?"),
                ext=f.get("ext", "?"),
                resolution=f.get("resolution") or (f.get("height") and f"{f['height']}p") or "audio",
                fps=str(f.get("fps") or ""),
                vcodec=f.get("vcodec", "none"),
                acodec=f.get("acodec", "none"),
                filesize=f.get("filesize") or f.get("filesize_approx"),
                note=f.get("format_note", "") or "",
            )
        )

    # Largest/best formats last from yt-dlp; show best first.
    formats.reverse()

    return VideoInfo(
        title=info.get("title", "Untitled"),
        uploader=info.get("uploader", "") or "",
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail"),
        webpage_url=info.get("webpage_url", url),
        formats=formats,
    )


def download(
    url: str,
    fmt: str,
    outdir: str,
    progress_hook,
    postprocessor_hook=None,
    extract_audio: bool = False,
    audio_codec: str = "mp3",
) -> None:
    """Download `url` using format selector `fmt` into `outdir`.

    `progress_hook` receives yt-dlp's status dicts on the calling thread.
    When `extract_audio` is set, the result is transcoded to `audio_codec`
    (e.g. mp3) at the best quality via ffmpeg.
    """
    opts = {
        "format": fmt,
        "outtmpl": f"{outdir}/%(title)s.%(ext)s",
        "progress_hooks": [progress_hook],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    if postprocessor_hook is not None:
        opts["postprocessor_hooks"] = [postprocessor_hook]
    if FFMPEG_LOCATION:
        opts["ffmpeg_location"] = FFMPEG_LOCATION

    if extract_audio:
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_codec,
                "preferredquality": "0",  # 0 = best VBR for mp3
            }
        ]
    else:
        # Merge to mp4 when combining separate video+audio streams.
        opts["merge_output_format"] = "mp4"

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
