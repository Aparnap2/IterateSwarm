# FROZEN — V6.0 M0.5
"""OntologyAI V6 — Policy Runtime Interface (Protocol + Base).

The Policy Runtime provides **governance gating** between the Decision Runtime
and the Workspace Runtime.  Even at M0.5 it enforces basic safety checks so
that recommendations are properly tiered before reaching a human.

Pipeline stages
---------------
1. **evaluate** — Determine ALLOW / REVIEW / BLOCK for a recommendation.
2. **permit**   — Check a specific action against policy constraints.
3. **record**   — Persist the policy decision for audit.

This is intentionally minimal at M0.5.  The interface is frozen so that
upstream consumers can compile against it, and a richer policy engine can
be swapped in later without changing callers.

Design constraints
------------------
* ``evaluate()`` is deterministic — no LLM calls.
* Policy rules are code, not prompts.
* All decisions are append-only (audit trail).

FROZEN — V6.0 M0.5
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from src.decision.contracts import DecisionAnalysis, ReadinessTier
from src.goal.models import Goal

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────


class PolicyDecision(str, Enum):
    """Governance gating tier for a recommendation."""

    ALLOW = "allow"  # Proceed without human review
    REVIEW = "review"  # Requires human approval
    BLOCK = "block"  # Must not proceed


# ── Error hierarchy ──────────────────────────────────────────────────────


class PolicyRuntimeError(Exception):
    """Base exception for all Policy Runtime failures."""


class PolicyEvaluationError(PolicyRuntimeError):
    """Raised when policy evaluation fails.

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
        super().__init__(f"Policy evaluation failed for '{decision_id}': {reason}")


class PolicyViolationError(PolicyRuntimeError):
    """Raised when an action violates policy (BLOCK).

    Parameters
    ----------
    decision_id : str
    action : str
    reason : str
    """

    def __init__(self, decision_id: str, action: str, reason: str) -> None:
        self.decision_id = decision_id
        self.action = action
        self.reason = reason
        super().__init__(
            f"Policy violation: action '{action}' blocked for "
            f"decision '{decision_id}': {reason}"
        )


# ── Value Objects ─────────────────────────────────────────────────────────


class PolicyResult:
    """Result of a policy evaluation.

    Parameters
    ----------
    decision_id : str
    recommendation : str
        The recommended option_id.
    decision : PolicyDecision
        ALLOW / REVIEW / BLOCK.
    rationale : str
        Why this tier was assigned.
    confidence : float
        Confidence in the policy decision (0.0–1.0).
    readiness_tier : ReadinessTier
        Maps to the Decision Runtime readiness tier.
    evaluated_at : datetime
    """

    __slots__ = (
        "decision_id",
        "recommendation",
        "decision",
        "rationale",
        "confidence",
        "readiness_tier",
        "evaluated_at",
    )

    def __init__(
        self,
        decision_id: str,
        recommendation: str,
        decision: PolicyDecision,
        rationale: str,
        confidence: float,
        readiness_tier: ReadinessTier,
        evaluated_at: datetime,
    ) -> None:
        self.decision_id = decision_id
        self.recommendation = recommendation
        self.decision = decision
        self.rationale = rationale
        self.confidence = confidence
        self.readiness_tier = readiness_tier
        self.evaluated_at = evaluated_at

    def __repr__(self) -> str:
        return (
            f"PolicyResult(decision={self.decision_id!r}, "
            f"action={self.decision.value!r}, "
            f"tier={self.readiness_tier.value!r}, "
            f"conf={self.confidence:.2f})"
        )


# ── Protocol ───────────────────────────────────────────────────────────


@runtime_checkable
class PolicyRuntime(Protocol):
    """Frozen interface for the Policy Runtime.

    Provides governance gating between Decision Runtime and Workspace.

    Pipeline stages:
        1. ``evaluate`` — ALLOW / REVIEW / BLOCK for a recommendation.
        2. ``permit``   — Check a specific action against constraints.
        3. ``record``   — Persist the policy decision for audit.

    FROZEN — V6.0 M0.5 — Do not modify this interface.
    """

    async def evaluate(
        self,
        analysis: DecisionAnalysis,
        *,
        goal: Goal | None = None,
        tenant_id: str,
    ) -> PolicyResult:
        """Evaluate a recommendation against policy rules.

        Parameters
        ----------
        analysis : DecisionAnalysis
            The completed analysis with recommendation.
        goal : Goal | None
            The Goal this decision advances (if any).
        tenant_id : str

        Returns
        -------
        PolicyResult
            ALLOW / REVIEW / BLOCK with rationale.

        Raises
        ------
        PolicyEvaluationError
        """
        ...

    async def permit(
        self,
        action: str,
        decision_id: str,
        *,
        tenant_id: str,
        reason: str = "",
    ) -> PolicyResult:
        """Check whether *action* is permitted for *decision_id*.

        Parameters
        ----------
        action : str
            The action to check (e.g. "execute", "notify", "export").
        decision_id : str
        tenant_id : str
        reason : str

        Returns
        -------
        PolicyResult

        Raises
        ------
        PolicyViolationError
            If the action is BLOCKed by policy.
        PolicyEvaluationError
        """
        ...

    async def record(
        self,
        policy_result: PolicyResult,
        *,
        tenant_id: str,
    ) -> PolicyResult:
        """Persist a policy decision for audit trail.

        Parameters
        ----------
        policy_result : PolicyResult
        tenant_id : str

        Returns
        -------
        PolicyResult
            The same result (possibly enriched with audit metadata).

        Raises
        ------
        PolicyRuntimeError
        """
        ...


