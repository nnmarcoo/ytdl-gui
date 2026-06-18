# PyInstaller spec — builds a single-file ytdl-gui binary.
# Build with:  pyinstaller --noconfirm ytdl-gui.spec
# Set FFMPEG_BIN=/path/to/ffmpeg(.exe) to bundle ffmpeg into the binary.

import os

from PyInstaller.utils.hooks import collect_all

datas = [("style.qss", ".")]
binaries = []

# Optionally bundle ffmpeg (so "best video" merging and mp3 work out of the box).
ffmpeg_bin = os.environ.get("FFMPEG_BIN")
if ffmpeg_bin and os.path.exists(ffmpeg_bin):
    binaries.append((ffmpeg_bin, "."))

# yt-dlp lazily imports its many extractors; pull them all in.
ydl_datas, ydl_binaries, ydl_hidden = collect_all("yt_dlp")
datas += ydl_datas
binaries += ydl_binaries

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=ydl_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ytdl-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app — no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
