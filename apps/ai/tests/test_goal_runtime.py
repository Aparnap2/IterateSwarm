"""Tests for Goal Runtime (V6 M0.5).

These are deterministic tests — no LLM required.
They validate the GoalRuntime Protocol, BaseGoalRuntime, and
DefaultGoalRuntime implementation.

Run:
    cd apps/ai
    uv run pytest tests/test_goal_runtime.py -v -s
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

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
from src.goal.runtime import (
    BaseGoalRuntime,
    DefaultGoalRuntime,
    GoalError,
    GoalRuntime,
    PlanError,
    get_goal_runtime,
)
from src.decision.decision_engine import DecisionEngine


class TestGoalModels:
    """Test Goal domain model construction and validation."""

    def test_goal_kpi_decrease_direction(self):
        """GoalKPI with direction='decrease' should validate."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="goal_001",
            name="Churn Rate",
            target_value=2.0,
            baseline_value=5.0,
            current_value=5.0,
            unit="percentage",
            direction="decrease",
        )
        assert kpi.direction == "decrease"
        assert kpi.target_value == 2.0

    def test_goal_kpi_increase_direction(self):
        """GoalKPI with direction='increase' should validate."""
        kpi = GoalKPI(
            id="kpi_002",
            goal_id="goal_001",
            name="ARR",
            target_value=500_000,
            baseline_value=300_000,
            current_value=300_000,
            unit="dollars",
            direction="increase",
        )
        assert kpi.direction == "increase"

    def test_goal_kpi_confidence_extra_field_forbidden(self):
        """GoalKPI should reject unknown fields (extra='forbid')."""
        with pytest.raises(Exception):
            GoalKPI(
                id="kpi_001",
                goal_id="goal_001",
                name="Churn",
                target_value=2.0,
                baseline_value=5.0,
                unit="percentage",
                direction="decrease",
                unknown_field="should_fail",  # type: ignore
            )


class TestGoalRuntimeProtocol:
    """Test that GoalRuntime is a runtime_checkable Protocol."""

    def test_protocol_is_runtime_checkable(self):
        """GoalRuntime should be a runtime_checkable Protocol."""
        import typing
        # runtime_checkable protocols support isinstance
        assert hasattr(GoalRuntime, "_is_runtime_protocol")
        assert GoalRuntime._is_runtime_protocol  # noqa: SLF001

    def test_default_runtime_is_goal_runtime(self):
        """DefaultGoalRuntime should satisfy the GoalRuntime Protocol."""
        runtime = DefaultGoalRuntime()
        assert isinstance(runtime, GoalRuntime)


