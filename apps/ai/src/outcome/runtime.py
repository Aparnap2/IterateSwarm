# FROZEN — V6.0 M0.5
"""OntologyAI V6 — Outcome Runtime Interface (ABC) — Placeholder.

The Outcome Runtime is the **Layer 7** execution domain responsible for
recording decision execution results, comparing expected vs actual outcomes,
and updating confidence scores based on observed outcomes.

This module defines the **frozen contract** that all Outcome Runtime
implementations must satisfy.  It contains **no execution logic** — only
the abstract interface, type contracts, and error hierarchy.

**Status: Placeholder for M1.** The interface is frozen at M0.5 so that
upstream and downstream consumers can compile against it, but no
production implementation exists yet.

Pipeline stages
---------------
1. **record**  — Record decision execution result.
2. **compare** — Expected vs actual outcome.
3. **update**  — Update confidence scores based on outcomes.

Design constraints
------------------
* Outcome recording is append-only — historical results are never mutated.
* Confidence updates follow a Bayesian-style formula: posterior ∝
  likelihood × prior.  The exact formula is an implementation detail.
* All methods are ``async`` to support non-blocking database access.

FROZEN — V6.0 M0.5
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any


# ── Error hierarchy ──────────────────────────────────────────────────────


class OutcomeRuntimeError(Exception):
    """Base exception for all Outcome Runtime failures."""


class RecordingError(OutcomeRuntimeError):
    """Raised when a decision execution result cannot be recorded.

    Parameters
    ----------
    decision_id : str
        The decision ULID whose result could not be recorded.
    reason : str
        Human-readable explanation.
    """

    def __init__(self, decision_id: str, reason: str) -> None:
        self.decision_id = decision_id
        self.reason = reason
        super().__init__(
            f"Recording failed for decision '{decision_id}': {reason}"
        )


class ComparisonError(OutcomeRuntimeError):
    """Raised when expected vs actual outcome comparison fails.

    Parameters
    ----------
    decision_id : str
        The decision ULID.
    reason : str
        Human-readable explanation.
    """

    def __init__(self, decision_id: str, reason: str) -> None:
        self.decision_id = decision_id
        self.reason = reason
        super().__init__(
            f"Comparison failed for decision '{decision_id}': {reason}"
        )


class ConfidenceUpdateError(OutcomeRuntimeError):
    """Raised when confidence scores cannot be updated.

    Parameters
    ----------
    decision_id : str
        The decision ULID.
    reason : str
        Human-readable explanation.
    """

    def __init__(self, decision_id: str, reason: str) -> None:
        self.decision_id = decision_id
        self.reason = reason
        super().__init__(
            f"Confidence update failed for decision '{decision_id}': {reason}"
        )


# ── Value objects ────────────────────────────────────────────────────────


class OutcomeStatus(str, Enum):
    """Lifecycle status of a decision execution outcome."""

    RECORDED = "recorded"
    COMPARED = "compared"
    UPDATED = "updated"
    FAILED = "failed"


class ExecutionOutcome:
    """Record of a decision execution result.

    Parameters
    ----------
    decision_id : str
        The decision ULID.
    outcome_id : str
        Unique identifier for this outcome record.
    option_id : str
        The option that was executed.
    status : OutcomeStatus
        Current lifecycle status.
    actual_result : str
        Human-readable description of what actually happened.
    expected_result : str
        What was expected to happen (from the analysis).
    measured_metrics : dict[str, Any]
        Key metrics measured after execution (e.g. ``{"cost_actual": 12000}``).
    recorded_at : datetime
        When the outcome was recorded.
    compared_at : datetime | None
        When the outcome was compared to expectations.
    confidence_delta : float
        Change in confidence after outcome observation (positive = better).
    """

    __slots__ = (
        "decision_id",
        "outcome_id",
        "option_id",
        "status",
        "actual_result",
        "expected_result",
        "measured_metrics",
        "recorded_at",
        "compared_at",
        "confidence_delta",
    )

    def __init__(
        self,
        decision_id: str,
        outcome_id: str,
        option_id: str,
        status: OutcomeStatus,
        actual_result: str,
        expected_result: str,
        measured_metrics: dict[str, Any],
        recorded_at: datetime,
        compared_at: datetime | None = None,
        confidence_delta: float = 0.0,
    ) -> None:
        self.decision_id = decision_id
        self.outcome_id = outcome_id
        self.option_id = option_id
        self.status = status
        self.actual_result = actual_result
        self.expected_result = expected_result
        self.measured_metrics = measured_metrics
        self.recorded_at = recorded_at
        self.compared_at = compared_at
        self.confidence_delta = confidence_delta

    def __repr__(self) -> str:
        return (
            f"ExecutionOutcome(decision={self.decision_id!r}, "
            f"option={self.option_id!r}, status={self.status.value!r})"
        )


# ── Abstract Runtime Interface ───────────────────────────────────────────


class OutcomeRuntime(ABC):
    """Frozen interface for the Outcome Runtime (V6.0 M0.5) — Placeholder.

    Every implementation of this ABC must satisfy the three-stage pipeline:

    1. ``record``  — Record decision execution result.
    2. ``compare`` — Expected vs actual outcome.
    3. ``update``  — Update confidence scores based on outcomes.

    **Status: Placeholder for M1.** No production implementation exists yet.
    Implementations must raise ``OutcomeRuntimeError`` if called at M0.5
    unless a stub behaviour is explicitly configured.

    FROZEN — V6.0 M0.5 — Do not modify this interface.
    """

    @abstractmethod
    async def record(
        self,
        decision_id: str,
        option_id: str,
        actual_result: str,
        *,
        expected_result: str = "",
        measured_metrics: dict[str, Any] | None = None,
        tenant_id: str,
    ) -> ExecutionOutcome:
        """Record a decision execution result.

        Creates an append-only outcome record.  The ``outcome_id`` is
        generated by the implementation (e.g. ULID).

        Parameters
        ----------
        decision_id : str
            The decision ULID.
        option_id : str
            The option that was executed.
        actual_result : str
            Human-readable description of what actually happened.
        expected_result : str
            What was expected to happen (from the analysis).
        measured_metrics : dict[str, Any] | None
            Key metrics measured after execution.
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        ExecutionOutcome
            The recorded outcome with generated ``outcome_id``.

        Raises
        ------
        RecordingError
            If the outcome cannot be recorded.
        """
        ...

    @abstractmethod
    async def compare(
        self,
        outcome_id: str,
        *,
        tenant_id: str,
    ) -> ExecutionOutcome:
        """Compare expected vs actual outcome for a recorded result.

        Updates the outcome's ``compared_at`` timestamp and computes
        the ``confidence_delta`` based on the comparison.

        Parameters
        ----------
        outcome_id : str
            The outcome ULID to compare.
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        ExecutionOutcome
            The outcome with comparison results populated.

        Raises
        ------
        ComparisonError
            If the comparison cannot be performed (e.g. outcome not found).
        """
        ...

    @abstractmethod
    async def update(
        self,
        decision_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, float]:
        """Update confidence scores based on observed outcomes.

        Applies a Bayesian-style update to the confidence scores of the
        decision and its options based on the outcome comparison results.

        Parameters
        ----------
        decision_id : str
            The decision ULID whose confidence scores should be updated.
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        dict[str, float]
            Mapping of ``{option_id: new_confidence}`` for all options
            affected by the update.

        Raises
        ------
        ConfidenceUpdateError
            If the update cannot be performed.
        """
        ...


__all__ = [
    "OutcomeRuntime",
    "OutcomeRuntimeError",
    "RecordingError",
    "ComparisonError",
    "ConfidenceUpdateError",
    "OutcomeStatus",
    "ExecutionOutcome",
]
