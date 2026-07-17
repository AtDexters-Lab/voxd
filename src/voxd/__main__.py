from __future__ import annotations

import argparse
import importlib.metadata
import os
import shutil
import subprocess
import sys
from pathlib import Path

from voxd.core.config import AppConfig


def _parse_bool(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "on", "yes", "y"}:
        return True
    if normalized in {"0", "false", "off", "no", "n"}:
        return False
    raise ValueError(f"expected true/false, got: {value}")


def _get_version() -> str:
    try:
        return importlib.metadata.version("voxd")
    except importlib.metadata.PackageNotFoundError:
        pyproject = Path(__file__).parents[2] / "pyproject.toml"
        if pyproject.exists():
            for line in pyproject.read_text(encoding="utf-8").splitlines():
                if line.startswith("version = "):
                    return line.split('"', 2)[1]
        return "unknown"


def _systemd_user_available() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except OSError:
        return False


def _voxd_command() -> str:
    argv0 = Path(sys.argv[0])
    if argv0.name == "voxd" and argv0.exists():
        return str(argv0.resolve())
    executable = shutil.which("voxd")
    return executable or f"{sys.executable} -m voxd"


def _ensure_voxd_tray_unit() -> None:
    command = _voxd_command()
    unit_dir = Path.home() / ".config/systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / "voxd-tray.service").write_text(
        "[Unit]\n"
        "Description=VOXD E4B tray\n"
        "After=default.target\n\n"
        "[Service]\n"
        f"ExecStart={command} --tray\n"
        "Restart=on-failure\n"
        "RestartSec=2s\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        "Environment=YDOTOOL_SOCKET=%h/.ydotool_socket\n\n"
        "[Install]\n"
        "WantedBy=default.target\n",
        encoding="utf-8",
    )


def _xdg_autostart_path() -> Path:
    return Path.home() / ".config/autostart/voxd-tray.desktop"


def _set_xdg_autostart(enabled: bool) -> bool:
    path = _xdg_autostart_path()
    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=VOXD\n"
                f"Exec={_voxd_command()} --tray\n"
                "X-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        elif path.exists():
            path.unlink()
        return True
    except OSError:
        return False


def _handle_autostart(value: str) -> int:
    enabled = _parse_bool(value)
    cfg = AppConfig()
    cfg.set("autostart", enabled)
    cfg.save()

    if _systemd_user_available():
        try:
            _ensure_voxd_tray_unit()
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"], check=False
            )
            action = "enable" if enabled else "disable"
            subprocess.run(
                ["systemctl", "--user", action, "--now", "voxd-tray.service"],
                check=False,
            )
            check = "is-enabled" if enabled else "is-active"
            result = subprocess.run(
                ["systemctl", "--user", check, "voxd-tray.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if (enabled and result.returncode == 0) or (not enabled and result.returncode != 0):
                _set_xdg_autostart(False)
                print(f"[autostart] {'enabled' if enabled else 'disabled'}")
                return 0
        except OSError:
            pass

    ok = _set_xdg_autostart(enabled)
    print(f"[autostart] {'enabled' if enabled else 'disabled'} (xdg={ok})")
    return 0 if ok else 1


def _mic_autoset_if_enabled(cfg: AppConfig) -> None:
    if not cfg.mic_autoset_enabled:
        return
    level = max(0.0, min(1.0, float(cfg.mic_autoset_level)))
    commands = []
    if shutil.which("wpctl"):
        commands = [
            ["wpctl", "set-mute", "@DEFAULT_SOURCE@", "0"],
            ["wpctl", "set-volume", "@DEFAULT_SOURCE@", f"{level:.2f}"],
        ]
    elif shutil.which("pactl"):
        percent = f"{round(level * 100)}%"
        commands = [
            ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"],
            ["pactl", "set-source-volume", "@DEFAULT_SOURCE@", percent],
        ]
    for command in commands:
        try:
            subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return


def _diagnose(cfg: AppConfig) -> int:
    import requests

    print(f"E4B endpoint: {cfg.gemma_server_url}")
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.get(f"{cfg.gemma_server_url.rstrip('/')}/v1/models", timeout=5)
        print(f"E4B service: {'ok' if response.ok else f'HTTP {response.status_code}'}")
    except requests.RequestException as exc:
        print(f"E4B service: unavailable ({exc})")

    socket_path = Path(os.environ.get("YDOTOOL_SOCKET", str(Path.home() / ".ydotool_socket")))
    print(f"ydotool: {shutil.which('ydotool') or 'missing'}")
    print(f"ydotool socket: {'ok' if socket_path.exists() else 'missing'} ({socket_path})")

    try:
        import sounddevice as sd

        device = sd.query_devices(kind="input")
        print(f"audio input: {device.get('name')} @ {device.get('default_samplerate')} Hz")
    except Exception as exc:
        print(f"audio input: unavailable ({exc})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="VOXD E4B voice typing")
    parser.add_argument("--tray", action="store_true", help="run the tray service (default)")
    parser.add_argument("--trigger-record", action="store_true", help="toggle recording in the tray")
    parser.add_argument("--setup", action="store_true", help="configure ydotool and desktop integration")
    parser.add_argument("--autostart", metavar="BOOL", help="enable or disable tray autostart")
    parser.add_argument("--diagnose", action="store_true", help="check E4B, ydotool, and audio")
    parser.add_argument("--version", action="store_true", help="print the installed version")
    args = parser.parse_args()

    if args.version:
        print(_get_version())
        return
    if args.trigger_record:
        from voxd.utils.ipc_client import send_trigger

        raise SystemExit(0 if send_trigger() else 1)
    if args.autostart is not None:
        raise SystemExit(_handle_autostart(args.autostart))
    if args.setup:
        from voxd.utils.setup_user import run_user_setup

        run_user_setup()
        return

    cfg = AppConfig()
    if args.diagnose:
        raise SystemExit(_diagnose(cfg))

    _mic_autoset_if_enabled(cfg)
    print("VOXD tray: E4B transcription + ydotool typing", flush=True)
    from voxd.tray.tray_main import main as tray_main

    tray_main()


if __name__ == "__main__":
    main()
