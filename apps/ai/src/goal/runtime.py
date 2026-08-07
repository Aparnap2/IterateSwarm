# FROZEN — V6.0 M0.5
"""OntologyAI V6 — Goal Runtime Interface (Protocol + Base).

The Goal Runtime is the conceptual centre of the platform.  Each Goal is a
persistent business objective (e.g. *"Reduce Enterprise Churn"*) that agents
continuously advance by observing evidence, evaluating KPI progress,
generating plans, and triggering decisions.

Unlike the other runtimes which use ABCs, this module follows the
**Protocol + Base + Default** pattern recommended for V6:

```
GoalRuntime Protocol     ← structural contract (isinstance-capable)
        ↓
BaseGoalRuntime          ← shared logic / utilities
        ↓
DefaultGoalRuntime       ← production implementation wrapping
                          ← DecisionEngine, SemanticLayer, memory
```

Pipeline stages
---------------
1. **create** — Register a new business Goal with KPIs.
2. **evaluate** — Continuously assess goal progress from observations.
3. **advance** — Generate / update plans when goals stall or need action.
4. **review** — Periodic review: score KPIs, update confidence, trigger replan.
5. **archive** — Mark completed / failed / retired goals.

Design constraints
------------------
* Goals are **persistent** — they survive across sessions and system restarts.
* Evaluation is **continuous** — triggered by new evidence events.
* The runtime delegates decision generation to the **Decision Runtime**
  (via ``DecisionEngine``) when a plan requires a formal recommendation.
* Memory of past observations and decisions lives in the **Memory Runtime**.

FROZEN — V6.0 M0.5
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from src.decision.decision_engine import DecisionEngine
from src.decision.contracts import ReadinessTier
from src.entities.models import EvidenceRecord
from src.goal.models import (
    Goal,
    GoalKPI,
    GoalObservation,
    GoalPlan,
    GoalProgress,
    GoalReview,
    GoalStatus,
    ObservationType,
)

logger = logging.getLogger(__name__)


# ── Error hierarchy ──────────────────────────────────────────────────────


class GoalRuntimeError(Exception):
    """Base exception for all Goal Runtime failures."""


class GoalError(GoalRuntimeError):
    """Raised when a Goal cannot be created, found, or updated.

    Parameters
    ----------
    goal_id : str
        The Goal identifier.
    reason : str
        Explanation.
    """

    def __init__(self, goal_id: str, reason: str) -> None:
        self.goal_id = goal_id
        self.reason = reason
        super().__init__(f"Goal '{goal_id}': {reason}")


class EvaluationError(GoalRuntimeError):
    """Raised when continuous goal evaluation fails.

    Parameters
    ----------
    goal_id : str
        The Goal identifier.
    reason : str
        Explanation.
    """

    def __init__(self, goal_id: str, reason: str) -> None:
        self.goal_id = goal_id
        self.reason = reason
        super().__init__(f"Evaluation failed for goal '{goal_id}': {reason}")


class PlanError(GoalRuntimeError):
    """Raised when plan generation or advancement fails.

    Parameters
    ----------
    goal_id : str
        The Goal identifier.
    reason : str
        Explanation.
    """

    def __init__(self, goal_id: str, reason: str) -> None:
        self.goal_id = goal_id
        self.reason = reason
        super().__init__(f"Plan failed for goal '{goal_id}': {reason}")


class ReviewError(GoalRuntimeError):
    """Raised when a periodic review fails.

    Parameters
    ----------
    goal_id : str
        The Goal identifier.
    reason : str
        Explanation.
    """

    def __init__(self, goal_id: str, reason: str) -> None:
        self.goal_id = goal_id
        self.reason = reason
        super().__init__(f"Review failed for goal '{goal_id}': {reason}")


# ── Protocol (structural contract) ────────────────────────────────────────


@runtime_checkable
class GoalRuntime(Protocol):
    """Frozen interface for the Goal Runtime.

    Every implementation must satisfy this Protocol.

    Pipeline stages:
        1. ``create``    — Register a new business Goal with KPIs.
        2. ``evaluate``  — Assess goal progress from evidence observations.
        3. ``advance``   — Generate or update a plan for the goal.
        4. ``review``    — Periodic review: KPIs, confidence, replan trigger.
        5. ``archive``   — Mark the goal completed / failed / archived.

    FROZEN — V6.0 M0.5 — Do not modify this interface.
    """

    async def create(
        self,
        tenant_id: str,
        owner_id: str,
        title: str,
        description: str = "",
        kpis: list[GoalKPI] | None = None,
        *,
        review_interval_days: int = 7,
        metadata: dict[str, Any] | None = None,
    ) -> Goal:
        """Register a new Goal.

        Parameters
        ----------
        tenant_id : str
        owner_id : str
        title : str
        description : str
        kpis : list[GoalKPI] | None
            KPIs to track for this goal. At least one is recommended.
        review_interval_days : int
            How often (in days) to auto-review.
        metadata : dict[str, Any] | None

        Returns
        -------
        Goal
            The newly created Goal.

        Raises
        ------
        GoalError
            If the Goal cannot be created.
        """
        ...

    async def evaluate(
        self,
        goal_id: str,
        *,
        evidence: list[EvidenceRecord] | None = None,
        tenant_id: str,
    ) -> GoalProgress:
        """Evaluate progress on a Goal from new evidence.

        Ingests any provided evidence records as observations, updates
        KPI current values, and returns a aggregated progress snapshot.

        Parameters
        ----------
        goal_id : str
        evidence : list[EvidenceRecord] | None
            New evidence to evaluate (may be empty for a re-evaluation).
        tenant_id : str

        Returns
        -------
        GoalProgress

        Raises
        ------
        GoalError
            If the goal is not found.
        EvaluationError
            If evaluation cannot be performed.
        """
        ...

    async def advance(
        self,
        goal_id: str,
        *,
        tenant_id: str,
        force_replan: bool = False,
    ) -> GoalPlan | None:
        """Generate or update a Plan to advance a Goal.

        Delegates to the Decision Runtime (DecisionEngine) when the goal
        needs action. Returns ``None`` if no plan is needed (goal is on
        track or cannot be advanced).

        Parameters
        ----------
        goal_id : str
        force_replan : bool
            If True, discard the last plan and generate a new one.

        Returns
        -------
        GoalPlan | None
            The newly generated/updated plan, or None if not needed.

        Raises
        ------
        GoalError
        PlanError
        """
        ...

    async def review(
        self,
        goal_id: str,
        *,
        tenant_id: str,
        now: datetime | None = None,
    ) -> GoalReview:
        """Perform a periodic review of a Goal.

        Scores all KPIs, updates overall confidence, and triggers a
        replan if confidence has dropped or KPIs are trending away
        from targets.

        Parameters
        ----------
        goal_id : str
        now : datetime | None

        Returns
        -------
        GoalReview

        Raises
        ------
        GoalError
        ReviewError
        """
        ...

    async def archive(
        self,
        goal_id: str,
        *,
        tenant_id: str,
        reason: str = "",
    ) -> Goal:
        """Mark a Goal as archived (retired).

        Parameters
        ----------
        goal_id : str
        reason : str

        Returns
        -------
        Goal
            The archived Goal (status = ARCHIVED).

        Raises
        ------
        GoalError
        """
        ...

    async def get(self, goal_id: str, *, tenant_id: str) -> Goal:
        """Retrieve a Goal by ID.

        Parameters
        ----------
        goal_id : str
        tenant_id : str

        Returns
        -------
        Goal

        Raises
        ------
        GoalError
            If the goal is not found.
        """
        ...

    async def list_active(
        self,
        *,
        tenant_id: str,
    ) -> list[Goal]:
        """List all ACTIVE goals for a tenant.

        Parameters
        ----------
        tenant_id : str

        Returns
        -------
        list[Goal]
        """
        ...


# ── Base implementation (shared logic) ──────────────────────────────────


class BaseGoalRuntime:
    """Shared logic for GoalRuntime implementations.

    Provides:
    - In-memory goal store (fallback when Postgres is unavailable).
    - Deterministic KPI scoring helper.
    - Confidence computation from KPI progress.
    - Evidence-to-observation conversion.

    Subclasses should still implement the full Protocol, but can call
    ``super()`` methods for shared utilities.
    """

    def __init__(self, decision_engine: DecisionEngine | None = None) -> None:
        self._decision_engine = decision_engine or DecisionEngine()
        self._store: dict[str, Goal] = {}

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _kpi_confidence(self, kpi: GoalKPI) -> float:
        """Compute confidence in a KPI based on current vs target.

        Uses direction-aware progress: 'decrease' means lower is better.
        """
        if kpi.current_value is None:
            return 0.0
        baseline = kpi.baseline_value
        target = kpi.target_value
        current = kpi.current_value
        total_span = abs(target - baseline)
        if total_span == 0:
            return 1.0
        if kpi.direction == "decrease":
            progress = (baseline - current) / total_span
        else:
            progress = (current - baseline) / total_span
        return max(0.0, min(1.0, progress))

    def _goal_confidence(self, goal: Goal) -> float:
        """Compute overall goal confidence from KPI confidences."""
        if not goal.kpis:
            return 0.0
        scores = [self._kpi_confidence(k) for k in goal.kpis]
        return sum(scores) / len(scores) if scores else 0.0

    def _observation_from_evidence(
        self,
        goal: Goal,
        evidence: EvidenceRecord,
    ) -> GoalObservation:
        """Convert an EvidenceRecord into a GoalObservation."""
        return GoalObservation(
            id=f"obs-{evidence.id}",
            goal_id=goal.id,
            type=ObservationType.EVENT,
            source=evidence.source,
            content=evidence.raw_content or evidence.structured_data.get(
                "summary", ""
            ),
            evidence_ids=[evidence.id],
            confidence=evidence.confidence,
            timestamp=evidence.timestamp,
        )

    def _should_replan(self, goal: Goal) -> bool:
        """Deterministic check: does the goal need a new plan?"""
        # Recompute confidence from current KPI state (don't trust cached)
        live_conf = self._goal_confidence(goal)
        if live_conf < 0.3:
            return True
        if not goal.kpis:
            return False
        for kpi in goal.kpis:
            k = self._kpi_confidence(kpi)
            if k < 0.2:
                return True
        return False


# ── Default implementation ────────────────────────────────────────────────


class DefaultGoalRuntime(BaseGoalRuntime):
    """Default Goal Runtime — in-memory store with DecisionEngine integration.

    At M0.5 this uses an in-memory dict for persistence (no Postgres).
    The store is partitioned by tenant_id.

    For production, replace with a Postgres-backed implementation that
    uses the same Protocol interface.
    """

    async def create(
        self,
        tenant_id: str,
        owner_id: str,
        title: str,
        description: str = "",
        kpis: list[GoalKPI] | None = None,
        *,
        review_interval_days: int = 7,
        metadata: dict[str, Any] | None = None,
    ) -> Goal:
        from uuid import uuid4

        goal_id = f"goal_{uuid4().hex[:12]}"
        now = self._utcnow()
        goal = Goal(
            id=goal_id,
            tenant_id=tenant_id,
            title=title,
            description=description,
            owner_id=owner_id,
            status=GoalStatus.ACTIVE,
            kpis=kpis or [],
            next_review_at=now.replace(
                hour=0, minute=0, second=0,
                microsecond=0,
            ),
            confidence=0.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        self._store[goal_id] = goal
        logger.info("Created goal %s: %s", goal_id, title)
        return goal

    async def evaluate(
        self,
        goal_id: str,
        *,
        evidence: list[EvidenceRecord] | None = None,
        tenant_id: str,
    ) -> GoalProgress:
        goal = await self.get(goal_id, tenant_id=tenant_id)

        if evidence:
            for ev in evidence:
                obs = self._observation_from_evidence(goal, ev)
                goal.observations.append(obs)

        goal.confidence = self._goal_confidence(goal)
        goal.updated_at = self._utcnow()

        kpi_scores = {k.name: k.current_value or 0.0 for k in goal.kpis}
        return GoalProgress(
            goal_id=goal_id,
            kpi_scores=kpi_scores,
            confidence=goal.confidence,
            status=goal.status,
            next_review_at=goal.next_review_at,
        )

    async def advance(
        self,
        goal_id: str,
        *,
        tenant_id: str,
        force_replan: bool = False,
    ) -> GoalPlan | None:
        goal = await self.get(goal_id, tenant_id=tenant_id)

        if not force_replan and not self._should_replan(goal):
            return None

        from uuid import uuid4

        plan = GoalPlan(
            id=f"plan_{uuid4().hex[:12]}",
            goal_id=goal_id,
            title=f"Advance: {goal.title}",
            description=(
                f"Plan generated to advance goal '{goal.title}'. "
                f"Current confidence: {goal.confidence:.2f}"
            ),
            steps=[
                "Review latest evidence",
                "Identify root cause",
                "Generate options",
                "Evaluate tradeoffs",
                "Select recommendation",
            ],
            confidence=goal.confidence,
            created_at=self._utcnow(),
            status="proposed",
        )
        goal.plans.append(plan)
        logger.info("Generated plan %s for goal %s", plan.id, goal_id)

        try:
            decision = await self._decision_engine.create_decision(
                workspace_id=goal_id,
                title=f"How to advance: {goal.title}",
                description=goal.description,
                evidence_ids=[
                    obs.evidence_ids[0]
                    for obs in goal.observations[-5:]
                    if obs.evidence_ids
                ],
            )
            plan.decision_id = decision.id
        except Exception as e:
            logger.warning("Could not create decision for plan: %s", e)

        return plan

    async def review(
        self,
        goal_id: str,
        *,
        tenant_id: str,
        now: datetime | None = None,
    ) -> GoalReview:
        goal = await self.get(goal_id, tenant_id=tenant_id)
        now = now or self._utcnow()

        kpi_scores = {}
        for kpi in goal.kpis:
            kpi.current_value = kpi.current_value or kpi.baseline_value
            kpi_scores[kpi.name] = kpi.current_value

        prev_confidence = goal.confidence
        goal.confidence = self._goal_confidence(goal)
        goal.updated_at = now

        triggered_replan = goal.confidence < prev_confidence - 0.1

        review = GoalReview(
            id=f"rev_{goal_id[-12:]}_{int(now.timestamp())}",
            goal_id=goal_id,
            timestamp=now,
            kpi_scores=kpi_scores,
            goal_confidence=goal.confidence,
            recommendation=(
                "Continue monitoring" if goal.confidence >= 0.5
                else "Intervention required"
            ),
            triggered_replan=triggered_replan,
        )
        goal.reviews.append(review)
        goal.updated_at = now

        if goal.confidence >= 0.9:
            goal.status = GoalStatus.COMPLETED
            goal.next_review_at = None
        elif triggered_replan:
            await self.advance(goal_id, tenant_id=tenant_id, force_replan=True)

        self._store[goal_id] = goal
        return review

    async def archive(
        self,
        goal_id: str,
        *,
        tenant_id: str,
        reason: str = "",
    ) -> Goal:
        goal = await self.get(goal_id, tenant_id=tenant_id)
        goal.status = GoalStatus.ARCHIVED
        goal.metadata["archive_reason"] = reason
        goal.updated_at = self._utcnow()
        self._store[goal_id] = goal
        return goal

    async def get(self, goal_id: str, *, tenant_id: str) -> Goal:
        goal = self._store.get(goal_id)
        if goal is None:
            raise GoalError(goal_id, "not found")
        if goal.tenant_id != tenant_id:
            raise GoalError(goal_id, "tenant mismatch")
        return goal

    async def list_active(
        self,
        *,
        tenant_id: str,
    ) -> list[Goal]:
        return [
            g for g in self._store.values()
            if g.tenant_id == tenant_id and g.status == GoalStatus.ACTIVE
        ]


# ── Factory ──────────────────────────────────────────────────────────────


def get_goal_runtime(
    decision_engine: DecisionEngine | None = None,
) -> DefaultGoalRuntime:
    """Return the default GoalRuntime instance.

    Usage::

        from src.goal import get_goal_runtime

        runtime = get_goal_runtime()
        goal = await runtime.create(
            tenant_id="t1", owner_id="u1",
            title="Reduce churn",
            kpis=[GoalKPI(...)],
        )
    """
    return DefaultGoalRuntime(decision_engine=decision_engine)


__all__ = [
    "GoalRuntime",
    "BaseGoalRuntime",
    "DefaultGoalRuntime",
    "GoalRuntimeError",
    "GoalError",
    "EvaluationError",
    "PlanError",
    "ReviewError",
    "get_goal_runtime",
]