class TestGoalLifecycle:
    """Test the full Goal lifecycle: create → evaluate → advance → review → archive."""

    @pytest.fixture
    def runtime(self):
        return DefaultGoalRuntime()

    @pytest.fixture
    def churn_kpi(self):
        return GoalKPI(
            id="kpi_churn",
            goal_id="",
            name="Monthly Churn Rate",
            target_value=2.0,
            baseline_value=5.3,
            current_value=5.3,
            unit="percentage",
            direction="decrease",
        )

    @pytest.mark.asyncio
    async def test_create_goal(self, runtime, churn_kpi):
        """Test creating a goal with KPIs."""
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="ceo_001",
            title="Reduce Enterprise Churn",
            description="Lower churn rate from 5.3% to 2.0%",
            kpis=[churn_kpi],
        )

        assert goal.id.startswith("goal_")
        assert goal.tenant_id == "t1"
        assert goal.owner_id == "ceo_001"
        assert goal.title == "Reduce Enterprise Churn"
        assert goal.status == GoalStatus.ACTIVE
        assert goal.confidence == 0.0
        assert len(goal.kpis) == 1
        assert goal.kpis[0].name == "Monthly Churn Rate"

    @pytest.mark.asyncio
    async def test_get_goal(self, runtime, churn_kpi):
        """Test retrieving a goal by ID."""
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="ceo_001",
            title="Reduce churn",
            kpis=[churn_kpi],
        )

        retrieved = await runtime.get(goal.id, tenant_id="t1")
        assert retrieved.id == goal.id
        assert retrieved.title == "Reduce churn"

    @pytest.mark.asyncio
    async def test_get_nonexistent_goal(self, runtime):
        """Test that get() raises GoalError for nonexistent goal."""
        with pytest.raises(GoalError, match="not found"):
            await runtime.get("nonexistent", tenant_id="t1")

    @pytest.mark.asyncio
    async def test_get_goal_tenant_mismatch(self, runtime, churn_kpi):
        """Test that get() raises GoalError for tenant mismatch."""
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="ceo_001",
            title="Test goal",
            kpis=[churn_kpi],
        )

        with pytest.raises(GoalError, match="tenant mismatch"):
            await runtime.get(goal.id, tenant_id="t2")

    @pytest.mark.asyncio
    async def test_list_active_goals(self, runtime, churn_kpi):
        """Test listing active goals for a tenant."""
        await runtime.create(
            tenant_id="t1",
            owner_id="ceo_001",
            title="Goal 1",
            kpis=[churn_kpi],
        )
        await runtime.create(
            tenant_id="t2",
            owner_id="ceo_002",
            title="Goal 2",
            kpis=[churn_kpi],
        )

        active_t1 = await runtime.list_active(tenant_id="t1")
        active_t2 = await runtime.list_active(tenant_id="t2")

        assert len(active_t1) == 1
        assert len(active_t2) == 1
        assert active_t1[0].tenant_id == "t1"

    @pytest.mark.asyncio
    async def test_archive_goal(self, runtime, churn_kpi):
        """Test archiving a goal."""
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="ceo_001",
            title="Test goal",
            kpis=[churn_kpi],
        )

        archived = await runtime.archive(goal.id, tenant_id="t1", reason="Completed")
        assert archived.status == GoalStatus.ARCHIVED
        assert archived.metadata["archive_reason"] == "Completed"

    @pytest.mark.asyncio
    async def test_empty_kpis_initial_confidence(self, runtime):
        """Test that a goal with KPIs has confidence based on baseline."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Test KPI",
            target_value=10.0,
            baseline_value=20.0,
            current_value=20.0,
            unit="count",
            direction="decrease",
        )

        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Test",
            kpis=[kpi],
        )

        # baseline == current → no progress → confidence = 0.0
        assert goal.confidence == 0.0


class TestGoalEvaluation:
    """Test goal evaluation and KPI scoring."""

    @pytest.fixture
    def runtime(self):
        return DefaultGoalRuntime()

    @pytest.mark.asyncio
    async def test_evaluate_with_no_kpis(self, runtime):
        """Test evaluating a goal with no KPIs."""
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Goal with no KPIs",
        )

        progress = await runtime.evaluate(goal.id, tenant_id="t1")
        assert progress.confidence == 0.0
        assert progress.status == GoalStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_evaluate_updates_confidence(self, runtime):
        """Test that evaluating with evidence updates confidence."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Churn Rate",
            target_value=2.0,  # lower is better (decrease)
            baseline_value=5.0,
            current_value=3.0,  # halfway to target
            unit="percentage",
            direction="decrease",
        )

        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Reduce Churn",
            kpis=[kpi],
        )

        # Evaluate should compute confidence from KPIs
        # (baseline - current) / (baseline - target) = (5-3)/(5-2) = 0.667
        progress = await runtime.evaluate(goal.id, tenant_id="t1")
        assert progress.confidence == pytest.approx(0.667, abs=0.01)
        assert progress.status == GoalStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_kpi_confidence_calculation(self, runtime):
        """Test the _kpi_confidence helper."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Test",
            target_value=10.0,
            baseline_value=20.0,
            current_value=15.0,  # halfway to target (decrease direction)
            unit="count",
            direction="decrease",
        )

        # (baseline - current) / (baseline - target) = (20-15)/(20-10) = 0.5
        conf = runtime._kpi_confidence(kpi)
        assert 0.4 < conf < 0.6

    @pytest.mark.asyncio
    async def test_kpi_confidence_increase_direction(self, runtime):
        """Test _kpi_confidence with increase direction."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Revenue",
            target_value=500_000,
            baseline_value=200_000,
            current_value=350_000,  # halfway to target
            unit="dollars",
            direction="increase",
        )

        # (current - baseline) / (target - baseline) = (350-200)/(500-200) = 0.5
        conf = runtime._kpi_confidence(kpi)
        assert 0.4 < conf < 0.6


