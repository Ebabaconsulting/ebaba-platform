"""Schema for the intermediate MarketReport model used by the analyzer."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TrendItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(..., min_length=1)
    detail: Optional[str] = None
    source: Optional[str] = None
    weight: float = Field(default=1.0, ge=0.0, le=10.0)


class ReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    items: list[TrendItem] = Field(default_factory=list)


class MarketReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry: str
    date: str
    executive_summary: str
    sections: list[ReportSection]
    sources: list[str] = Field(default_factory=list)
