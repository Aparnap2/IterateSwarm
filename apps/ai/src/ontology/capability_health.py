"""OntologyAI V6 — Capability Health Engine (ADR-013 §8).

Deterministic computation of capability health and maturity scores
from evidence. No LLM — purely structural mapping.

The engine runs at Stage 8.5 of the pipeline (after Graph Update,
before Gap Analysis) and emits CapabilityHealthUpdated events.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.ontology.capability_types import (
    Capability,
    CapabilityScore,
    HealthTier,
    MaturityLevel,
    compute_health_score,
    compute_health_tier,
    compute_maturity_score,
)

log = logging.getLogger(__name__)


# ── Configuration (loaded from config/capability_weights.yaml) ────

DEFAULT_HEALTH_WEIGHTS = {
    "evidence_volume": 0.20,
    "evidence_freshness": 0.20,
    "evidence_sentiment": 0.20,
    "evidence_confidence": 0.20,
    "risk_exposure": 0.20,
}

DEFAULT_MATURITY_WEIGHTS = {
    "process_standardization": 0.25,
    "measurement_coverage": 0.25,
    "improvement_activity": 0.25,
    "documentation_coverage": 0.25,
}

# Normalization constants
MAX_EVIDENCE_VOLUME = 20  # Normalize evidence count to [0, 1] by dividing by this
MAX_OPEN_RISKS = 10  # Normalize risk count to [0, 1] by dividing by this


# ── Evidence Analysis Helpers ─────────────────────────────────────


def _compute_evidence_volume(evidence_count: int) -> float:
    """Normalize evidence count to [0.0, 1.0]."""
    return min(evidence_count / MAX_EVIDENCE_VOLUME, 1.0)


def _compute_evidence_freshness(
    evidence_timestamps: list[str],
    reference_time: datetime | None = None,
) -> float:
    """Compute freshness score [0.0, 1.0] from evidence timestamps.

    Freshness = avg(1 / (days_since_evidence + 1)) clamped to [0, 1].
    More recent evidence = higher score.
    """
    if not evidence_timestamps:
        return 0.0

    ref = reference_time or datetime.now(timezone.utc)
    total_freshness = 0.0

    for ts_str in evidence_timestamps:
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            days_old = max((ref - ts).total_seconds() / 86400, 0)
            total_freshness += 1.0 / (days_old + 1.0)
        except (ValueError, TypeError):
            continue

    avg_freshness = total_freshness / len(evidence_timestamps) if evidence_timestamps else 0.0
    return min(avg_freshness, 1.0)


def _compute_evidence_sentiment(evidence_sentiments: list[float]) -> float:
    """Compute average sentiment [-1.0, 1.0] from evidence sentiment scores."""
    if not evidence_sentiments:
        return 0.0
    return sum(evidence_sentiments) / len(evidence_sentiments)


def _compute_evidence_confidence(evidence_confidences: list[float]) -> float:
    """Compute weighted average confidence [0.0, 1.0].

    Weighted by freshness (more recent evidence counts more).
    """
    if not evidence_confidences:
        return 0.0
    # Simple average for now; could be freshness-weighted
    return sum(evidence_confidences) / len(evidence_confidences)


def _compute_risk_exposure(open_risks: int, open_conflicts: int) -> float:
    """Compute risk exposure [0.0, 1.0] (inverted: 1.0 = no risk)."""
    total = open_risks + open_conflicts
    return max(0.0, 1.0 - (total / MAX_OPEN_RISKS))


# ── Maturity Analysis Helpers ─────────────────────────────────────


def _compute_process_standardization(
    process_evidence_count: int,
    total_evidence: int,
) -> float:
    """Estimate process standardization from evidence about processes.

    Higher ratio of process-related evidence = more standardized.
    """
    if total_evidence == 0:
        return 0.0
    return min(process_evidence_count / max(total_evidence * 0.3, 1), 1.0)


def _compute_measurement_coverage(
    kpi_evidence_count: int,
    total_evidence: int,
) -> float:
    """Estimate measurement coverage from KPI/metrics evidence.

    Higher ratio of measurement evidence = better coverage.
    """
    if total_evidence == 0:
        return 0.0
    return min(kpi_evidence_count / max(total_evidence * 0.2, 1), 1.0)


def _compute_improvement_activity(
    project_evidence_count: int,
    total_evidence: int,
) -> float:
    """Estimate improvement activity from project/sprint evidence.

    Higher ratio of project evidence = more active improvement.
    """
    if total_evidence == 0:
        return 0.0
    return min(project_evidence_count / max(total_evidence * 0.2, 1), 1.0)


def _compute_documentation_coverage(
    doc_evidence_count: int,
    total_evidence: int,
) -> float:
    """Estimate documentation coverage from doc/wiki evidence.

    Higher ratio of documentation evidence = better coverage.
    """
    if total_evidence == 0:
        return 0.0
    return min(doc_evidence_count / max(total_evidence * 0.25, 1), 1.0)


# ── Main Engine ───────────────────────────────────────────────────


class CapabilityHealthEngine:
    """Computes health and maturity scores for capabilities.

    This engine is deterministic (no LLM) and runs at pipeline Stage 8.5.
    """

    def __init__(
        self,
        health_weights: dict[str, float] | None = None,
        maturity_weights: dict[str, float] | None = None,
    ):
        self.health_weights = health_weights or DEFAULT_HEALTH_WEIGHTS
        self.maturity_weights = maturity_weights or DEFAULT_MATURITY_WEIGHTS

    def compute_score(
        self,
        capability: Capability,
        evidence_records: list[dict],
        open_risks: int = 0,
        open_conflicts: int = 0,
        linked_projects: int = 0,
        linked_requirements: int = 0,
        linked_decisions: int = 0,
    ) -> CapabilityScore:
        """Compute health and maturity scores for a capability.

        Args:
            capability: The capability to score.
            evidence_records: List of evidence dicts with keys:
                - timestamp: ISO datetime string
                - confidence: float [0, 1]
                - sentiment: float [-1, 1]
                - source_type: str (connector, chat, etc.)
                - structured_data: dict (may contain process/kpi/doc keywords)
            open_risks: Count of open risks affecting this capability.
            open_conflicts: Count of open conflicts involving this capability.
            linked_projects: Count of projects investing in this capability.
            linked_requirements: Count of requirements requiring this capability.
            linked_decisions: Count of decisions targeting this capability.

        Returns:
            CapabilityScore with computed health and maturity scores.
        """
        now = datetime.now(timezone.utc).isoformat()
        total_evidence = len(evidence_records)

        # ── Health dimensions ──
        evidence_volume = _compute_evidence_volume(total_evidence)
        evidence_freshness = _compute_evidence_freshness(
            [r.get("timestamp", "") for r in evidence_records]
        )
        evidence_sentiment = _compute_evidence_sentiment(
            [r.get("sentiment", 0.0) for r in evidence_records]
        )
        evidence_confidence = _compute_evidence_confidence(
            [r.get("confidence", 0.5) for r in evidence_records]
        )
        risk_exposure = _compute_risk_exposure(open_risks, open_conflicts)

        health_score = compute_health_score(
            evidence_volume=evidence_volume,
            evidence_freshness=evidence_freshness,
            evidence_sentiment=evidence_sentiment,
            evidence_confidence=evidence_confidence,
            risk_exposure=risk_exposure,
        )

        # ── Maturity dimensions ──
        # Categorize evidence by type for maturity analysis
        process_count = sum(
            1 for r in evidence_records
            if _has_keyword(r, ["process", "playbook", "runbook", "standard", "procedure"])
        )
        kpi_count = sum(
            1 for r in evidence_records
            if _has_keyword(r, ["kpi", "metric", "measure", "track", "dashboard"])
        )
        project_count = sum(
            1 for r in evidence_records
            if _has_keyword(r, ["project", "sprint", "iteration", "experiment", "improvement"])
        )
        doc_count = sum(
            1 for r in evidence_records
            if _has_keyword(r, ["doc", "wiki", "documentation", "handbook", "guide"])
        )

        process_standardization = _compute_process_standardization(process_count, total_evidence)
        measurement_coverage = _compute_measurement_coverage(kpi_count, total_evidence)
        improvement_activity = _compute_improvement_activity(project_count, total_evidence)
        documentation_coverage = _compute_documentation_coverage(doc_count, total_evidence)

        maturity_score, maturity_level = compute_maturity_score(
            process_standardization=process_standardization,
            measurement_coverage=measurement_coverage,
            improvement_activity=improvement_activity,
            documentation_coverage=documentation_coverage,
        )

        # ── Investment level ──
        if linked_projects >= 3:
            investment_level = "high"
        elif linked_projects >= 1:
            investment_level = "medium"
        elif linked_requirements >= 2:
            investment_level = "low"
        else:
            investment_level = "none"

        return CapabilityScore(
            id=f"cs-{capability.id}",
            capability_id=capability.id,
            computed_at=now,
            # Health
            health_score=health_score,
            evidence_volume=total_evidence,
            evidence_freshness=evidence_freshness,
            evidence_sentiment=evidence_sentiment,
            evidence_confidence=evidence_confidence,
            risk_exposure=risk_exposure,
            # Maturity
            maturity_level=maturity_level,
            maturity_score=maturity_score,
            process_standardization=process_standardization,
            measurement_coverage=measurement_coverage,
            improvement_activity=improvement_activity,
            documentation_coverage=documentation_coverage,
            # Investment
            investment_level=investment_level,
            linked_projects=linked_projects,
            linked_requirements=linked_requirements,
            linked_decisions=linked_decisions,
            # Risk
            open_risks=open_risks,
            open_conflicts=open_conflicts,
            unresolved_issues=0,  # computed externally
            # Metadata
            weights_snapshot={
                "health": self.health_weights,
                "maturity": self.maturity_weights,
            },
        )

    def compute_health_tier(self, score: float) -> HealthTier:
        """Map health score to tier."""
        return compute_health_tier(score)


def _has_keyword(record: dict, keywords: list[str]) -> bool:
    """Check if an evidence record contains any of the given keywords."""
    structured = record.get("structured_data", {})
    text = record.get("raw_content", "") or record.get("text", "")

    # Check structured data values
    for value in structured.values():
        if isinstance(value, str) and any(kw in value.lower() for kw in keywords):
            return True
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and any(kw in item.lower() for kw in keywords):
                    return True

    # Check raw text
    if text and any(kw in text.lower() for kw in keywords):
        return True

    return False
