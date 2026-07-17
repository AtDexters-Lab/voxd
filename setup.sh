#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_DIR/.venv"

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -e "$REPO_DIR"
"$VENV/bin/voxd" --setup

if ! command -v ydotool >/dev/null 2>&1 || ! command -v ydotoold >/dev/null 2>&1; then
  echo "ydotool or ydotoold is missing. Install both before starting VOXD." >&2
fi

echo "Start VOXD: $VENV/bin/voxd --tray"
echo "Bind your desktop shortcut to: $VENV/bin/voxd --trigger-record"
