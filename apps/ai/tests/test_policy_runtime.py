"""Tests for Policy Runtime (V6 M0.5).

These are deterministic tests — no LLM required.
They validate the PolicyRuntime Protocol, BasePolicyRuntime, and
DefaultPolicyRuntime implementation.

Run:
    cd apps/ai
    uv run pytest tests/test_policy_runtime.py -v -s
"""

from __future__ import annotations

import pytest

from src.policy.runtime import (
    BasePolicyRuntime,
    DefaultPolicyRuntime,
    PolicyDecision,
    PolicyEvaluationError,
    PolicyResult,
    PolicyRuntime,
    PolicyRuntimeError,
    PolicyViolationError,
    get_policy_runtime,
)
from src.decision.contracts import (
    DecisionAnalysis,
    DecisionOption,
    TradeOff,
    ReadinessTier,
)
from src.goal.models import Goal, GoalKPI, GoalStatus


def _make_analysis(
    decision_id: str = "dec_001",
    confidence: float = 0.75,
    recommendation: str = "opt_a",
) -> DecisionAnalysis:
    """Helper to build a minimal DecisionAnalysis for tests."""
    return DecisionAnalysis(
        decision_id=decision_id,
        tenant_id="t1",
        workspace_id="ws_001",
        root_cause="Resource constraints",
        options=[
            DecisionOption(option_id="opt_a", title="Option A", description="Do A"),
            DecisionOption(option_id="opt_b", title="Option B", description="Do B"),
        ],
        tradeoffs=[
            TradeOff(
                option_a_id="opt_a",
                option_b_id="opt_b",
                dimension="cost",
                a_score=60.0,
                b_score=40.0,
                delta=20.0,
            ),
        ],
        recommended_option_id=recommendation,
        rationale="Option A has better tradeoff profile",
        confidence=confidence,
        impact_summary="Improved resource allocation",
    )


def _make_goal(
    goal_id: str = "goal_001",
    status: GoalStatus = GoalStatus.ACTIVE,
    confidence: float = 0.5,
) -> Goal:
    """Helper to build a minimal Goal for tests."""
    return Goal(
        id=goal_id,
        tenant_id="t1",
        title="Test Goal",
        description="A test goal",
        owner_id="u1",
        status=status,
        kpis=[
            GoalKPI(
                id="kpi_001",
                goal_id=goal_id,
                name="Test KPI",
                target_value=100,
                baseline_value=0,
                current_value=50,
                unit="count",
                direction="increase",
            )
        ],
        confidence=confidence,
    )


class TestPolicyProtocol:
    """Test the PolicyRuntime Protocol."""

    def test_protocol_is_runtime_checkable(self):
        """PolicyRuntime should be a runtime_checkable Protocol."""
        assert hasattr(PolicyRuntime, "_is_runtime_protocol")
        assert PolicyRuntime._is_runtime_protocol  # noqa: SLF001

    def test_default_runtime_is_policy_runtime(self):
        """DefaultPolicyRuntime should satisfy the Protocol."""
        runtime = DefaultPolicyRuntime()
        assert isinstance(runtime, PolicyRuntime)

    def test_factory_returns_runtime(self):
        """get_policy_runtime should return a DefaultPolicyRuntime."""
        runtime = get_policy_runtime()
        assert isinstance(runtime, DefaultPolicyRuntime)
        assert isinstance(runtime, PolicyRuntime)


