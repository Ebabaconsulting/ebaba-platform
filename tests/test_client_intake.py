from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ebaba.tools.client_intake import (
    _build_profile_dict,
    _flatten_structured,
    app,
    parse_free_text,
)


SAMPLE = """
Company: Acme Industrial Holdings
Industry: Industrial Manufacturing
HQ Country: DE
Regions: EMEA, North America
Revenue: 1-5B
Employees: 1000-5000
Contact name: Helena Vogt
Contact role: Chief Strategy Officer
Email: helena.vogt@acme.example
Engagement type: strategy
Scope: Three-year corporate strategy refresh
Timeline weeks: 16
Budget: 1-5M
Strategic priorities: Portfolio simplification, EBITDA expansion
Pain points: Margin compression, Legacy ERP fragmentation
Success metrics: +300bps EBITDA, 25% SKU reduction
""".strip()


def test_parse_free_text_extracts_fields():
    flat = parse_free_text(SAMPLE)
    assert flat["company_name"] == "Acme Industrial Holdings"
    assert flat["industry"] == "Industrial Manufacturing"
    assert "Portfolio simplification" in flat["strategic_priorities"]
    assert flat["primary_contact_email"] == "helena.vogt@acme.example"


def test_build_profile_dict_enriches_tier_and_practice():
    profile = _build_profile_dict(parse_free_text(SAMPLE), source="test")
    assert profile["company_name"] == "Acme Industrial Holdings"
    assert profile["hq_country"] == "DE"
    assert profile["derived"]["engagement_tier"] == "Tier 1"
    assert profile["derived"]["recommended_practice_area"] == "Strategy"
    assert 0 <= profile["derived"]["priority_score"] <= 100


def test_cli_writes_validated_profile(tmp_path: Path):
    input_path = tmp_path / "acme.txt"
    input_path.write_text(SAMPLE, encoding="utf-8")
    output_path = tmp_path / "acme.json"

    runner = CliRunner()
    result = runner.invoke(app, ["--input", str(input_path), "--output", str(output_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["company_name"] == "Acme Industrial Holdings"
    assert payload["engagement"]["timeline_weeks"] == 16
    assert payload["derived"]["engagement_tier"] in {"Tier 1", "Tier 2", "Tier 3"}


def test_flatten_structured_roundtrip():
    structured = {
        "company_name": "Beta Co",
        "industry": "Retail",
        "hq_country": "FR",
        "primary_contact": {"name": "Anna", "role": "COO"},
        "engagement": {
            "type": "operational-excellence",
            "scope": "Network optimization",
            "timeline_weeks": 10,
            "budget_band_usd": "250K-1M",
        },
        "strategic_priorities": ["Cost-out"],
        "pain_points": ["Stockouts"],
    }
    flat = _flatten_structured(structured)
    profile = _build_profile_dict(flat, source="json")
    assert profile["engagement"]["type"] == "operational-excellence"
    assert profile["derived"]["recommended_practice_area"] == "Operational Excellence"
