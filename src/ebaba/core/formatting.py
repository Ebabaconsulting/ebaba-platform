"""Formatting helpers: slugs, markdown blocks, JSON canonicalization."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Iterable


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str, max_len: int = 60) -> str:
    """Convert an arbitrary string into a filesystem-safe slug."""
    if not value:
        return "untitled"
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_RE.sub("-", ascii_only).strip("-")
    return (slug or "untitled")[:max_len]


def today_stamp() -> str:
    """Return today's date as YYYYMMDD."""
    return date.today().strftime("%Y%m%d")


def iso_now() -> str:
    """Return the current UTC time as ISO-8601 (seconds precision)."""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def canonical_json(data: Any, *, indent: int = 2) -> str:
    """Render JSON with deterministic, executive-readable formatting."""
    return json.dumps(data, indent=indent, ensure_ascii=False, sort_keys=False)


def markdown_bullets(items: Iterable[str]) -> str:
    """Render an iterable of strings as a markdown bullet list."""
    cleaned = [str(i).strip() for i in items if str(i).strip()]
    if not cleaned:
        return "_None reported._"
    return "\n".join(f"- {item}" for item in cleaned)


def markdown_section(title: str, body: str, level: int = 2) -> str:
    """Wrap a body of text in a Markdown heading."""
    prefix = "#" * max(1, min(level, 6))
    return f"{prefix} {title}\n\n{body.strip()}\n"
