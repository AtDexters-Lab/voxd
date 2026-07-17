from __future__ import annotations

import os
import shutil
import subprocess

import pyperclip

from voxd.utils.libw import verbo


class ClipboardError(RuntimeError):
    pass


class ClipboardManager:
    """Keep a best-effort recovery copy; never use paste for insertion."""

    def __init__(self, backend: str | None = None):
        self.backend = (backend or "auto").lower()
        if self.backend == "auto":
            self.backend = self._detect_backend()
        verbo(f"[clipboard] Using backend: {self.backend}")

    @staticmethod
    def _detect_backend() -> str:
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
            return "wl-copy"
        for command in ("xclip", "xsel", "wl-copy"):
            if shutil.which(command):
                return command
        return "pyperclip"

    def copy(self, text: str) -> None:
        if not text.strip():
            raise ClipboardError("cannot copy an empty transcript")

        if self.backend == "pyperclip":
            try:
                pyperclip.copy(text)
            except pyperclip.PyperclipException as exc:
                raise ClipboardError(str(exc)) from exc
            return

        commands = {
            "xclip": ["xclip", "-selection", "clipboard"],
            "xsel": ["xsel", "-i"],
            "wl-copy": ["wl-copy"],
        }
        command = commands.get(self.backend)
        if command is None:
            raise ClipboardError(f"unsupported clipboard backend: {self.backend}")
        try:
            subprocess.run(
                command,
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ClipboardError(f"{self.backend} failed: {exc}") from exc
