"""Schema for an executive ClientProfile JSON artefact."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


RevenueBand = Literal[
    "<10M",
    "10-50M",
    "50-250M",
    "250M-1B",
    "1-5B",
    ">5B",
    "undisclosed",
]

EmployeeBand = Literal[
    "<50",
    "50-250",
    "250-1000",
    "1000-5000",
    ">5000",
    "undisclosed",
]

BudgetBand = Literal[
    "<50K",
    "50-250K",
    "250K-1M",
    "1-5M",
    ">5M",
    "undisclosed",
]

EngagementType = Literal[
    "strategy",
    "operational-excellence",
    "tech-transformation",
    "diagnostic",
    "advisory",
]

EngagementTier = Literal["Tier 1", "Tier 2", "Tier 3"]

PracticeArea = Literal[
    "Strategy",
    "Operational Excellence",
    "Tech Transformation",
    "Cross-Practice",
]


class PrimaryContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    email: Optional[EmailStr] = None


class Engagement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EngagementType
    scope: str = Field(..., min_length=1)
    timeline_weeks: int = Field(..., ge=1, le=104)
    budget_band_usd: BudgetBand = "undisclosed"


class DerivedInsights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engagement_tier: EngagementTier
    priority_score: int = Field(..., ge=0, le=100)
    recommended_practice_area: PracticeArea


class ProfileMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_at: str
    source: str
    intake_version: str = "0.1.0"


class ClientProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(..., min_length=1)
    company_name: str = Field(..., min_length=1)
    industry: str = Field(..., min_length=1)
    sub_industry: Optional[str] = None
    hq_country: str = Field(..., min_length=2, max_length=2, description="ISO-3166-1 alpha-2")
    regions_active: list[str] = Field(default_factory=list)
    revenue_band_usd: RevenueBand = "undisclosed"
    employee_band: EmployeeBand = "undisclosed"
    primary_contact: PrimaryContact
    engagement: Engagement
    strategic_priorities: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    derived: DerivedInsights
    metadata: ProfileMetadata

    @field_validator("hq_country")
    @classmethod
    def _uppercase_country(cls, v: str) -> str:
        return v.upper()

    @field_validator("regions_active")
    @classmethod
    def _dedupe_regions(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for r in v:
            key = r.strip()
            if key and key.lower() not in seen:
                seen.add(key.lower())
                out.append(key)
        return out
