"""Logging helpers providing colourised output for backend components."""
from __future__ import annotations

import logging
import os
import sys
from typing import Final


def _supports_colour(stream: object) -> bool:
    if os.getenv("NO_COLOR") is not None:
        return False
    return hasattr(stream, "isatty") and bool(stream.isatty())


class _ColourFormatter(logging.Formatter):
    """Formatter that injects ANSI colours for log levels."""

    _RESET: Final[str] = "\033[0m"
    _COLOURS: Final[dict[str, str]] = {
        "DEBUG": "\033[36m",  # cyan
        "INFO": "\033[32m",  # green
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",  # red
        "CRITICAL": "\033[35m",  # magenta
    }

    def __init__(self, *, use_colour: bool) -> None:
        super().__init__(fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        self._use_colour = use_colour

    def format(self, record: logging.LogRecord) -> str:
        if not self._use_colour:
            return super().format(record)

        colour = self._COLOURS.get(record.levelname)
        if not colour:
            return super().format(record)

        original_levelname = record.levelname
        record.levelname = f"{colour}{record.levelname}{self._RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


_CONFIGURED = False


def setup_logging() -> None:
    """Apply a colour-aware formatter to the project logger once."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    stream = sys.stderr
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_ColourFormatter(use_colour=_supports_colour(stream)))

    log_level = os.getenv("APP_LOG_LEVEL", "INFO").upper()
    level_value = getattr(logging, log_level, logging.INFO)

    package_logger = logging.getLogger("backend")
    package_logger.setLevel(level_value if isinstance(level_value, int) else logging.INFO)
    package_logger.addHandler(handler)
    package_logger.propagate = False

    _CONFIGURED = True