# ── Base implementation ─────────────────────────────────────────────────


class BasePolicyRuntime:
    """Shared logic for PolicyRuntime implementations.

    Provides:
    - In-memory policy log.
    - Deterministic readiness-tier mapping.
    - Basic confidence thresholds.
    """

    def __init__(self) -> None:
        self._log: list[dict[str, Any]] = {}
        self._audit: dict[str, list[PolicyResult]] = {}

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _determines_tier(
        self,
        confidence: float,
        goal: Goal | None,
    ) -> ReadinessTier:
        """Map confidence + goal context to a readiness tier.

        Deterministic rules (no LLM):
        - confidence >= 0.8 → publish
        - confidence >= 0.5 → caveat
        - confidence >= 0.3 → review
        - confidence < 0.3 → block
        - goal status stalled → review
        """
        if goal and goal.status.value == "stalled":
            return ReadinessTier.REVIEW
        if confidence >= 0.8:
            return ReadinessTier.PUBLISH
        if confidence >= 0.5:
            return ReadinessTier.CAVEAT
        if confidence >= 0.3:
            return ReadinessTier.REVIEW
        return ReadinessTier.BLOCK

    def _maps_to_policy(
        self,
        readiness: ReadinessTier,
    ) -> PolicyDecision:
        """Map ReadinessTier to PolicyDecision."""
        mapping = {
            ReadinessTier.PUBLISH: PolicyDecision.ALLOW,
            ReadinessTier.CAVEAT: PolicyDecision.REVIEW,
            ReadinessTier.REVIEW: PolicyDecision.REVIEW,
            ReadinessTier.BLOCK: PolicyDecision.BLOCK,
        }
        return mapping.get(readiness, PolicyDecision.REVIEW)


# ── Default implementation ────────────────────────────────────────────────


class DefaultPolicyRuntime(BasePolicyRuntime):
    """Default in-memory Policy Runtime.

    At M0.5, implements basic confidence-threshold policy rules.
    """

    async def evaluate(
        self,
        analysis: DecisionAnalysis,
        *,
        goal: Goal | None = None,
        tenant_id: str,
    ) -> PolicyResult:
        if not analysis.recommended_option_id:
            raise PolicyEvaluationError(
                "unknown",
                "no recommended option in analysis",
            )

        readiness = self._determines_tier(analysis.confidence, goal)
        decision = self._maps_to_policy(readiness)

        rationale = (
            f"Confidence={analysis.confidence:.2f} → "
            f"ReadinessTier={readiness.value} → "
            f"PolicyDecision={decision.value}"
        )

        result = PolicyResult(
            decision_id=analysis.decision_id,
            recommendation=analysis.recommended_option_id,
            decision=decision,
            rationale=rationale,
            confidence=analysis.confidence,
            readiness_tier=readiness,
            evaluated_at=self._utcnow(),
        )

        self._audit.setdefault(tenant_id, []).append(result)
        logger.info(
            "Policy evaluation for decision %s: %s (%s)",
            analysis.decision_id,
            decision.value,
            readiness.value,
        )
        return result

    async def permit(
        self,
        action: str,
        decision_id: str,
        *,
        tenant_id: str,
        reason: str = "",
    ) -> PolicyResult:
        audit = self._audit.get(tenant_id, [])
        existing = [r for r in audit if r.decision_id == decision_id]

        if not existing:
            raise PolicyEvaluationError(
                decision_id,
                "no prior policy evaluation found",
            )

        last_result = existing[-1]
        if last_result.decision == PolicyDecision.BLOCK:
            raise PolicyViolationError(
                decision_id, action,
                f"action '{action}' blocked — prior decision was BLOCK: {reason}",
            )

        result = PolicyResult(
            decision_id=decision_id,
            recommendation=last_result.recommendation,
            decision=last_result.decision,
            rationale=f"Permit check for '{action}': {reason or 'within policy'}",
            confidence=last_result.confidence,
            readiness_tier=last_result.readiness_tier,
            evaluated_at=self._utcnow(),
        )
        self._audit.setdefault(tenant_id, []).append(result)
        return result

    async def record(
        self,
        policy_result: PolicyResult,
        *,
        tenant_id: str,
    ) -> PolicyResult:
        self._audit.setdefault(tenant_id, []).append(policy_result)
        logger.info(
            "Policy recorded for decision %s: %s",
            policy_result.decision_id,
            policy_result.decision.value,
        )
        return policy_result


# ── Factory ────────────────────────────────────────────────────────────


def get_policy_runtime() -> DefaultPolicyRuntime:
    """Return the default PolicyRuntime instance."""
    return DefaultPolicyRuntime()


__all__ = [
    "PolicyRuntime",
    "BasePolicyRuntime",
    "DefaultPolicyRuntime",
    "PolicyRuntimeError",
    "PolicyEvaluationError",
    "PolicyViolationError",
    "PolicyDecision",
    "PolicyResult",
    "get_policy_runtime",
]
