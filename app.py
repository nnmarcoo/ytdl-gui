"""PySide6 GUI for yt-dlp: search or paste a URL, browse, and download.

All network work runs on QThreadPool workers so the UI stays responsive.
"""

from __future__ import annotations

import os
import sys
import traceback
import urllib.request

from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import engine

CARD_THUMB = QSize(124, 70)
HERO_THUMB = QSize(220, 124)
USER_AGENT = "Mozilla/5.0"
THUMB_TIMEOUT = 10
AUDIO_FORMATS = (
    ("MP3", "mp3"),
    ("M4A", "m4a"),
    ("Opus", "opus"),
    ("FLAC", "flac"),
    ("WAV", "wav"),
    ("Original (no re-encode)", None),
)


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(dict)


class Worker(QRunnable):
    """Runs `fn(progress_emit)` off the UI thread, emitting its result or error."""

    def __init__(self, fn):
        super().__init__()
        self._fn = fn
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.finished.emit(self._fn(self.signals.progress.emit))
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc) or traceback.format_exc())


class _ThumbSignals(QObject):
    loaded = Signal(str, object)


class ThumbnailLoader(QRunnable):
    def __init__(self, url: str, signals: _ThumbSignals):
        super().__init__()
        self.url = url
        self.signals = signals

    def run(self):
        data = None
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=THUMB_TIMEOUT) as resp:
                data = resp.read()
        except Exception:  # noqa: BLE001
            data = None
        self.signals.loaded.emit(self.url, data)


class ThumbnailManager(QObject):
    """Fetches each image once, caches the QPixmap, and fans out to callers."""

    def __init__(self, pool: QThreadPool):
        super().__init__()
        self.pool = pool
        self._cache: dict[str, QPixmap] = {}
        self._pending: dict[str, list] = {}
        self._signals = _ThumbSignals()
        self._signals.loaded.connect(self._on_loaded)

    def get(self, url: str, callback):
        if not url:
            return
        if url in self._cache:
            callback(self._cache[url])
            return
        if url in self._pending:
            self._pending[url].append(callback)
            return
        self._pending[url] = [callback]
        self.pool.start(ThumbnailLoader(url, self._signals))

    def _on_loaded(self, url: str, data):
        callbacks = self._pending.pop(url, [])
        if not data:
            return
        pix = QPixmap()
        if not pix.loadFromData(data):
            return
        self._cache[url] = pix
        for cb in callbacks:
            cb(pix)


