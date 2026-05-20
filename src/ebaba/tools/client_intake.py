"""Tool #1 — client_intake.

Ingest raw client information (free-text, markdown, or pre-structured JSON)
and emit a validated executive `ClientProfile` JSON artefact.

Usage:
    python -m ebaba.tools.client_intake --input data/inbox/acme.json
    python -m ebaba.tools.client_intake --input data/inbox/acme.txt --output outputs/client_profiles/acme.json
    python -m ebaba.tools.client_intake --interactive
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from pydantic import ValidationError

from ebaba.core import io as eio
from ebaba.core.enrichment import enrich
from ebaba.core.formatting import iso_now, slugify, today_stamp
from ebaba.core.logging import executive_fail, executive_ok, executive_warn, get_logger
from ebaba.core.validation import SchemaValidationError, validate
from ebaba.schemas.client_profile import (
    BudgetBand,
    ClientProfile,
    EmployeeBand,
    Engagement,
    EngagementType,
    PrimaryContact,
    ProfileMetadata,
    RevenueBand,
)


app = typer.Typer(
    add_completion=False,
    help="ebabaConsulting — Client Intake. Converts raw client info into executive JSON profiles.",
)
log = get_logger("ebaba.client_intake")


# ---------------------------------------------------------------------------
# Free-text parsing
# ---------------------------------------------------------------------------

_FIELD_PATTERN = re.compile(
    r"^\s*(?:[-*]\s+)?(?P<key>[A-Za-z][A-Za-z0-9 _/&-]+?)\s*[:=]\s*(?P<value>.+?)\s*$"
)

_LIST_KEYS = {"strategic_priorities", "pain_points", "success_metrics", "regions_active"}

_KEY_ALIASES = {
    "company": "company_name",
    "company name": "company_name",
    "client": "company_name",
    "name": "company_name",
    "industry": "industry",
    "sector": "industry",
    "sub industry": "sub_industry",
    "sub-industry": "sub_industry",
    "country": "hq_country",
    "hq": "hq_country",
    "hq country": "hq_country",
    "regions": "regions_active",
    "regions active": "regions_active",
    "geography": "regions_active",
    "revenue": "revenue_band_usd",
    "revenue band": "revenue_band_usd",
    "employees": "employee_band",
    "headcount": "employee_band",
    "contact": "primary_contact_name",
    "contact name": "primary_contact_name",
    "contact role": "primary_contact_role",
    "role": "primary_contact_role",
    "email": "primary_contact_email",
    "engagement": "engagement_type",
    "engagement type": "engagement_type",
    "scope": "engagement_scope",
    "timeline": "engagement_timeline_weeks",
    "timeline weeks": "engagement_timeline_weeks",
    "duration": "engagement_timeline_weeks",
    "budget": "engagement_budget_band",
    "budget band": "engagement_budget_band",
    "priorities": "strategic_priorities",
    "strategic priorities": "strategic_priorities",
    "pain points": "pain_points",
    "pains": "pain_points",
    "success": "success_metrics",
    "success metrics": "success_metrics",
    "kpis": "success_metrics",
}


def _normalize_key(raw: str) -> Optional[str]:
    return _KEY_ALIASES.get(raw.strip().lower().replace("_", " "))


def _split_list(value: str) -> list[str]:
    parts = re.split(r"[,;\n]|\s+•\s+|\s+-\s+", value)
    return [p.strip(" -•\t") for p in parts if p.strip(" -•\t")]


def _coerce_int(value: Any, default: int = 12) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        if m:
            return int(m.group(0))
    return default


def parse_free_text(raw: str) -> dict[str, Any]:
    """Parse a `key: value` style free-text intake form into a flat dict."""
    flat: dict[str, Any] = {}
    for line in raw.splitlines():
        match = _FIELD_PATTERN.match(line)
        if not match:
            continue
        key = _normalize_key(match.group("key"))
        if key is None:
            continue
        value = match.group("value").strip()
        if key in _LIST_KEYS:
            flat.setdefault(key, [])
            flat[key].extend(_split_list(value))
        else:
            flat[key] = value
    return flat


# ---------------------------------------------------------------------------
# Normalization to ClientProfile-shaped dict
# ---------------------------------------------------------------------------

def _normalize_revenue(value: Any) -> RevenueBand:
    allowed: set[str] = {"<10M", "10-50M", "50-250M", "250M-1B", "1-5B", ">5B", "undisclosed"}
    if isinstance(value, str) and value in allowed:
        return value  # type: ignore[return-value]
    return "undisclosed"


def _normalize_budget(value: Any) -> BudgetBand:
    allowed: set[str] = {"<50K", "50-250K", "250K-1M", "1-5M", ">5M", "undisclosed"}
    if isinstance(value, str) and value in allowed:
        return value  # type: ignore[return-value]
    return "undisclosed"


def _normalize_employees(value: Any) -> EmployeeBand:
    allowed: set[str] = {"<50", "50-250", "250-1000", "1000-5000", ">5000", "undisclosed"}
    if isinstance(value, str) and value in allowed:
        return value  # type: ignore[return-value]
    return "undisclosed"


def _normalize_engagement_type(value: Any) -> EngagementType:
    allowed: set[str] = {
        "strategy",
        "operational-excellence",
        "tech-transformation",
        "diagnostic",
        "advisory",
    }
    if isinstance(value, str):
        v = value.strip().lower().replace(" ", "-")
        if v in allowed:
            return v  # type: ignore[return-value]
    return "advisory"


def _build_profile_dict(flat: dict[str, Any], *, source: str) -> dict[str, Any]:
    """Convert a flat key/value dict into a ClientProfile-shaped nested dict."""
    company = str(flat.get("company_name", "")).strip()
    if not company:
        raise ValueError("Missing required field: company_name")

    industry = str(flat.get("industry", "")).strip()
    if not industry:
        raise ValueError("Missing required field: industry")

    contact_name = str(flat.get("primary_contact_name", "")).strip()
    contact_role = str(flat.get("primary_contact_role", "")).strip()
    if not contact_name or not contact_role:
        raise ValueError("Missing required fields: primary contact name and role")

    engagement_type = _normalize_engagement_type(flat.get("engagement_type"))
    engagement_scope = str(flat.get("engagement_scope", "")).strip()
    if not engagement_scope:
        raise ValueError("Missing required field: engagement scope")

    profile = {
        "client_id": flat.get("client_id") or slugify(company),
        "company_name": company,
        "industry": industry,
        "sub_industry": flat.get("sub_industry") or None,
        "hq_country": str(flat.get("hq_country", "")).strip().upper()[:2] or "US",
        "regions_active": flat.get("regions_active") or [],
        "revenue_band_usd": _normalize_revenue(flat.get("revenue_band_usd")),
        "employee_band": _normalize_employees(flat.get("employee_band")),
        "primary_contact": {
            "name": contact_name,
            "role": contact_role,
            "email": flat.get("primary_contact_email") or None,
        },
        "engagement": {
            "type": engagement_type,
            "scope": engagement_scope,
            "timeline_weeks": _coerce_int(flat.get("engagement_timeline_weeks"), default=12),
            "budget_band_usd": _normalize_budget(flat.get("engagement_budget_band")),
        },
        "strategic_priorities": flat.get("strategic_priorities") or [],
        "pain_points": flat.get("pain_points") or [],
        "success_metrics": flat.get("success_metrics") or [],
        "metadata": {
            "created_at": iso_now(),
            "source": source,
            "intake_version": "0.1.0",
        },
    }

    derived = enrich(
        revenue=profile["revenue_band_usd"],
        budget=profile["engagement"]["budget_band_usd"],
        engagement_type=engagement_type,
        num_priorities=len(profile["strategic_priorities"]),
        num_pain_points=len(profile["pain_points"]),
    )
    profile["derived"] = derived.model_dump()
    return profile


def _load_raw(path: Path) -> dict[str, Any]:
    fmt = eio.detect_format(path)
    if fmt == "json":
        data = eio.read_json(path)
        if not isinstance(data, dict):
            raise ValueError("JSON intake input must be an object at the root.")
        return data
    return parse_free_text(eio.read_text(path))


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

def _prompt_intake() -> dict[str, Any]:
    typer.echo("Interactive client intake — press Enter to skip optional fields.")
    flat: dict[str, Any] = {
        "company_name": typer.prompt("Company name"),
        "industry": typer.prompt("Industry"),
        "sub_industry": typer.prompt("Sub-industry", default="", show_default=False) or None,
        "hq_country": typer.prompt("HQ country (ISO-2)", default="US"),
        "regions_active": _split_list(
            typer.prompt("Regions active (comma-separated)", default="", show_default=False)
        ),
        "revenue_band_usd": typer.prompt(
            "Revenue band [<10M|10-50M|50-250M|250M-1B|1-5B|>5B|undisclosed]",
            default="undisclosed",
        ),
        "employee_band": typer.prompt(
            "Employee band [<50|50-250|250-1000|1000-5000|>5000|undisclosed]",
            default="undisclosed",
        ),
        "primary_contact_name": typer.prompt("Primary contact name"),
        "primary_contact_role": typer.prompt("Primary contact role"),
        "primary_contact_email": typer.prompt(
            "Primary contact email", default="", show_default=False
        )
        or None,
        "engagement_type": typer.prompt(
            "Engagement type [strategy|operational-excellence|tech-transformation|diagnostic|advisory]",
            default="advisory",
        ),
        "engagement_scope": typer.prompt("Engagement scope"),
        "engagement_timeline_weeks": typer.prompt("Engagement timeline (weeks)", default="12"),
        "engagement_budget_band": typer.prompt(
            "Budget band [<50K|50-250K|250K-1M|1-5M|>5M|undisclosed]",
            default="undisclosed",
        ),
        "strategic_priorities": _split_list(
            typer.prompt("Strategic priorities (comma-separated)", default="", show_default=False)
        ),
        "pain_points": _split_list(
            typer.prompt("Pain points (comma-separated)", default="", show_default=False)
        ),
        "success_metrics": _split_list(
            typer.prompt("Success metrics (comma-separated)", default="", show_default=False)
        ),
    }
    return flat


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def _default_output_path(profile: ClientProfile) -> Path:
    return Path("outputs/client_profiles") / f"{slugify(profile.client_id)}-{today_stamp()}.json"


@app.command()
def main(
    input: Optional[Path] = typer.Option(
        None,
        "--input",
        "-i",
        exists=False,
        readable=True,
        help="Path to a raw intake file (.json | .txt | .md).",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Destination JSON path. Defaults to outputs/client_profiles/<slug>-<YYYYMMDD>.json",
    ),
    interactive: bool = typer.Option(
        False, "--interactive", help="Prompt-driven intake (overrides --input)."
    ),
) -> None:
    """Run a client intake and emit a validated ClientProfile JSON."""
    try:
        if interactive:
            flat = _prompt_intake()
            source = "interactive"
        else:
            if input is None:
                executive_fail("Provide --input <path> or use --interactive.")
                raise typer.Exit(code=2)
            raw = _load_raw(input)
            # If the input is already a fully-shaped ClientProfile, accept it as-is.
            if {"company_name", "industry", "primary_contact", "engagement"}.issubset(raw.keys()) and isinstance(
                raw.get("primary_contact"), dict
            ):
                flat = _flatten_structured(raw)
            else:
                flat = raw
            source = str(input)

        profile_dict = _build_profile_dict(flat, source=source)
        profile = validate(ClientProfile, profile_dict)
    except SchemaValidationError as exc:
        executive_fail(str(exc))
        raise typer.Exit(code=2) from exc
    except ValidationError as exc:
        executive_fail(f"Validation error: {exc}")
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        executive_fail(str(exc))
        raise typer.Exit(code=2) from exc
    except eio.IOError_ as exc:
        executive_fail(str(exc))
        raise typer.Exit(code=3) from exc

    out_path = output or _default_output_path(profile)
    try:
        written = eio.write_json(out_path, profile.model_dump())
    except eio.IOError_ as exc:
        executive_fail(str(exc))
        raise typer.Exit(code=3) from exc

    executive_ok(
        f"ClientProfile written -> {written} "
        f"({profile.derived.engagement_tier}, {profile.derived.recommended_practice_area}, "
        f"priority={profile.derived.priority_score})"
    )


def _flatten_structured(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a pre-structured JSON intake into the flat shape used internally."""
    contact = raw.get("primary_contact", {}) or {}
    engagement = raw.get("engagement", {}) or {}
    return {
        "client_id": raw.get("client_id"),
        "company_name": raw.get("company_name"),
        "industry": raw.get("industry"),
        "sub_industry": raw.get("sub_industry"),
        "hq_country": raw.get("hq_country"),
        "regions_active": raw.get("regions_active") or [],
        "revenue_band_usd": raw.get("revenue_band_usd"),
        "employee_band": raw.get("employee_band"),
        "primary_contact_name": contact.get("name"),
        "primary_contact_role": contact.get("role"),
        "primary_contact_email": contact.get("email"),
        "engagement_type": engagement.get("type"),
        "engagement_scope": engagement.get("scope"),
        "engagement_timeline_weeks": engagement.get("timeline_weeks"),
        "engagement_budget_band": engagement.get("budget_band_usd"),
        "strategic_priorities": raw.get("strategic_priorities") or [],
        "pain_points": raw.get("pain_points") or [],
        "success_metrics": raw.get("success_metrics") or [],
    }


if __name__ == "__main__":
    sys.exit(app())
