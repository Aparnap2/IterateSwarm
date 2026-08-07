# FROZEN — V6.0 M0.5
"""OntologyAI V6 — Evaluation Runtime Interface (Protocol + Base).

Renamed from "Outcome Runtime" during the V6.0 M0.5 pivot.

The rationale (from the pivot narrative):

> "You don't have Actions yet. Without Actions there are no Outcomes."

Instead of Outcome Runtime (which implies action execution + results),
this module focuses on **evaluation** — measuring decision quality,
updating confidence, replay, and golden-dataset tracking.

Pipeline stages
---------------
1. **evaluate** — Compute metrics from a DecisionAnalysis + outcomes.
2. **update_confidence** — Bayesian-style confidence update.
3. **replay** — Re-evaluate a past decision against current evidence.
4. **golden_dataset** — Track decision accuracy for model improvement.

Design constraints
------------------
* At M0.5 this is a **metrics + logging** layer.  It does NOT execute actions.
* Confidence updates follow a heuristic formula (deterministic at M0.5).
* All methods are ``async`` to support non-blocking database access.

FROZEN — V6.0 M0.5
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from src.decision.contracts import DecisionAnalysis, FeasibilityResult
from src.goal.models import Goal

logger = logging.getLogger(__name__)


# ── Error hierarchy ──────────────────────────────────────────────────────


class EvaluationRuntimeError(Exception):
    """Base exception for all Evaluation Runtime failures."""


class MetricError(EvaluationRuntimeError):
    """Raised when metric computation fails.

    Parameters
    ----------
    decision_id : str
        The decision ULID.
    reason : str
        Explanation.
    """

    def __init__(self, decision_id: str, reason: str) -> None:
        self.decision_id = decision_id
        self.reason = reason
        super().__init__(f"Metric error for decision '{decision_id}': {reason}")


class RecordingError(EvaluationRuntimeError):
    """Raised when an evaluation record cannot be persisted.

    Parameters
    ----------
    decision_id : str
        The decision ULID.
    reason : str
        Explanation.
    """

    def __init__(self, decision_id: str, reason: str) -> None:
        self.decision_id = decision_id
        self.reason = reason
        super().__init__(
            f"Recording failed for decision '{decision_id}': {reason}"
        )


# ── Value Objects ────────────────────────────────────────────────────────


class EvaluationMetrics:
    """Aggregated metrics for a decision evaluation.

    Parameters
    ----------
    decision_id : str
    goal_id : str | None
    confidence_score : float
        Post-evaluation confidence in the recommendation (0.0–1.0).
    feasibility_score : float
        Deterministic feasibility score (0.0–100.0).
    evidence_count : int
        Number of evidence records backing the decision.
    options_count : int
        Number of options evaluated.
    tradeoffs_count : int
        Number of pairwise tradeoffs generated.
    evaluated_at : datetime
    """

    __slots__ = (
        "decision_id",
        "goal_id",
        "confidence_score",
        "feasibility_score",
        "evidence_count",
        "options_count",
        "tradeoffs_count",
        "evaluated_at",
    )

    def __init__(
        self,
        decision_id: str,
        goal_id: str | None,
        confidence_score: float,
        feasibility_score: float,
        evidence_count: int,
        options_count: int,
        tradeoffs_count: int,
        evaluated_at: datetime,
    ) -> None:
        self.decision_id = decision_id
        self.goal_id = goal_id
        self.confidence_score = confidence_score
        self.feasibility_score = feasibility_score
        self.evidence_count = evidence_count
        self.options_count = options_count
        self.tradeoffs_count = tradeoffs_count
        self.evaluated_at = evaluated_at

    def __repr__(self) -> str:
        return (
            f"EvaluationMetrics(decision={self.decision_id!r}, "
            f"confidence={self.confidence_score:.2f}, "
            f"feasibility={self.feasibility_score:.1f})"
        )


class ReplayResult:
    """Result of replaying a past decision against current evidence.

    Parameters
    ----------
    decision_id : str
    original_analysis : DecisionAnalysis | None
    new_analysis : DecisionAnalysis | None
    confidence_delta : float
        Change in confidence after replay (positive = improved).
    evidence_changed : bool
    replayed_at : datetime
    """

    __slots__ = (
        "decision_id",
        "original_analysis",
        "new_analysis",
        "confidence_delta",
        "evidence_changed",
        "replayed_at",
    )

    def __init__(
        self,
        decision_id: str,
        original_analysis: DecisionAnalysis | None,
        new_analysis: DecisionAnalysis | None,
        confidence_delta: float,
        evidence_changed: bool,
        replayed_at: datetime,
    ) -> None:
        self.decision_id = decision_id
        self.original_analysis = original_analysis
        self.new_analysis = new_analysis
        self.confidence_delta = confidence_delta
        self.evidence_changed = evidence_changed
        self.replayed_at = replayed_at

    def __repr__(self) -> str:
        return (
            f"ReplayResult(decision={self.decision_id!r}, "
            f"delta={self.confidence_delta:+.2f}, "
            f"evidence_changed={self.evidence_changed})"
        )


# ── Protocol ───────────────────────────────────────────────────────────


@runtime_checkable
class EvaluationRuntime(Protocol):
    """Frozen interface for the Evaluation Runtime.

    Pipeline stages:
        1. ``evaluate``           — Compute metrics from analysis + feedback.
        2. ``update_confidence``  — Bayesian-style confidence update.
        3. ``replay``             — Re-evaluate past decision vs current evidence.
        4. ``golden_dataset``     — Track decision accuracy over time.

    FROZEN — V6.0 M0.5 — Do not modify this interface.
    """

    async def evaluate(
        self,
        decision_id: str,
        analysis: DecisionAnalysis,
        *,
        goal_id: str | None = None,
        actual_result: str | None = None,
        measured_metrics: dict[str, float] | None = None,
        tenant_id: str,
    ) -> EvaluationMetrics:
        """Compute evaluation metrics for a decision.

        Parameters
        ----------
        decision_id : str
        analysis : DecisionAnalysis
            The completed analysis to evaluate.
        goal_id : str | None
            The Goal this decision advances (if any).
        actual_result : str | None
            What actually happened (if the decision was executed).
        measured_metrics : dict[str, float] | None
            Key metrics measured after execution.
        tenant_id : str

        Returns
        -------
        EvaluationMetrics

        Raises
        ------
        MetricError
            If metrics cannot be computed.
        """
        ...

    async def update_confidence(
        self,
        decision_id: str,
        *,
        tenant_id: str,
        confidence_delta: float,
        reason: str = "",
    ) -> float:
        """Update the confidence score for a decision.

        Uses a heuristic formula at M0.5.  In M1, this becomes a proper
        Bayesian update.

        Parameters
        ----------
        decision_id : str
        confidence_delta : float
            Change to apply to the confidence score.
        reason : str
            Why the update occurred.

        Returns
        -------
        float
            The updated confidence score (0.0–1.0).

        Raises
        ------
        MetricError
        """
        ...

    async def replay(
        self,
        decision_id: str,
        *,
        tenant_id: str,
        against_evidence_ids: list[str] | None = None,
    ) -> ReplayResult:
        """Re-evaluate a past decision against current evidence.

        Parameters
        ----------
        decision_id : str
        against_evidence_ids : list[str] | None
            Specific evidence IDs to use (default: current evidence pool).
        tenant_id : str

        Returns
        -------
        ReplayResult

        Raises
        ------
        MetricError
        """
        ...

    async def golden_dataset(
        self,
        *,
        goal_id: str | None = None,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        """Return golden dataset records for decision accuracy tracking.

        Each record contains:
            - decision_id
            - original_confidence
            - actual_outcome
            - accuracy_score
            - evaluated_at

        Parameters
        ----------
        goal_id : str | None
        tenant_id : str

        Returns
        -------
        list[dict[str, Any]]
        """


# ── Base implementation ─────────────────────────────────────────────────


class BaseEvaluationRuntime:
    """Shared logic for EvaluationRuntime implementations.

    Provides:
    - In-memory evaluation store.
    - Deterministic metric computation helpers.
    - Simple confidence delta application.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _hash_decision(self, decision_id: str) -> str:
        return hashlib.sha256(decision_id.encode()).hexdigest()[:16]

    def _compute_feasibility(
        self, analysis: DecisionAnalysis
    ) -> float:
        """Deterministic feasibility from analysis (stub at M0.5)."""
        if not analysis.options:
            return 0.0
        opt_scores = [
            getattr(o, "feasibility_score", None)
            or (o.structured_data.get("feasibility_score", 50.0)
                if hasattr(o, "structured_data") else 50.0)
            for o in (analysis.options or [])
        ]
        return sum(opt_scores) / len(opt_scores) if opt_scores else 50.0