def _cover_scaled(pix: QPixmap, size: QSize) -> QPixmap:
    scaled = pix.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (scaled.width() - size.width()) // 2)
    y = max(0, (scaled.height() - size.height()) // 2)
    return scaled.copy(x, y, size.width(), size.height())


def _join(*parts: str) -> str:
    return "   ·   ".join(p for p in parts if p)


class ResultCard(QFrame):
    """A clickable search result: thumbnail, title, uploader and duration."""

    clicked = Signal(str)

    def __init__(self, result: engine.SearchResult, thumbs: ThumbnailManager):
        super().__init__()
        self.url = result.url
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(12)

        self.thumb = QLabel("🎬")
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(CARD_THUMB)
        self.thumb.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.thumb)

        info = QVBoxLayout()
        info.setSpacing(3)
        title = QLabel(result.title)
        title.setObjectName("cardTitle")
        title.setWordWrap(True)
        sub = QLabel(_join(result.uploader, result.duration_str))
        sub.setObjectName("cardSub")
        info.addWidget(title)
        info.addWidget(sub)
        info.addStretch()
        lay.addLayout(info, 1)

        if result.thumbnail:
            thumbs.get(result.thumbnail, self._set_thumb)

    def _set_thumb(self, pix: QPixmap):
        self.thumb.setText("")
        self.thumb.setPixmap(_cover_scaled(pix, CARD_THUMB))

    def mousePressEvent(self, event):  # noqa: N802
        self.clicked.emit(self.url)
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ytdl-gui")
        self.resize(940, 680)
        self.setMinimumSize(720, 520)

        self.pool = QThreadPool()
        self.thumbs = ThumbnailManager(self.pool)
        self.current_url: str | None = None
        self.formats: list[engine.Format] = []
        self.outdir = os.path.expanduser("~/Downloads")

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)
        root.addLayout(self._build_search_bar())
        root.addLayout(self._build_content(), 1)
        root.addWidget(self._build_actions())

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.status("Search for a title, or paste a link to begin.")
        self.set_busy(False)

    def _build_search_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.url_input = QLineEdit()
        self.url_input.setObjectName("search")
        self.url_input.setPlaceholderText("Search a title, or paste a URL…")
        self.url_input.returnPressed.connect(self.on_query)
        self.source_combo = QComboBox()
        self.source_combo.addItems(list(engine.SEARCH_PREFIXES))
        self.source_combo.setToolTip("Where to search when you type a title")
        self.query_btn = QPushButton("Go")
        self.query_btn.clicked.connect(self.on_query)
        bar.addWidget(self.url_input, 1)
        bar.addWidget(self.source_combo)
        bar.addWidget(self.query_btn)
        return bar

    def _build_content(self) -> QVBoxLayout:
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(12)

        self.placeholder = QLabel(
            "Search for a song or video above,\nor paste a link to get started."
        )
        self.placeholder.setObjectName("placeholder")
        self.placeholder.setAlignment(Qt.AlignCenter)
        content.addWidget(self.placeholder, 1)

        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        results_container = QWidget()
        self.results_layout = QVBoxLayout(results_container)
        self.results_layout.setContentsMargins(0, 0, 6, 0)
        self.results_layout.setSpacing(8)
        self.results_layout.addStretch()
        self.results_scroll.setWidget(results_container)
        self.results_scroll.hide()
        content.addWidget(self.results_scroll, 1)

        self.detail = QWidget()
        detail_row = QHBoxLayout(self.detail)
        detail_row.setContentsMargins(0, 0, 0, 0)
        detail_row.setSpacing(14)
        self.hero = QLabel()
        self.hero.setObjectName("hero")
        self.hero.setFixedSize(HERO_THUMB)
        self.hero.setAlignment(Qt.AlignCenter)
        detail_row.addWidget(self.hero, 0, Qt.AlignTop)
        meta_col = QVBoxLayout()
        meta_col.setSpacing(4)
        self.meta_title = QLabel("")
        self.meta_title.setObjectName("metaTitle")
        self.meta_title.setWordWrap(True)
        self.meta_sub = QLabel("")
        self.meta_sub.setObjectName("metaSub")
        meta_col.addWidget(self.meta_title)
        meta_col.addWidget(self.meta_sub)
        meta_col.addStretch()
        detail_row.addLayout(meta_col, 1)
        self.detail.hide()
        content.addWidget(self.detail)

        self.formats_label = QLabel("Formats")
        self.formats_label.setObjectName("sectionLabel")
        self.formats_label.hide()
        content.addWidget(self.formats_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Type", "Resolution", "Ext", "Size", "Note"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.hide()
        content.addWidget(self.table, 1)
        return content

    def _build_actions(self) -> QWidget:
        self.actions = QWidget()
        col = QVBoxLayout(self.actions)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        dir_row.addWidget(QLabel("Save to:"))
        self.dir_label = QLabel(self.outdir)
        self.dir_btn = QPushButton("Choose…")
        self.dir_btn.setObjectName("secondary")
        self.dir_btn.clicked.connect(self.on_choose_dir)
        dir_row.addWidget(self.dir_label, 1)
        dir_row.addWidget(self.dir_btn)
        col.addLayout(dir_row)

        dl_row = QHBoxLayout()
        dl_row.setSpacing(8)
        self.video_btn = QPushButton("🎬  Best video")
        self.video_btn.setToolTip("Highest-quality video + audio, merged to mp4")
        self.video_btn.clicked.connect(
            lambda: self.start_download("bestvideo+bestaudio/best")
        )
        self.audio_btn = QPushButton("🎵  Best audio")
        self.audio_btn.setToolTip("Highest-quality audio in the chosen format")
        self.audio_btn.clicked.connect(self.on_download_audio)
        self.audio_format = QComboBox()
        self.audio_format.setToolTip("Audio format for the Best audio button")
        for label, codec in AUDIO_FORMATS:
            self.audio_format.addItem(label, codec)
        self.selected_btn = QPushButton("Download selected")
        self.selected_btn.setObjectName("secondary")
        self.selected_btn.clicked.connect(self.on_download_selected)
        dl_row.addWidget(self.video_btn)
        dl_row.addWidget(self.audio_btn)
        dl_row.addWidget(self.audio_format)
        dl_row.addWidget(self.selected_btn)
        dl_row.addStretch()
        col.addLayout(dl_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        col.addWidget(self.progress)

        self.actions.hide()
        return self.actions

    def set_busy(self, busy: bool):
        for w in (
            self.query_btn,
            self.video_btn,
            self.audio_btn,
            self.selected_btn,
            self.url_input,
        ):
            w.setEnabled(not busy)

    def status(self, msg: str):
        self.statusBar().showMessage(msg)

    def _run(self, fn, on_done, on_progress=None) -> None:
        worker = Worker(fn)
        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(self.on_error)
        if on_progress is not None:
            worker.signals.progress.connect(on_progress)
        self.pool.start(worker)

    def _clear_results(self):
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_results_mode(self):
        self.placeholder.hide()
        self.detail.hide()
        self.formats_label.hide()
        self.table.hide()
        self.actions.hide()
        self.results_scroll.show()

    def _show_detail_mode(self):
        self.placeholder.hide()
        self.results_scroll.hide()
        self.detail.show()
        self.formats_label.show()
        self.table.show()
        self.actions.show()

    def on_query(self):
        text = self.url_input.text().strip()
        if not text:
            return
        if engine.looks_like_url(text):
            self.start_query(text)
        else:
            self.start_search(text)

    def start_search(self, text: str):
        source = self.source_combo.currentText()
        self.set_busy(True)
        self.status(f"Searching {source} for “{text}”…")
        self._clear_results()
        self._show_results_mode()
        self._run(lambda _p: engine.search(text, source), self.on_search_done)

    def on_search_done(self, results: list):
        self.set_busy(False)
        if not results:
            self.status("No results found.")
            return
        for r in results:
            card = ResultCard(r, self.thumbs)
            card.clicked.connect(self.on_result_chosen)
            self.results_layout.insertWidget(self.results_layout.count() - 1, card)
        self.status(f"{len(results)} results — click one to load formats")

    def on_result_chosen(self, url: str):
        if url:
            self.start_query(url)

    def start_query(self, url: str):
        self.current_url = url
        self.set_busy(True)
        self.status("Loading formats…")
        self.table.setRowCount(0)
        self._run(lambda _p: engine.query(url), self.on_query_done)

    def on_query_done(self, info: engine.VideoInfo):
        self.set_busy(False)
        self._show_detail_mode()
        self.formats = info.formats

        self.meta_title.setText(info.title)
        self.meta_sub.setText(_join(info.uploader, info.duration_str))
        self.hero.setText("🎬")
        if info.thumbnail:
            self.thumbs.get(info.thumbnail, self._set_hero)

        self.table.setRowCount(len(info.formats))
        for row, f in enumerate(info.formats):
            cells = (f.format_id, f.kind, f.resolution, f.ext, f.filesize_str, f.note)
            for col, text in enumerate(cells):
                self.table.setItem(row, col, QTableWidgetItem(str(text)))
        self.status(f"{len(info.formats)} formats — pick one or use Best video / Best audio")

    def _set_hero(self, pix: QPixmap):
        self.hero.setText("")
        self.hero.setPixmap(_cover_scaled(pix, HERO_THUMB))

    def on_choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose download folder", self.outdir)
        if d:
            self.outdir = d
            self.dir_label.setText(d)

    def on_download_selected(self):
        row = self.table.currentRow()
        if row < 0:
            self.status("Select a format row first, or use Best video / Best audio.")
            return
        fmt = self.formats[row].format_id
        if self.formats[row].kind == "video only":
            fmt = f"{fmt}+bestaudio/best"
        self.start_download(fmt)

    def on_download_audio(self):
        codec = self.audio_format.currentData()
        if codec is None:
            self.start_download("bestaudio/best")
        else:
            self.start_download("bestaudio/best", extract_audio=True, audio_codec=codec)

    def start_download(self, fmt: str, extract_audio: bool = False, audio_codec: str = "mp3"):
        if not self.current_url:
            self.status("Load a video first.")
            return
        url, outdir = self.current_url, self.outdir
        self.set_busy(True)
        self.progress.setValue(0)
        self.status(f"Downloading audio ({audio_codec})…" if extract_audio else "Downloading…")
        self._run(
            lambda progress: engine.download(
                url,
                fmt,
                outdir,
                progress_hook=progress,
                postprocessor_hook=progress,
                extract_audio=extract_audio,
                audio_codec=audio_codec,
            ),
            self.on_download_done,
            self.on_progress,
        )

    def on_progress(self, d: dict):
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                self.progress.setValue(int(d.get("downloaded_bytes", 0) / total * 100))
            parts = []
            if d.get("speed"):
                parts.append(f"{d['speed'] / 1_000_000:.1f} MB/s")
            if d.get("eta"):
                parts.append(f"ETA {int(d['eta'])}s")
            self.status("Downloading…  " + "   ".join(parts))
        elif status == "finished":
            self.progress.setValue(100)
            self.status("Post-processing (merging / converting)…")

    def on_download_done(self, _):
        self.set_busy(False)
        self.progress.setValue(100)
        self.status(f"✓ Done — saved to {self.outdir}")

    def on_error(self, msg: str):
        self.set_busy(False)
        self.status(f"Error: {msg}")

    def closeEvent(self, event):  # noqa: N802
        self.pool.clear()
        self.pool.waitForDone(2000)
        super().closeEvent(event)


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def load_stylesheet() -> str:
    try:
        with open(resource_path("style.qss"), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def configure_ffmpeg():
    """Point yt-dlp at a bundled ffmpeg, if one shipped with the binary."""
    exe = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
    for base in (getattr(sys, "_MEIPASS", None), os.path.dirname(sys.executable)):
        if base and os.path.exists(os.path.join(base, exe)):
            engine.FFMPEG_LOCATION = base
            return


def main():
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "xdgdesktopportal")

    configure_ffmpeg()
    app = QApplication(sys.argv)
    app.setStyleSheet(load_stylesheet())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
