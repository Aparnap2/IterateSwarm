"""V6 OntologyAI — 8-Dimension Feasibility Runtime.

Per §8 of the V6 spec, the Feasibility Runtime scores options across 8
dimensions with weights loaded from an external YAML configuration file
(``config/feasibility/weights.yaml`` by default).

Each dimension produces a score 0–100 (or -100..100 for financial_impact).
The weighted total is mapped to a readiness tier (publish / caveat / review
/ block).  Blocking rules (§8.5) can override the tier.

For M0.5 the runtime is deterministic — no LLM calls.  All dimension scores
are derived from evidence confidence averages and basic heuristics.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from src.entities.models import EvidenceRecord, FeasibilityScore, Option

logger = logging.getLogger(__name__)


# ── Exceptions ──────────────────────────────────────────────────────────


class FeasibilityError(Exception):
    """Base exception for feasibility-runtime failures."""


class WeightConfigError(FeasibilityError):
    """Raised when weight configuration is invalid or unloadable."""


# ── Blocking rule override reasons ──────────────────────────────────────


_BLOCKING_RULES: list[tuple[str, str, float]] = [
    ("dimension_floor", "Any single dimension < 20", 20.0),
    ("compliance_threshold", "Compliance Risk < 30", 30.0),
    ("alignment_floor", "Stakeholder Alignment < 20", 20.0),
    ("data_readiness_zero", "Data Readiness = 0", 0.0),
]

# The fifth blocking rule (open conflict) requires graph check — not
# implemented in M0.5 because we have no Neo4j conflict tracking yet.


# ── Default weights (used when YAML file is not found) ──────────────────


_DEFAULT_WEIGHTS: dict[str, dict[str, Any]] = {
    "business_value": {"weight": 0.25, "inverted": False, "scale": (0, 100)},
    "technical_complexity": {"weight": 0.15, "inverted": True, "scale": (0, 100)},
    "operational_fit": {"weight": 0.15, "inverted": False, "scale": (0, 100)},
    "financial_impact": {"weight": 0.20, "inverted": False, "scale": (-100, 100)},
    "compliance_risk": {"weight": 0.10, "inverted": True, "scale": (0, 100)},
    "data_readiness": {"weight": 0.05, "inverted": False, "scale": (0, 100)},
    "change_effort": {"weight": 0.05, "inverted": True, "scale": (0, 100)},
    "stakeholder_alignment": {"weight": 0.05, "inverted": False, "scale": (0, 100)},
}


def _default_weights_path() -> str:
    """Return the default path to the feasibility weights YAML file."""
    # Walk up from this file to find the project root
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "..", "..", "..", "config", "feasibility", "weights.yaml")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── DimensionScore model (not in entities — internal to FeasibilityRuntime) ─


class DimensionScore(BaseModel):
    """Internal model for a single dimension score.

    This is not a canonical entity — it is an intermediate computation
    result used by the FeasibilityRuntime.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    raw_score: float
    clipped_score: float
    weight: float
    weighted_contribution: float
    source: str = ""
    narrative: str = ""


# ── FeasibilityEngine ───────────────────────────────────────────────
# Note: Class name retains "Engine" for backward compatibility; the
# architectural concept is now the Feasibility Runtime.