class TestPolicyEvaluation:
    """Test policy evaluation based on confidence tiers."""

    @pytest.fixture
    def runtime(self):
        return DefaultPolicyRuntime()

    @pytest.fixture
    def goal(self):
        return _make_goal()

    @pytest.mark.asyncio
    async def test_evaluate_high_confidence(self, runtime):
        """Test that high confidence (>=0.8) → ALLOW."""
        analysis = _make_analysis(confidence=0.85)
        result = await runtime.evaluate(analysis, tenant_id="t1")

        assert result.decision == PolicyDecision.ALLOW
        assert result.readiness_tier == ReadinessTier.PUBLISH
        assert result.recommendation == "opt_a"

    @pytest.mark.asyncio
    async def test_evaluate_medium_high_confidence(self, runtime):
        """Test 0.5 <= conf < 0.8 → CAVEAT → REVIEW."""
        analysis = _make_analysis(confidence=0.6)
        result = await runtime.evaluate(analysis, tenant_id="t1")

        assert result.decision == PolicyDecision.REVIEW
        assert result.readiness_tier == ReadinessTier.CAVEAT

    @pytest.mark.asyncio
    async def test_evaluate_medium_low_confidence(self, runtime, goal):
        """Test 0.3 <= conf < 0.5 → REVIEW."""
        analysis = _make_analysis(confidence=0.35)
        result = await runtime.evaluate(analysis, goal=goal, tenant_id="t1")

        assert result.decision == PolicyDecision.REVIEW
        assert result.readiness_tier == ReadinessTier.REVIEW

    @pytest.mark.asyncio
    async def test_evaluate_low_confidence(self, runtime):
        """Test confidence < 0.3 → BLOCK."""
        analysis = _make_analysis(confidence=0.15)
        result = await runtime.evaluate(analysis, tenant_id="t1")

        assert result.decision == PolicyDecision.BLOCK
        assert result.readiness_tier == ReadinessTier.BLOCK

    @pytest.mark.asyncio
    async def test_evaluate_stalled_goal_overrides_to_review(self, runtime):
        """Test that a stalled goal overrides confidence to REVIEW."""
        goal = _make_goal(status=GoalStatus.STALLED)
        analysis = _make_analysis(confidence=0.9)

        result = await runtime.evaluate(analysis, goal=goal, tenant_id="t1")

        # Stalled goal → REVIEW regardless of confidence
        assert result.readiness_tier == ReadinessTier.REVIEW

    @pytest.mark.asyncio
    async def test_evaluate_no_recommendation(self, runtime):
        """Test that missing recommendation raises PolicyEvaluationError."""
        analysis = _make_analysis(recommendation="")
        with pytest.raises(PolicyEvaluationError, match="no recommended option"):
            await runtime.evaluate(analysis, tenant_id="t1")


class TestPolicyPermit:
    """Test action permission checks."""

    @pytest.fixture
    def runtime(self):
        return DefaultPolicyRuntime()

    @pytest.mark.asyncio
    async def test_permit_allowed_action(self, runtime):
        """Test that ALLOW permits actions."""
        analysis = _make_analysis(confidence=0.9)
        await runtime.evaluate(analysis, tenant_id="t1")

        result = await runtime.permit(
            "execute", "dec_001", tenant_id="t1", reason="within policy"
        )
        assert result.decision == PolicyDecision.ALLOW

    @pytest.mark.asyncio
    async def test_permit_blocked_action(self, runtime):
        """Test that BLOCK raises PolicyViolationError."""
        analysis = _make_analysis(confidence=0.1)
        await runtime.evaluate(analysis, tenant_id="t1")

        with pytest.raises(PolicyViolationError, match="blocked"):
            await runtime.permit("execute", "dec_001", tenant_id="t1")

    @pytest.mark.asyncio
    async def test_permit_without_prior_evaluation(self, runtime):
        """Test that permit without prior evaluation raises error."""
        with pytest.raises(PolicyEvaluationError, match="no prior"):
            await runtime.permit("execute", "unknown", tenant_id="t1")


class TestPolicyRecord:
    """Test policy decision recording for audit."""

    @pytest.fixture
    def runtime(self):
        return DefaultPolicyRuntime()

    @pytest.mark.asyncio
    async def test_record_appends_to_audit(self, runtime):
        """Test that record() persists the policy decision."""
        analysis = _make_analysis(confidence=0.7)
        result = await runtime.evaluate(analysis, tenant_id="t1")

        recorded = await runtime.record(result, tenant_id="t1")
        assert recorded.decision_id == result.decision_id

    @pytest.mark.asyncio
    async def test_audit_trail_grows(self, runtime):
        """Test that multiple evaluations create an audit trail."""
        for i in range(3):
            analysis = _make_analysis(
                decision_id=f"dec_{i}",
                confidence=0.8 + (i * 0.05),  # 0.8, 0.85, 0.9 → all ALLOW
            )
            result = await runtime.evaluate(analysis, tenant_id="t1")
            await runtime.record(result, tenant_id="t1")

        # Verify audit trail has 3 entries for tenant t1
        # (We can verify indirectly by checking permit works for known IDs)
        for i in range(3):
            result = await runtime.permit("execute", f"dec_{i}", tenant_id="t1")
            assert result.decision == PolicyDecision.ALLOW


class TestPolicyResult:
    """Test the PolicyResult value object."""

    def test_repr(self):
        """Test that PolicyResult has a readable repr."""
        from datetime import datetime, timezone

        result = PolicyResult(
            decision_id="dec_001",
            recommendation="opt_a",
            decision=PolicyDecision.ALLOW,
            rationale="High confidence",
            confidence=0.9,
            readiness_tier=ReadinessTier.PUBLISH,
            evaluated_at=datetime.now(timezone.utc),
        )

        repr_str = repr(result)
        assert "dec_001" in repr_str
        assert "allow" in repr_str
        assert "publish" in repr_str
