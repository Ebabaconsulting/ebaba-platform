"""Executive-grade structured logging built on `rich`."""

from __future__ import annotations

import logging
import os

from rich.console import Console
from rich.logging import RichHandler

_CONSOLE = Console(stderr=False, highlight=False)


def get_logger(name: str = "ebaba") -> logging.Logger:
    """Return a configured logger; safe to call multiple times."""
    level_name = os.getenv("EBABA_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = RichHandler(
            console=_CONSOLE,
            show_time=False,
            show_path=False,
            markup=True,
            rich_tracebacks=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(level)
    return logger


def executive_ok(message: str) -> None:
    """Print a single-line executive success confirmation."""
    _CONSOLE.print(f"[bold green]\\[OK][/bold green] {message}")


def executive_warn(message: str) -> None:
    _CONSOLE.print(f"[bold yellow]\\[WARN][/bold yellow] {message}")


def executive_fail(message: str) -> None:
    _CONSOLE.print(f"[bold red]\\[FAIL][/bold red] {message}")
