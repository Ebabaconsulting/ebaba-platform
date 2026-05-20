"""Safe filesystem I/O primitives for the ebaba toolkit.

All write operations are atomic: content is written to a temporary file in
the destination directory and then renamed into place, so a crash mid-write
will never leave a half-written executive artefact on disk.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any


class IOError_(Exception):
    """Raised for any toolkit I/O failure (kept distinct from builtin OSError)."""


def resolve_path(path: str | Path) -> Path:
    """Resolve a user-supplied path to an absolute Path, expanding ~ and env vars."""
    return Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()


def read_text(path: str | Path, encoding: str = "utf-8") -> str:
    """Read a UTF-8 text file."""
    p = resolve_path(path)
    if not p.exists():
        raise IOError_(f"Input file not found: {p}")
    if not p.is_file():
        raise IOError_(f"Input path is not a file: {p}")
    return p.read_text(encoding=encoding)


def read_json(path: str | Path) -> Any:
    """Read and parse a JSON file."""
    raw = read_text(path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IOError_(f"Invalid JSON in {path}: {exc}") from exc


def read_csv(path: str | Path) -> list[dict[str, str]]:
    """Read a CSV file as a list of row dicts."""
    raw = read_text(path)
    reader = csv.DictReader(StringIO(raw))
    return [dict(row) for row in reader]


def _atomic_write(path: Path, payload: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        # Best-effort cleanup of the temp file
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_json(path: str | Path, data: Any, *, indent: int = 2) -> Path:
    """Atomically write a JSON document with stable key ordering."""
    p = resolve_path(path)
    payload = json.dumps(data, indent=indent, ensure_ascii=False, sort_keys=False)
    if not payload.endswith("\n"):
        payload += "\n"
    _atomic_write(p, payload)
    return p


def write_markdown(path: str | Path, markdown: str) -> Path:
    """Atomically write a Markdown document."""
    p = resolve_path(path)
    payload = markdown if markdown.endswith("\n") else markdown + "\n"
    _atomic_write(p, payload)
    return p


def detect_format(path: str | Path) -> str:
    """Return a normalized format token based on file extension."""
    suffix = Path(str(path)).suffix.lower().lstrip(".")
    return {
        "json": "json",
        "csv": "csv",
        "md": "markdown",
        "markdown": "markdown",
        "txt": "text",
    }.get(suffix, "text")
