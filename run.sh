#!/usr/bin/env bash
# Launch ytdl-gui, bootstrapping the virtualenv on first run.
set -euo pipefail

# Resolve the directory this script lives in, regardless of where it's called from.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [[ ! -d .venv ]]; then
    echo "First run: creating virtualenv and installing dependencies…"
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
fi

exec .venv/bin/python app.py
