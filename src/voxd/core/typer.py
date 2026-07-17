from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from voxd.utils.libw import verbo


_TEXT_CHUNK_CHARS = 400
_KEY_HOLD_MS = 5
_DRAIN_DELAY = 0.05
_RELEASE_ARGS = [
    f"{keycode}:0"
    for keycode in (
        list(range(2, 14))
        + list(range(16, 28))
        + list(range(30, 42))
        + [29, 42, 43]
        + list(range(44, 54))
        + [54, 56, 57, 97, 100, 125, 126]
    )
]


class YdotoolTyper:
    """Emit real Linux input events through ydotool; never paste text."""

    def __init__(self, *, delay=1, start_delay=0.15, cfg=None):
        try:
            self.delay_ms = max(1.0, float(delay))
        except (TypeError, ValueError):
            self.delay_ms = 1.0
        try:
            self.start_delay = max(0.0, float(start_delay))
        except (TypeError, ValueError):
            self.start_delay = 0.15
        self.delay_str = str(int(self.delay_ms))
        self.cfg = cfg
        default_socket = str(Path.home() / ".ydotool_socket")
        self.socket_path = Path(os.environ.setdefault("YDOTOOL_SOCKET", default_socket))
        self.tool = self._find_tool()
        self.supports_key_hold = self._supports_key_hold(self.tool)

    @staticmethod
    def _find_tool() -> str | None:
        candidates = [
            shutil.which("ydotool"),
            "/usr/local/bin/ydotool",
            "/usr/bin/ydotool",
            str(Path.home() / ".local/bin/ydotool"),
            str(Path.home() / ".local/share/voxd/bin/ydotool"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        return None

    @staticmethod
    def _supports_key_hold(tool: str | None) -> bool:
        if not tool:
            return False
        try:
            with open(tool, "rb") as executable:
                return b"key-hold" in executable.read()
        except OSError:
            return False

    def _ensure_daemon(self) -> bool:
        if self._daemon_socket_ready():
            return True
        try:
            subprocess.run(
                ["systemctl", "--user", "start", "ydotoold.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

        for _ in range(10):
            if self._daemon_socket_ready():
                return True
            time.sleep(0.1)
        return False

    def _daemon_socket_ready(self) -> bool:
        if not self.socket_path.exists():
            return False
        # ydotoold uses a Unix datagram socket. A stream probe always fails
        # with a protocol mismatch even while the daemon is healthy.
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            probe.settimeout(0.25)
            probe.connect(str(self.socket_path))
            return True
        except OSError:
            return False
        finally:
            probe.close()

    def type(self, text: str) -> None:
        if not self.tool:
            raise RuntimeError("ydotool is not installed")
        if not self._ensure_daemon():
            raise RuntimeError("ydotoold is not running")

        if self.start_delay:
            time.sleep(self.start_delay)

        rendered = text.rstrip()
        if self.cfg is None or self.cfg.data.get("append_trailing_space", True):
            rendered += " "

        verbo(f"[typer] Typing {len(rendered)} characters with ydotool")
        for chunk in self._split_chunks(rendered):
            self._type_chunk(chunk)

    def _type_chunk(self, text: str) -> None:
        hold_ms = _KEY_HOLD_MS if self.supports_key_hold else 0
        expected_seconds = len(text) * (self.delay_ms + hold_ms) / 1000.0
        timeout = max(5.0, expected_seconds * 2.0 + 3.0)
        if self.supports_key_hold:
            command = [
                self.tool,
                "type",
                "-d",
                self.delay_str,
                "-H",
                str(_KEY_HOLD_MS),
                "-f",
                "-",
            ]
        else:
            command = [
                self.tool,
                "type",
                "--key-delay",
                self.delay_str,
                "--file",
                "-",
            ]
        succeeded = self._run_tool(command, timeout=timeout, input_text=text)
        time.sleep(_DRAIN_DELAY)
        self._release_keys()
        if not succeeded:
            raise RuntimeError("ydotool failed before the complete transcript was typed")

    @staticmethod
    def _split_chunks(text: str, max_chars: int = _TEXT_CHUNK_CHARS):
        if max_chars < 1:
            raise ValueError("max_chars must be positive")

        start = 0
        while len(text) - start > max_chars:
            limit = start + max_chars
            split_at = max(
                text.rfind(" ", start, limit),
                text.rfind("\n", start, limit),
                text.rfind("\t", start, limit),
            )
            if split_at < start + max_chars // 2:
                split_at = limit
            else:
                split_at += 1
            yield text[start:split_at]
            start = split_at
        if start < len(text):
            yield text[start:]

    def _run_tool(
        self, command: list[str], *, timeout: float, input_text: str | None = None
    ) -> bool:
        try:
            result = subprocess.run(
                command,
                input=input_text,
                text=input_text is not None,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def _release_keys(self) -> None:
        if not self.tool:
            return
        try:
            subprocess.run(
                [self.tool, "key", *_RELEASE_ARGS],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
