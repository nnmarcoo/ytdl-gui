"""yt-dlp interaction, isolated from the GUI layer."""

from __future__ import annotations

import re
from dataclasses import dataclass

import yt_dlp

SEARCH_PREFIXES = {
    "YouTube": "ytsearch",
    "SoundCloud": "scsearch",
}

FFMPEG_LOCATION: str | None = None

_URL_RE = re.compile(r"^(https?://|www\.)", re.IGNORECASE)
_BASE_OPTS = {"quiet": True, "no_warnings": True}


def looks_like_url(text: str) -> bool:
    text = text.strip()
    if _URL_RE.match(text):
        return True
    return " " not in text and "." in text and "/" in text


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@dataclass
class Format:
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
        return f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"

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
    title: str
    uploader: str
    duration: int | None
    thumbnail: str | None
    webpage_url: str
    formats: list[Format]

    @property
    def duration_str(self) -> str:
        return _format_duration(self.duration)


@dataclass
class SearchResult:
    title: str
    uploader: str
    duration: int | None
    url: str
    thumbnail: str | None = None

    @property
    def duration_str(self) -> str:
        return _format_duration(self.duration)


def _pick_thumbnail(entry: dict) -> str | None:
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        return thumbs[0].get("url")
    return entry.get("thumbnail")


def _resolution(fmt: dict) -> str:
    if fmt.get("resolution"):
        return fmt["resolution"]
    if fmt.get("height"):
        return f"{fmt['height']}p"
    return "audio"


def search(query_text: str, source: str = "YouTube", limit: int = 15) -> list[SearchResult]:
    """Return lightweight search hits via fast flat extraction."""
    prefix = SEARCH_PREFIXES.get(source, "ytsearch")
    opts = {**_BASE_OPTS, "extract_flat": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"{prefix}{limit}:{query_text}", download=False)

    results = []
    for e in info.get("entries") or []:
        if not e:
            continue
        results.append(
            SearchResult(
                title=e.get("title", "Untitled"),
                uploader=e.get("uploader") or e.get("channel") or "",
                duration=e.get("duration"),
                url=e.get("url") or e.get("webpage_url") or e.get("id"),
                thumbnail=_pick_thumbnail(e),
            )
        )
    return results


def query(url: str) -> VideoInfo:
    """Fetch metadata and available formats without downloading."""
    opts = {**_BASE_OPTS, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    formats = [
        Format(
            format_id=f.get("format_id", "?"),
            ext=f.get("ext", "?"),
            resolution=_resolution(f),
            fps=str(f.get("fps") or ""),
            vcodec=f.get("vcodec", "none"),
            acodec=f.get("acodec", "none"),
            filesize=f.get("filesize") or f.get("filesize_approx"),
            note=f.get("format_note") or "",
        )
        for f in info.get("formats", [])
    ]
    formats.reverse()

    return VideoInfo(
        title=info.get("title", "Untitled"),
        uploader=info.get("uploader") or "",
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
    """Download `url` with selector `fmt` into `outdir`.

    When `extract_audio` is set, transcode to `audio_codec` at best quality.
    """
    opts = {
        **_BASE_OPTS,
        "format": fmt,
        "outtmpl": f"{outdir}/%(title)s.%(ext)s",
        "progress_hooks": [progress_hook],
        "noplaylist": True,
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
                "preferredquality": "0",
            }
        ]
    else:
        opts["merge_output_format"] = "mp4"

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
