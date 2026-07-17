from __future__ import annotations

import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from voxd.core.config import AppConfig, CONFIG_PATH


def _run(command: list[str], *, timeout: int = 15) -> bool:
    try:
        result = subprocess.run(command, check=False, timeout=timeout)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _install_user_ydotool_unit() -> bool:
    if Path("/usr/lib/systemd/user/ydotoold.service").exists():
        return True

    daemon = shutil.which("ydotoold")
    if not daemon:
        return False

    unit_dir = Path.home() / ".config/systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    command = daemon
    if Path(daemon).name == "ydotoold":
        command += " --socket-path=%h/.ydotool_socket --socket-own=%U:%G"
    (unit_dir / "ydotoold.service").write_text(
        "[Unit]\n"
        "Description=ydotool user daemon\n"
        "After=default.target\n\n"
        "[Service]\n"
        f"ExecStart={command}\n"
        "Restart=on-failure\n"
        "RestartSec=1s\n\n"
        "[Install]\n"
        "WantedBy=default.target\n",
        encoding="utf-8",
    )
    return True


def _install_desktop_entry() -> None:
    icon_dir = Path.home() / ".local/share/icons/hicolor/256x256/apps"
    icon_dir.mkdir(parents=True, exist_ok=True)
    try:
        icon = files("voxd").joinpath("assets", "voxd-1.png").read_bytes()
        (icon_dir / "voxd.png").write_bytes(icon)
    except (FileNotFoundError, OSError):
        pass

    apps_dir = Path.home() / ".local/share/applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    argv0 = Path(sys.argv[0])
    if argv0.name == "voxd" and argv0.exists():
        command = str(argv0.resolve())
    else:
        command = shutil.which("voxd") or "voxd"
    (apps_dir / "voxd-tray.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=VOXD\n"
        "Comment=E4B voice typing\n"
        f"Exec={command} --tray\n"
        "Icon=voxd\n"
        "Terminal=false\n"
        "Categories=Utility;AudioVideo;\n",
        encoding="utf-8",
    )


def run_user_setup(verbose: bool = False) -> None:
    """Create the small per-user runtime surface; never download ASR models."""
    cfg = AppConfig()
    cfg.save()
    os.environ.setdefault("YDOTOOL_SOCKET", str(Path.home() / ".ydotool_socket"))

    unit_available = _install_user_ydotool_unit()
    daemon_started = False
    if unit_available and shutil.which("systemctl"):
        _run(["systemctl", "--user", "daemon-reload"])
        daemon_started = _run(
            ["systemctl", "--user", "enable", "--now", "ydotoold.service"]
        )

    _install_desktop_entry()

    client = shutil.which("ydotool")
    print(f"[setup] config: {CONFIG_PATH}")
    print(f"[setup] ydotool: {client or 'missing'}")
    print(f"[setup] ydotoold: {'running' if daemon_started else 'not running'}")
    if not client or not unit_available:
        print("[setup] Install ydotool, then run: systemctl --user enable --now ydotoold.service")
    if verbose:
        print(f"[setup] E4B endpoint: {cfg.gemma_server_url}")
