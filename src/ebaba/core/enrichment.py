"""Rule-based enrichment: engagement_tier and priority_score.

v1 is intentionally deterministic and free of LLM calls so that every
derived value is auditable. The rules below are tuned for a boutique
consulting book: a Tier-1 engagement requires both real revenue scale
and material budget commitment.
"""

from __future__ import annotations

from ebaba.schemas.client_profile import (
    BudgetBand,
    DerivedInsights,
    EngagementTier,
    EngagementType,
    PracticeArea,
    RevenueBand,
)


# Higher score = larger / more material client.
_REVENUE_SCORE: dict[RevenueBand, int] = {
    "<10M": 5,
    "10-50M": 15,
    "50-250M": 30,
    "250M-1B": 50,
    "1-5B": 70,
    ">5B": 90,
    "undisclosed": 10,
}

_BUDGET_SCORE: dict[BudgetBand, int] = {
    "<50K": 5,
    "50-250K": 15,
    "250K-1M": 35,
    "1-5M": 60,
    ">5M": 85,
    "undisclosed": 10,
}

_PRACTICE_AREA: dict[EngagementType, PracticeArea] = {
    "strategy": "Strategy",
    "operational-excellence": "Operational Excellence",
    "tech-transformation": "Tech Transformation",
    "diagnostic": "Cross-Practice",
    "advisory": "Cross-Practice",
}


def _tier_from_score(score: int) -> EngagementTier:
    if score >= 70:
        return "Tier 1"
    if score >= 40:
        return "Tier 2"
    return "Tier 3"


def compute_priority_score(
    revenue: RevenueBand,
    budget: BudgetBand,
    *,
    num_priorities: int,
    num_pain_points: int,
) -> int:
    """Weighted blend of revenue scale, budget commitment, and signal density."""
    base = int(0.55 * _REVENUE_SCORE[revenue] + 0.45 * _BUDGET_SCORE[budget])
    # Each declared priority / pain point is a small signal of engagement readiness.
    signal_bonus = min(10, num_priorities * 2) + min(10, num_pain_points * 2)
    return max(0, min(100, base + signal_bonus))


def enrich(
    *,
    revenue: RevenueBand,
    budget: BudgetBand,
    engagement_type: EngagementType,
    num_priorities: int,
    num_pain_points: int,
) -> DerivedInsights:
    """Produce a fully validated DerivedInsights block."""
    score = compute_priority_score(
        revenue,
        budget,
        num_priorities=num_priorities,
        num_pain_points=num_pain_points,
    )
    return DerivedInsights(
        engagement_tier=_tier_from_score(score),
        priority_score=score,
        recommended_practice_area=_PRACTICE_AREA[engagement_type],
    )
