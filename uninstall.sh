#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

systemctl --user disable --now voxd-tray.service 2>/dev/null || true

rm -f "$HOME/.config/autostart/voxd-tray.desktop"
rm -f "$HOME/.config/systemd/user/voxd-tray.service"
rm -f "$HOME/.local/share/applications/voxd-tray.desktop"
rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/voxd.png"
rm -rf "$REPO_DIR/.venv"
systemctl --user daemon-reload 2>/dev/null || true

echo "VOXD source install removed. Config and recordings were kept."
