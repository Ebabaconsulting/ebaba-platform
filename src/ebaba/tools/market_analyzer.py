"""Tool #2 — market_analyzer.

Parse and clean raw industry trend material (txt / md / json / csv) into a
structured `MarketReport` and render it as an executive Markdown brief via
the bundled Jinja2 template.

Usage:
    python -m ebaba.tools.market_analyzer --input data/market_feeds/fintech.txt --industry fintech
    python -m ebaba.tools.market_analyzer --input data/market_feeds/feed.json --industry retail --output outputs/market_reports/retail.md
"""

from __future__ import annotations

import json
import re
import sys
from importlib import resources
from pathlib import Path
from typing import Any, Optional

import typer
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from ebaba.core import io as eio
from ebaba.core.formatting import today_stamp
from ebaba.core.logging import executive_fail, executive_ok, get_logger
from ebaba.core.validation import validate
from ebaba.schemas.market_report import MarketReport, ReportSection, TrendItem


app = typer.Typer(
    add_completion=False,
    help="ebabaConsulting — Market Analyzer. Cleans industry trends into executive Markdown reports.",
)
log = get_logger("ebaba.market_analyzer")


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------

def load_sections_config(path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Load the section configuration JSON (defaults to bundled sections.json)."""
    if path is None:
        path = _TEMPLATES_DIR / "sections.json"
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError(f"Invalid section configuration at {path}")
    return sections


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

_BOILERPLATE_PREFIXES = (
    "subscribe",
    "advertisement",
    "ad ·",
    "sponsored",
    "©",
    "copyright",
    "all rights reserved",
)

_WHITESPACE_RE = re.compile(r"\s+")


def clean_lines(raw_lines: list[str], *, min_length: int = 12) -> list[str]:
    """Strip boilerplate, normalize whitespace, dedupe, and drop low-signal lines."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for line in raw_lines:
        text = _WHITESPACE_RE.sub(" ", line).strip(" \t-•*·")
        if not text or len(text) < min_length:
            continue
        lowered = text.lower()
        if any(lowered.startswith(p) for p in _BOILERPLATE_PREFIXES):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(text)
    return cleaned


# ---------------------------------------------------------------------------
# Loading raw feed into TrendItem candidates
# ---------------------------------------------------------------------------

def _items_from_text(raw: str) -> list[TrendItem]:
    lines = clean_lines(raw.splitlines())
    return [TrendItem(headline=line) for line in lines]


def _items_from_json(raw: Any) -> list[TrendItem]:
    if isinstance(raw, dict) and "items" in raw:
        raw = raw["items"]
    if not isinstance(raw, list):
        raise ValueError("JSON market feed must be a list (or {'items': [...]}).")
    items: list[TrendItem] = []
    for entry in raw:
        if isinstance(entry, str):
            items.append(TrendItem(headline=entry.strip()))
        elif isinstance(entry, dict):
            headline = str(entry.get("headline") or entry.get("title") or "").strip()
            if not headline:
                continue
            items.append(
                TrendItem(
                    headline=headline,
                    detail=(entry.get("detail") or entry.get("summary") or None),
                    source=entry.get("source"),
                    weight=float(entry.get("weight", 1.0)),
                )
            )
    # Final clean pass on headlines
    cleaned_headlines = clean_lines([i.headline for i in items])
    allowed = {h.lower() for h in cleaned_headlines}
    return [i for i in items if i.headline.lower() in allowed]


def _items_from_csv(rows: list[dict[str, str]]) -> list[TrendItem]:
    items: list[TrendItem] = []
    for row in rows:
        headline = (row.get("headline") or row.get("title") or "").strip()
        if not headline:
            continue
        try:
            weight = float(row.get("weight", "1.0"))
        except ValueError:
            weight = 1.0
        items.append(
            TrendItem(
                headline=headline,
                detail=row.get("detail") or row.get("summary") or None,
                source=row.get("source") or None,
                weight=weight,
            )
        )
    return items


def load_feed(path: Path) -> list[TrendItem]:
    fmt = eio.detect_format(path)
    if fmt == "json":
        return _items_from_json(eio.read_json(path))
    if fmt == "csv":
        return _items_from_csv(eio.read_csv(path))
    return _items_from_text(eio.read_text(path))


# ---------------------------------------------------------------------------
# Classification + ranking
# ---------------------------------------------------------------------------

def _compile_section_patterns(
    section_config: list[dict[str, Any]],
) -> list[tuple[str, re.Pattern[str]]]:
    """Compile each section's keywords into a single word-boundary regex.

    Word boundaries prevent short keywords (e.g. "ai") from matching inside
    unrelated words (e.g. "Brazilian"), while still allowing partial-stem
    matches like "regulat" or "acquir" through `re.escape` + optional suffix.
    """
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for section in section_config:
        keywords = section.get("keywords", [])
        if not keywords:
            continue
        alternation = "|".join(re.escape(kw.lower()) for kw in keywords)
        pattern = re.compile(rf"\b(?:{alternation})", flags=re.IGNORECASE)
        compiled.append((section["key"], pattern))
    return compiled


def classify_items(
    items: list[TrendItem],
    section_config: list[dict[str, Any]],
) -> dict[str, list[TrendItem]]:
    """Assign each TrendItem to the first section whose keywords match.

    Items that match no section are dropped from the structured report
    (they remain in the raw input). This keeps the executive brief tight.
    """
    buckets: dict[str, list[TrendItem]] = {s["key"]: [] for s in section_config}
    patterns = _compile_section_patterns(section_config)
    for item in items:
        haystack = f"{item.headline} {item.detail or ''}".lower()
        for key, pattern in patterns:
            if pattern.search(haystack):
                buckets[key].append(item)
                break
    return buckets


def rank_items(items: list[TrendItem]) -> list[TrendItem]:
    """Stable sort: descending weight, then headline alpha for determinism."""
    return sorted(items, key=lambda i: (-i.weight, i.headline.lower()))


# ---------------------------------------------------------------------------
# Executive summary
# ---------------------------------------------------------------------------

def build_executive_summary(
    industry: str,
    buckets: dict[str, list[TrendItem]],
    section_config: list[dict[str, Any]],
) -> str:
    populated = [s for s in section_config if buckets.get(s["key"])]
    if not populated:
        return (
            f"No material signals were extracted from the {industry} feed. "
            "Recommend broadening source coverage before drawing conclusions."
        )

    counts = ", ".join(f"{len(buckets[s['key']])} in {s['title']}" for s in populated)
    top_signal = ""
    for section in populated:
        ranked = rank_items(buckets[section["key"]])
        if ranked:
            top_signal = f"Leading signal: \"{ranked[0].headline}\" ({section['title']})."
            break

    return (
        f"Synthesis of the latest {industry} market signals across "
        f"{len(populated)} executive dimensions ({counts}). {top_signal} "
        "Detailed implications follow."
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(report: MarketReport, *, template_name: str = "market_report.md.j2") -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_name)
    # NOTE: pass dicts but resolve `items` via bracket-syntax in the template,
    # since `dict.items` collides with Jinja's attribute resolution.
    return template.render(
        industry=report.industry,
        date=report.date,
        executive_summary=report.executive_summary,
        sections=[s.model_dump() for s in report.sections],
        sources=report.sources,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_report(
    *,
    industry: str,
    items: list[TrendItem],
    section_config: list[dict[str, Any]],
) -> MarketReport:
    buckets = classify_items(items, section_config)
    sections = [
        ReportSection(
            key=s["key"],
            title=s["title"],
            items=rank_items(buckets.get(s["key"], [])),
        )
        for s in section_config
    ]
    sources = sorted({i.source for i in items if i.source})
    summary = build_executive_summary(industry, buckets, section_config)
    report_dict = {
        "industry": industry,
        "date": today_stamp(),
        "executive_summary": summary,
        "sections": [s.model_dump() for s in sections],
        "sources": sources,
    }
    return validate(MarketReport, report_dict)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

@app.command()
def main(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        help="Raw market feed file (.txt | .md | .json | .csv).",
    ),
    industry: str = typer.Option(
        ...,
        "--industry",
        help="Industry tag (e.g. fintech, industrial-manufacturing).",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Destination markdown path. Defaults to outputs/market_reports/<industry>-<YYYYMMDD>.md",
    ),
    template: str = typer.Option(
        "market_report.md.j2",
        "--template",
        help="Jinja2 template filename within the templates/ directory.",
    ),
    sections_config: Optional[Path] = typer.Option(
        None,
        "--sections-config",
        help="Override the bundled sections.json configuration.",
    ),
) -> None:
    """Generate an executive Markdown market brief from a raw industry feed."""
    try:
        section_config = load_sections_config(sections_config)
        items = load_feed(input)
        report = build_report(
            industry=industry,
            items=items,
            section_config=section_config,
        )
        markdown = render_markdown(report, template_name=template)
    except eio.IOError_ as exc:
        executive_fail(str(exc))
        raise typer.Exit(code=3) from exc
    except (ValueError, FileNotFoundError) as exc:
        executive_fail(str(exc))
        raise typer.Exit(code=2) from exc

    out_path = output or Path("outputs/market_reports") / f"{industry}-{today_stamp()}.md"
    try:
        written = eio.write_markdown(out_path, markdown)
    except eio.IOError_ as exc:
        executive_fail(str(exc))
        raise typer.Exit(code=3) from exc

    populated = sum(1 for s in report.sections if s.items)
    executive_ok(
        f"MarketReport written -> {written} "
        f"({populated}/{len(report.sections)} sections populated, "
        f"{sum(len(s.items) for s in report.sections)} signals)"
    )


if __name__ == "__main__":
    sys.exit(app())