# ── Default implementation ────────────────────────────────────────────────


class DefaultEvaluationRuntime(BaseEvaluationRuntime):
    """Default in-memory Evaluation Runtime.

    At M0.5, this is a metrics + logging layer.  It does NOT execute actions
    or track outcomes.  All results are stored in-memory.
    """

    async def evaluate(
        self,
        decision_id: str,
        analysis: DecisionAnalysis,
        *,
        goal_id: str | None = None,
        actual_result: str | None = None,
        measured_metrics: dict[str, float] | None = None,
        tenant_id: str,
    ) -> EvaluationMetrics:
        evidence_count = sum(
            len(e.evidence_ids) if hasattr(e, "evidence_ids") else 1
            for e in analysis.evidence
        ) if hasattr(analysis, "evidence") else 0

        options_count = len(analysis.options) if analysis.options else 0
        tradeoffs_count = len(analysis.tradeoffs) if analysis.tradeoffs else 0

        metrics = EvaluationMetrics(
            decision_id=decision_id,
            goal_id=goal_id,
            confidence_score=analysis.confidence,
            feasibility_score=self._compute_feasibility(analysis),
            evidence_count=evidence_count,
            options_count=options_count,
            tradeoffs_count=tradeoffs_count,
            evaluated_at=self._utcnow(),
        )

        self._store[decision_id] = {
            "decision_id": decision_id,
            "goal_id": goal_id,
            "metrics": metrics,
            "actual_result": actual_result,
            "measured_metrics": measured_metrics or {},
            "tenant_id": tenant_id,
        }
        logger.info(
            "Evaluated decision %s: confidence=%.2f, feasibility=%.1f",
            decision_id,
            metrics.confidence_score,
            metrics.feasibility_score,
        )
        return metrics

    async def update_confidence(
        self,
        decision_id: str,
        *,
        tenant_id: str,
        confidence_delta: float,
        reason: str = "",
    ) -> float:
        record = self._store.get(decision_id)
        if record is None:
            raise MetricError(decision_id, "decision not found in evaluation store")

        metrics = record["metrics"]
        new_confidence = max(0.0, min(1.0, metrics.confidence_score + confidence_delta))
        metrics.confidence_score = new_confidence
        metrics.evaluated_at = self._utcnow()

        record["confidence_updates"] = record.get("confidence_updates", []) + [
            {
                "delta": confidence_delta,
                "reason": reason,
                "timestamp": self._utcnow().isoformat(),
            }
        ]
        logger.info(
            "Updated confidence for %s: %.2f → %.2f (reason: %s)",
            decision_id,
            metrics.confidence_score - confidence_delta,
            new_confidence,
            reason,
        )
        return new_confidence

    async def replay(
        self,
        decision_id: str,
        *,
        tenant_id: str,
        against_evidence_ids: list[str] | None = None,
    ) -> ReplayResult:
        record = self._store.get(decision_id)
        if record is None:
            raise MetricError(decision_id, "decision not found in evaluation store")

        original_metrics = record["metrics"]
        evidence_changed = bool(against_evidence_ids) or original_metrics.evidence_count > 0

        replayed_metrics = EvaluationMetrics(
            decision_id=decision_id,
            goal_id=original_metrics.goal_id,
            confidence_score=max(0.0, original_metrics.confidence_score + 0.05),
            feasibility_score=original_metrics.feasibility_score,
            evidence_count=len(against_evidence_ids) if against_evidence_ids else original_metrics.evidence_count,
            options_count=original_metrics.options_count,
            tradeoffs_count=original_metrics.tradeoffs_count,
            evaluated_at=self._utcnow(),
        )

        delta = replayed_metrics.confidence_score - original_metrics.confidence_score

        result = ReplayResult(
            decision_id=decision_id,
            original_analysis=None,  # could be fetched from DecisionRuntime
            new_analysis=None,
            confidence_delta=delta,
            evidence_changed=evidence_changed,
            replayed_at=self._utcnow(),
        )
        logger.info(
            "Replayed decision %s: delta=%.2f, evidence_changed=%s",
            decision_id, delta, evidence_changed,
        )
        return result

    async def golden_dataset(
        self,
        *,
        goal_id: str | None = None,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        results = []
        for decision_id, record in self._store.items():
            if goal_id and record.get("goal_id") != goal_id:
                continue
            metrics = record["metrics"]
            actual = record.get("actual_result")
            results.append({
                "decision_id": decision_id,
                "goal_id": record.get("goal_id"),
                "original_confidence": metrics.confidence_score,
                "actual_outcome": actual,
                "evidence_count": metrics.evidence_count,
                "evaluated_at": metrics.evaluated_at.isoformat(),
                "has_accuracy_label": actual is not None,
            })
        return results


# ── Factory ─�───────────────────────────────────────────────────────────


def get_evaluation_runtime() -> DefaultEvaluationRuntime:
    """Return the default EvaluationRuntime instance."""
    return DefaultEvaluationRuntime()


__all__ = [
    "EvaluationRuntime",
    "BaseEvaluationRuntime",
    "DefaultEvaluationRuntime",
    "EvaluationRuntimeError",
    "MetricError",
    "RecordingError",
    "EvaluationMetrics",
    "ReplayResult",
    "get_evaluation_runtime",
]
