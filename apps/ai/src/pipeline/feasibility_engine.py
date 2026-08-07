"""Feasibility Engine — multi-dimensional option scoring.

For the V6 vertical slice, scores each option along 8 dimensions
(per V6 spec §8), computes a weighted total, and determines a
readiness tier:

=============== =====  ===========================================
Dimension       Weight Source
=============== =====  ===========================================
Business Value   25%   Stakeholder scoring, KPI targets
Technical Compl. 15%   System dependency analysis (inverted)
Operational Fit  15%   Capability maturity
Financial Impact 20%   Cost/benefit from evidence
Compliance Risk  10%   BusinessRule check (inverted)
Data Readiness    5%   Evidence coverage score
Change Effort     5%   Org impact analysis (inverted)
Stakeholder Align 5%   Stakeholder sentiment from evidence
=============== =====  ===========================================

Readiness tiers: **Publish** (85-100), **Caveats** (70-84),
**Review** (60-69), **Block** (<60).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

from src.entities.models import Option

logger = logging.getLogger(__name__)

# ── Default weights (mirrors config/feasibility/weights.yaml) ────────────

DEFAULT_WEIGHTS: dict[str, float] = {
    "business_value": 0.25,
    "technical_complexity": 0.15,
    "operational_fit": 0.15,
    "financial_impact": 0.20,
    "compliance_risk": 0.10,
    "data_readiness": 0.05,
    "change_effort": 0.05,
    "stakeholder_alignment": 0.05,
}

# ── Hardcoded dimension scores for the two options ───────────────────────
# These are derived from the three mock evidence records.

OPTION_A_SCORES: dict[str, float] = {
    "business_value": 85,
    "technical_complexity": 45,
    "operational_fit": 70,
    "financial_impact": 75,
    "compliance_risk": 80,
    "data_readiness": 60,
    "change_effort": 40,
    "stakeholder_alignment": 80,
}

OPTION_B_SCORES: dict[str, float] = {
    "business_value": 55,
    "technical_complexity": 80,
    "operational_fit": 85,
    "financial_impact": 45,
    "compliance_risk": 90,
    "data_readiness": 70,
    "change_effort": 70,
    "stakeholder_alignment": 65,
}


class FeasibilityResult(BaseModel):
    """Result of scoring a single option.

    Attributes
    ----------
    option_id:
        ULID of the scored option.
    option_title:
        Human-readable title.
    dimensions:
        Individual dimension scores (0–100 each).
    weighted_total:
        Sum of dimension × weight (0–100).
    readiness_tier:
        One of ``"publish"``, ``"caveat"``, ``"review"``, ``"block"``.
    blocking_reasons:
        Any blocking-rule violations (empty = no blockers).
    """

    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    option_id: str
    option_title: str
    dimensions: dict[str, float] = Field(default_factory=dict)
    weighted_total: float = Field(ge=0.0, le=100.0)
    readiness_tier: str  # "publish" | "caveat" | "review" | "block"
    blocking_reasons: list[str] = Field(default_factory=list)


class FeasibilityEngine:
    """Multi-dimensional feasibility scoring engine.

    Parameters
    ----------
    db_pool:
        An ``asyncpg.Pool`` (or compatible). May be ``None``.
    """

    def __init__(self, db_pool) -> None:
        self._pool = db_pool
        self._weights: dict[str, float] = dict(DEFAULT_WEIGHTS)

    async def score_options(
        self,
        options: list[Option],
    ) -> list[FeasibilityResult]:
        """Score each option across all 8 feasibility dimensions.

        Parameters
        ----------
        options:
            The option entities to score.

        Returns
        -------
        list[FeasibilityResult]
            One result per option, sorted by weighted_total descending.
        """
        results: list[FeasibilityResult] = []

        for option in options:
            dimensions = self._get_scores_for_option(option)
            weighted_total = self._compute_weighted_total(dimensions)
            blocking_reasons = self._check_blocking_rules(dimensions, weighted_total)
            tier = self._determine_tier(weighted_total, blocking_reasons)

            results.append(
                FeasibilityResult(
                    option_id=option.id,
                    option_title=option.title,
                    dimensions=dimensions,
                    weighted_total=round(weighted_total, 1),
                    readiness_tier=tier,
                    blocking_reasons=blocking_reasons,
                )
            )

        results.sort(key=lambda r: r.weighted_total, reverse=True)
        logger.info(
            "Feasibility scored: %s",
            {r.option_title: r.readiness_tier for r in results},
        )
        return results

    def _get_scores_for_option(self, option: Option) -> dict[str, float]:
        """Return hardcoded dimension scores for an option.

        In production, these would be computed from evidence, stakeholder
        sentiment, and graph analysis.
        """
        if option.id.endswith("OA"):
            return dict(OPTION_A_SCORES)
        return dict(OPTION_B_SCORES)

    def _compute_weighted_total(self, dimensions: dict[str, float]) -> float:
        """Compute weighted total = Σ(dimension × weight).

        Returns
        -------
        float
            Weighted total (0–100).
        """
        total = 0.0
        for dim, score in dimensions.items():
            weight = self._weights.get(dim, 0.0)
            total += score * weight
        return total

    def _check_blocking_rules(
        self,
        dimensions: dict[str, float],
        weighted_total: float,  # noqa: ARG002
    ) -> list[str]:
        """Check blocking override rules (V6 spec §8.5).

        Returns a list of violated blocking-reason strings.
        """
        blockers: list[str] = []

        # Rule 1: Any single dimension < 20 → Block
        for dim, score in dimensions.items():
            if score < 20.0:
                blockers.append(f"Dimension '{dim}' score ({score}) is below 20 floor")

        # Rule 2: Compliance Risk < 30 → Block
        compliance = dimensions.get("compliance_risk", 100)
        if compliance < 30.0:
            blockers.append(
                f"Compliance risk score ({compliance}) is below 30 threshold"
            )

        # Rule 3: Stakeholder Alignment < 20 → Block
        alignment = dimensions.get("stakeholder_alignment", 100)
        if alignment < 20.0:
            blockers.append(f"Stakeholder alignment ({alignment}) is below 20 floor")

        # Rule 4: Data Readiness = 0 → Block
        data_readiness = dimensions.get("data_readiness", 100)
        if data_readiness == 0.0:
            blockers.append("Data readiness is 0% — no evidence at all")

        return blockers

    @staticmethod
    def _determine_tier(
        weighted_total: float,
        blocking_reasons: list[str],
    ) -> str:
        """Determine readiness tier from weighted total and blockers.

        Blocking rules override the numeric tier.
        """
        if blocking_reasons:
            return "block"

        if weighted_total >= 85:
            return "publish"
        if weighted_total >= 70:
            return "caveat"
        if weighted_total >= 60:
            return "review"
        return "block"
