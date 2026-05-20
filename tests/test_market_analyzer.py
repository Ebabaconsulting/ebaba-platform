from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ebaba.tools.market_analyzer import (
    app,
    build_report,
    classify_items,
    clean_lines,
    load_sections_config,
)
from ebaba.schemas.market_report import TrendItem


RAW = """
Inflation eased to 2.4% supporting consumer demand recovery.
Sponsored: subscribe to our newsletter.
Talent shortage in compliance roles is driving wage inflation.
Stripe acquired a Brazilian payments startup, expanding market share.
GenAI fraud risk is rising as deepfake attacks accelerate.
The EU AI Act compliance deadline tightens obligations.
Volatility in bond markets is creating treasury exposure.
"""


def test_clean_lines_drops_boilerplate_and_short_lines():
    cleaned = clean_lines(RAW.splitlines())
    assert all("subscribe" not in c.lower() for c in cleaned)
    assert all(len(c) >= 12 for c in cleaned)
    # Dedup is implicit via lowercase set
    assert len(cleaned) == len(set(c.lower() for c in cleaned))


def test_classify_items_routes_to_expected_sections():
    config = load_sections_config()
    items = [
        TrendItem(headline="Talent shortage in compliance roles"),
        TrendItem(headline="Stripe acquired a Brazilian payments startup"),
        TrendItem(headline="EU AI Act compliance deadline tightens obligations"),
        TrendItem(headline="GenAI fraud risk is rising"),
    ]
    buckets = classify_items(items, config)
    assert any(i.headline.startswith("Talent") for i in buckets["macro_drivers"])
    assert any("acquired" in i.headline for i in buckets["competitive_moves"])
    assert any("EU AI Act" in i.headline for i in buckets["regulatory"])
    assert any("GenAI" in i.headline for i in buckets["technology"])


def test_build_report_produces_all_sections_in_order():
    config = load_sections_config()
    items = [TrendItem(headline=h) for h in clean_lines(RAW.splitlines())]
    report = build_report(industry="fintech", items=items, section_config=config)
    assert [s.key for s in report.sections] == [s["key"] for s in config]
    assert report.industry == "fintech"
    assert report.executive_summary  # non-empty


def test_cli_writes_markdown_with_required_headings(tmp_path: Path):
    feed = tmp_path / "feed.txt"
    feed.write_text(RAW, encoding="utf-8")
    out = tmp_path / "fintech.md"

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--input", str(feed), "--industry", "fintech", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output

    md = out.read_text(encoding="utf-8")
    for heading in (
        "Executive Market Brief",
        "## Executive Summary",
        "## Macro Drivers",
        "## Competitive Landscape",
        "## Technology & Innovation",
        "## Regulatory & Policy",
        "## Appendix",
    ):
        assert heading in md, f"missing heading: {heading}"