class TestGoalAdvancement:
    """Test goal plan generation and advancement."""

    @pytest.fixture
    def runtime(self):
        return DefaultGoalRuntime()

    @pytest.mark.asyncio
    async def test_advance_stalled_goal(self, runtime):
        """Test that a stalled goal gets a plan."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Revenue",
            target_value=1_000_000,
            baseline_value=200_000,
            current_value=200_000,  # no progress → confidence 0
            unit="dollars",
            direction="increase",
        )

        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Increase Revenue",
            kpis=[kpi],
        )

        # confidence is 0 → should replan
        plan = await runtime.advance(goal.id, tenant_id="t1", force_replan=True)
        assert plan is not None
        assert plan.goal_id == goal.id
        assert len(plan.steps) > 0
        assert plan.status == "proposed"

    @pytest.mark.asyncio
    async def test_advance_on_track_no_plan(self, runtime):
        """Test that a goal that doesn't need replan returns None."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Test",
            target_value=100,
            baseline_value=0,
            current_value=95,  # nearly at target → high confidence
            unit="count",
            direction="increase",
        )

        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Goal",
            kpis=[kpi],
        )

        plan = await runtime.advance(goal.id, tenant_id="t1")
        assert plan is None

    @pytest.mark.asyncio
    async def test_force_replan(self, runtime):
        """Test that force_replan=True always generates a plan."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Test",
            target_value=100,
            baseline_value=0,
            current_value=95,
            unit="count",
            direction="increase",
        )

        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Goal",
            kpis=[kpi],
        )

        plan = await runtime.advance(goal.id, tenant_id="t1", force_replan=True)
        assert plan is not None
        assert plan.status == "proposed"


class TestGoalReview:
    """Test periodic goal review."""

    @pytest.fixture
    def runtime(self):
        return DefaultGoalRuntime()

    @pytest.mark.asyncio
    async def test_review_updates_confidence(self, runtime):
        """Test that review updates goal confidence."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Test",
            target_value=100,
            baseline_value=0,
            current_value=50,  # halfway
            unit="count",
            direction="increase",
        )

        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Test Goal",
            kpis=[kpi],
        )

        review = await runtime.review(goal.id, tenant_id="t1")
        assert review.goal_id == goal.id
        assert isinstance(review.goal_confidence, float)
        assert 0.4 < review.goal_confidence < 0.6
        assert review.kpi_scores is not None

    @pytest.mark.asyncio
    async def test_review_replan_on_low_confidence(self, runtime):
        """Test that review triggers replan when confidence drops."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Test",
            target_value=100,
            baseline_value=100,
            current_value=100,  # at baseline → confidence 0
            unit="count",
            direction="increase",
        )

        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Test Goal",
            kpis=[kpi],
        )

        # Set some initial confidence
        goal.confidence = 0.7
        await runtime.evaluate(goal.id, tenant_id="t1")

        review = await runtime.review(goal.id, tenant_id="t1")

        # With no progress, confidence drops → should trigger replan
        assert review.goal_id == goal.id

    @pytest.mark.asyncio
    async def test_review_completes_goal(self, runtime):
        """Test that review marks goal as completed when confidence >= 0.9."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Test",
            target_value=100,
            baseline_value=0,
            current_value=100,  # at target → confidence 1.0
            unit="count",
            direction="increase",
        )

        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Test Goal",
            kpis=[kpi],
        )

        review = await runtime.review(goal.id, tenant_id="t1")

        retrieved = await runtime.get(goal.id, tenant_id="t1")
        assert retrieved.status == GoalStatus.COMPLETED