class FeasibilityEngine:
    """8-dimension feasibility scoring runtime.

    Dimensions with weights loaded from an external YAML file:

    ====================== ====== ==========
    Dimension              Weight Inverted?
    ====================== ====== ==========
    Business Value         25%    No
    Technical Complexity   15%    Yes
    Operational Fit        15%    No
    Financial Impact       20%    No
    Compliance Risk        10%    Yes
    Data Readiness          5%    No
    Change Effort           5%    Yes
    Stakeholder Alignment   5%    No
    ====================== ====== ==========
    """

    def __init__(self, weights_path: str | None = None) -> None:
        """Load weights from YAML config.

        Parameters
        ----------
        weights_path:
            Path to the YAML weights file.  Defaults to
            ``config/feasibility/weights.yaml`` relative to the project root.
        """
        self._weights_path = weights_path or _default_weights_path()
        self._dimension_config: dict[str, dict[str, Any]] = {}
        self._weights: dict[str, float] = {}
        self._load_weights()

    # ── Weight loading ───────────────────────────────────────────────

    def _load_weights(self) -> None:
        """Load dimension weights from YAML file or use defaults.

        Raises
        ------
        WeightConfigError
            If the YAML file is found but malformed.
        """
        path = self._weights_path
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    raw: dict[str, Any] = yaml.safe_load(f)
            except Exception as exc:
                raise WeightConfigError(
                    f"Failed to load weights from {path}: {exc}"
                ) from exc

            if not raw or "dimensions" not in raw:
                raise WeightConfigError(
                    f"Weights file {path} is missing the top-level 'dimensions' key."
                )

            dimensions_raw: dict[str, Any] = raw["dimensions"]
            for dim_name, cfg in dimensions_raw.items():
                weight = float(cfg.get("weight", 0))
                scale_raw = cfg.get("scale", "0-100")
                inverted = bool(cfg.get("inverted", False))

                # Parse scale string like "0-100" or "-100-100"
                parts = [s.strip() for s in scale_raw.split("-") if s.strip()]
                if len(parts) == 2:
                    try:
                        scale = (int(parts[0]), int(parts[1]))
                    except ValueError:
                        scale = (0, 100)
                else:
                    scale = (0, 100)

                self._dimension_config[dim_name] = {
                    "weight": weight,
                    "inverted": inverted,
                    "scale": scale,
                }
                self._weights[dim_name] = weight

            # Validate weights sum to ~1.0
            total = sum(self._weights.values())
            if abs(total - 1.0) > 0.01:
                logger.warning(
                    "Feasibility weights sum to %.4f (expected 1.0). "
                    "Dimension scores may be skewed.",
                    total,
                )

            logger.info(
                "Loaded %d dimension weights from %s",
                len(self._dimension_config),
                path,
            )
        else:
            logger.warning(
                "Weights file not found at %s — using built-in defaults.",
                path,
            )
            self._dimension_config = dict(_DEFAULT_WEIGHTS)
            self._weights = {
                name: cfg["weight"] for name, cfg in _DEFAULT_WEIGHTS.items()
            }

    # ── Public scoring API ───────────────────────────────────────────

    async def score_option(
        self,
        option: Option,
        evidence_context: list[EvidenceRecord],
    ) -> FeasibilityScore:
        """Score a single option across all 8 dimensions.

        Parameters
        ----------
        option:
            The option to score.
        evidence_context:
            Evidence records linked to the option's decision — used as the
            data source for dimension scoring heuristics.

        Returns
        -------
        FeasibilityScore
            Scores per dimension, weighted total, and readiness tier.
        """
        dimension_scores: dict[str, float] = {}
        details: list[DimensionScore] = []

        for dim_name, cfg in self._dimension_config.items():
            raw = self._compute_dimension_score(dim_name, evidence_context)
            clipped = self._clip_to_scale(raw, cfg["scale"], cfg["inverted"])
            weight = cfg["weight"]
            weighted_val = clipped * weight

            dimension_scores[dim_name] = round(clipped, 1)

            details.append(
                DimensionScore(
                    name=dim_name,
                    raw_score=round(raw, 2),
                    clipped_score=round(clipped, 1),
                    weight=weight,
                    weighted_contribution=round(weighted_val, 2),
                )
            )

        weighted_total = sum(d.clipped_score * d.weight for d in details)
        readiness_tier = self.compute_readiness_tier(weighted_total, dimension_scores)

        score = FeasibilityScore(
            id=f"fs-m0.5-{option.id}",
            option_id=option.id,
            dimensions=dimension_scores,
            weighted_total=round(weighted_total, 1),
            readiness_tier=readiness_tier,
            computed_at=_utcnow(),
        )

        logger.info(
            "Scored option %s — total=%.1f tier=%s",
            option.id,
            score.weighted_total,
            score.readiness_tier,
        )

        return score

    async def score_options(
        self,
        options: list[Option],
        evidence_context: list[EvidenceRecord],
    ) -> list[FeasibilityScore]:
        """Score multiple options.

        Parameters
        ----------
        options:
            List of options to score.
        evidence_context:
            Shared evidence context for all options.

        Returns
        -------
        list[FeasibilityScore]
            One score per option, in the same order.
        """
        scores: list[FeasibilityScore] = []
        for opt in options:
            scores.append(await self.score_option(opt, evidence_context))
        return scores

    # ── Readiness tier ───────────────────────────────────────────────

    def compute_readiness_tier(
        self,
        weighted_total: float,
        dimension_scores: dict[str, float] | None = None,
    ) -> str:
        """Map a weighted total to a readiness tier.

        Base mapping (from §8.4):

        * 85+  → ``"publish"``
        * 70-84 → ``"caveat"``
        * 60-69 → ``"review"``
        * <60   → ``"block"``

        Blocking rules (§8.5) are checked after base mapping:

        1. Any single dimension < 20 → block
        2. Compliance Risk < 30 → block
        3. Stakeholder Alignment < 20 → block
        4. Data Readiness = 0 → block
        5. (M0.5 skip) Open conflict linked to decision → block

        Parameters
        ----------
        weighted_total:
            The weighted sum of dimension scores [0, 100].
        dimension_scores:
            Optional dict of individual dimension scores for blocking rule
            checks.  If ``None``, blocking rules are skipped.

        Returns
        -------
        str
            One of ``"publish"``, ``"caveat"``, ``"review"``, ``"block"``.
        """
        # Base tier from weighted total
        if weighted_total >= 85:
            base_tier = "publish"
        elif weighted_total >= 70:
            base_tier = "caveat"
        elif weighted_total >= 60:
            base_tier = "review"
        else:
            base_tier = "block"

        # Apply blocking rules (they only override to "block")
        if dimension_scores is not None:
            blocking_reasons: list[str] = []

            for dim_name, score in dimension_scores.items():
                if dim_name == "compliance_risk" and score < 30:
                    blocking_reasons.append("compliance_risk < 30")
                if dim_name == "stakeholder_alignment" and score < 20:
                    blocking_reasons.append("stakeholder_alignment < 20")
                if dim_name == "data_readiness" and score == 0:
                    blocking_reasons.append("data_readiness == 0")
                if score < 20:
                    blocking_reasons.append(f"{dim_name} < 20")

            if blocking_reasons:
                logger.warning(
                    "Blocking rules triggered: %s. Overriding tier '%s' → 'block'.",
                    "; ".join(blocking_reasons),
                    base_tier,
                )
                return "block"

        return base_tier

    # ── Dimension score computation ──────────────────────────────────

    @staticmethod
    def _compute_dimension_score(
        dim_name: str,
        evidence_context: list[EvidenceRecord],
    ) -> float:
        """Compute a raw (unclipped) score for a single dimension.

        For M0.5 all scores are derived from evidence confidence averages
        and simple heuristics.
        """
        avg_conf = (
            sum(r.confidence for r in evidence_context) / len(evidence_context)
            if evidence_context
            else 0.0
        )
        base = avg_conf * 100  # normalise to 0-100

        dimension_heuristics: dict[str, float] = {
            # Business value: how much evidence supports the option
            "business_value": base * 1.0,
            # Technical complexity: more evidence may mean more known complexity
            "technical_complexity": base * 0.8,
            # Operational fit: evidence maturity indicator
            "operational_fit": base * 0.7,
            # Financial impact: scaled -100..100 from confidence
            "financial_impact": (base * 0.6) - 20.0,
            # Compliance risk: higher confidence = lower risk (but inverted later)
            "compliance_risk": base * 0.85,
            # Data readiness: coverage from available evidence
            "data_readiness": (len(evidence_context) / 10.0) * 100 if evidence_context else 0.0,
            # Change effort: more evidence may indicate more org impact
            "change_effort": base * 0.75,
            # Stakeholder alignment: derived from mentions
            "stakeholder_alignment": base * 0.65,
        }

        return dimension_heuristics.get(dim_name, base)

    @staticmethod
    def _clip_to_scale(
        raw: float,
        scale: tuple[int, int],
        inverted: bool,
    ) -> float:
        """Clip *raw* to *scale* and optionally invert.

        Inverted dimensions transform so that higher raw = lower score
        (for complexity, risk, effort).
        """
        lo, hi = float(scale[0]), float(scale[1])
        if inverted:
            # Invert: if raw is at the top of the conceptual range,
            # produce a low score.
            # Conceptual range is always 0-100 for inverted dims.
            inverted_raw = 100.0 - raw
            return max(lo, min(hi, inverted_raw))
        return max(lo, min(hi, raw))

    # ── Utility ──────────────────────────────────────────────────────

    def get_weights_snapshot(self) -> dict[str, dict[str, Any]]:
        """Return a copy of the current dimension configuration.

        Useful for attaching to ``FeasibilityScore`` records.
        """
        return dict(self._dimension_config)
