from __future__ import annotations

import os
import sys


RED = "\033[31m"
RESET = "\033[0m"


def _color_enabled() -> bool:
    return bool(sys.stdout.isatty() and os.getenv("NO_COLOR") is None)


def verbo(message: str, *args, **kwargs) -> None:
    from voxd.core.config import get_config

    if get_config().verbosity:
        print(message.format(*args, **kwargs), flush=True)


def verr(message: str, *args, **kwargs) -> None:
    rendered = message.format(*args, **kwargs)
    if _color_enabled():
        rendered = f"{RED}{rendered}{RESET}"
    print(rendered, flush=True)
