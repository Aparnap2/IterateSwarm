"""Tests for Evaluation Runtime (V6 M0.5).

These are deterministic tests — no LLM required.
They validate the EvaluationRuntime Protocol, BaseEvaluationRuntime, and
DefaultEvaluationRuntime implementation.

Run:
    cd apps/ai
    uv run pytest tests/test_evaluation_runtime.py -v -s
"""

from __future__ import annotations

import pytest

from src.evaluation.runtime import (
    BaseEvaluationRuntime,
    DefaultEvaluationRuntime,
    EvaluationRuntime,
    EvaluationMetrics,
    MetricError,
    ReplayResult,
    get_evaluation_runtime,
)
from src.decision.contracts import (
    DecisionAnalysis,
    DecisionOption,
    DecisionContext,
    ReadinessTier,
    TradeOff,
    RiskAssessment,
)
from src.decision.contracts import Runtime


class TestEvaluationProtocol:
    """Test the EvaluationRuntime Protocol."""

    def test_protocol_is_runtime_checkable(self):
        """EvaluationRuntime should be a runtime_checkable Protocol."""
        assert hasattr(EvaluationRuntime, "_is_runtime_protocol")
        assert EvaluationRuntime._is_runtime_protocol  # noqa: SLF001

    def test_default_runtime_is_evaluation_runtime(self):
        """DefaultEvaluationRuntime should satisfy the Protocol."""
        runtime = DefaultEvaluationRuntime()
        assert isinstance(runtime, EvaluationRuntime)

    def test_factory_returns_runtime(self):
        """get_evaluation_runtime should return a DefaultEvaluationRuntime."""
        runtime = get_evaluation_runtime()
        assert isinstance(runtime, DefaultEvaluationRuntime)
        assert isinstance(runtime, EvaluationRuntime)


def _make_analysis(
    decision_id: str = "dec_001",
    confidence: float = 0.75,
    options: list[DecisionOption] | None = None,
    tradeoffs: list[TradeOff] | None = None,
    evidence=None,
) -> DecisionAnalysis:
    """Helper to build a minimal DecisionAnalysis for tests."""
    opts = options or [
        DecisionOption(
            option_id="opt_a",
            title="Option A",
            description="Do A",
        ),
        DecisionOption(
            option_id="opt_b",
            title="Option B",
            description="Do B",
        ),
    ]
    tios = tradeoffs or [
        TradeOff(
            option_a_id="opt_a",
            option_b_id="opt_b",
            dimension="cost",
            a_score=60.0,
            b_score=40.0,
            delta=20.0,
            narrative="A costs more but delivers faster.",
        )
    ]
    return DecisionAnalysis(
        decision_id=decision_id,
        tenant_id="t1",
        workspace_id="ws_001",
        root_cause="Resource constraints",
        options=opts,
        tradeoffs=tios,
        recommended_option_id="opt_a",
        rationale="Option A has better tradeoff profile",
        confidence=confidence,
        impact_summary="Improved resource allocation",
    )


class TestEvaluationMetrics:
    """Test metric computation from DecisionAnalysis."""

    @pytest.fixture
    def runtime(self):
        return DefaultEvaluationRuntime()

    @pytest.fixture
    def analysis(self):
        return _make_analysis()

    @pytest.mark.asyncio
    async def test_evaluate_produces_metrics(self, runtime, analysis):
        """Test that evaluate() returns EvaluationMetrics."""
        metrics = await runtime.evaluate(
            decision_id=analysis.decision_id,
            analysis=analysis,
            tenant_id="t1",
        )

        assert isinstance(metrics, EvaluationMetrics)
        assert metrics.decision_id == "dec_001"
        assert metrics.confidence_score == 0.75
        assert metrics.options_count == 2
        assert metrics.tradeoffs_count == 1
        assert metrics.evidence_count == 0  # DecisionAnalysis doesn't have .evidence

    @pytest.mark.asyncio
    async def test_evaluate_with_goal_id(self, runtime, analysis):
        """Test that evaluate() accepts goal_id."""
        metrics = await runtime.evaluate(
            decision_id=analysis.decision_id,
            analysis=analysis,
            goal_id="goal_001",
            tenant_id="t1",
        )

        assert metrics.goal_id == "goal_001"

    @pytest.mark.asyncio
    async def test_evaluate_with_actual_result(self, runtime, analysis):
        """Test that evaluate() records actual results."""
        await runtime.evaluate(
            decision_id=analysis.decision_id,
            analysis=analysis,
            actual_result="Option A was executed successfully",
            measured_metrics={"cost_actual": 12000, "time_actual_days": 30},
            tenant_id="t1",
        )

        # Verify it's recorded
        golden = await runtime.golden_dataset(tenant_id="t1")
        assert len(golden) == 1
        assert golden[0]["actual_outcome"] == "Option A was executed successfully"
        assert golden[0]["has_accuracy_label"] is True

    @pytest.mark.asyncio
    async def test_evaluate_different_confidence_levels(self, runtime):
        """Test evaluation at different confidence levels."""
        for conf in [0.1, 0.5, 0.9]:
            analysis = _make_analysis(confidence=conf)
            metrics = await runtime.evaluate(
                decision_id=f"dec_{conf}",
                analysis=analysis,
                tenant_id="t1",
            )
            assert metrics.confidence_score == conf


class TestConfidenceUpdate:
    """Test confidence score updates."""

    @pytest.fixture
    def runtime(self):
        return DefaultEvaluationRuntime()

    @pytest.fixture
    def analysis(self):
        return _make_analysis()

    @pytest.mark.asyncio
    async def test_update_confidence_positive_delta(self, runtime, analysis):
        """Test increasing confidence."""
        await runtime.evaluate(
            decision_id=analysis.decision_id,
            analysis=analysis,
            tenant_id="t1",
        )

        new_conf = await runtime.update_confidence(
            decision_id=analysis.decision_id,
            tenant_id="t1",
            confidence_delta=0.1,
            reason="Positive outcome observed",
        )

        assert new_conf == pytest.approx(0.85, abs=0.01)

    @pytest.mark.asyncio
    async def test_update_confidence_clamped_to_1(self, runtime, analysis):
        """Test that confidence is clamped to [0, 1]."""
        await runtime.evaluate(
            decision_id=analysis.decision_id,
            analysis=analysis,
            tenant_id="t1",
        )

        new_conf = await runtime.update_confidence(
            decision_id=analysis.decision_id,
            tenant_id="t1",
            confidence_delta=0.5,  # 0.75 + 0.5 = 1.25 → 1.0
            reason="Excellent outcome",
        )
        assert new_conf == 1.0

    @pytest.mark.asyncio
    async def test_update_confidence_clamped_to_0(self, runtime, analysis):
        """Test that confidence is clamped to [0, 1] on the low end."""
        analysis_low = _make_analysis(confidence=0.1)
        await runtime.evaluate(
            decision_id=analysis_low.decision_id,
            analysis=analysis_low,
            tenant_id="t1",
        )

        new_conf = await runtime.update_confidence(
            decision_id=analysis_low.decision_id,
            tenant_id="t1",
            confidence_delta=-0.5,  # 0.1 - 0.5 = -0.4 → 0.0
            reason="Worse than expected",
        )
        assert new_conf == 0.0

    @pytest.mark.asyncio
    async def test_update_confidence_not_found(self, runtime):
        """Test error when decision not in store."""
        with pytest.raises(MetricError, match="not found"):
            await runtime.update_confidence(
                decision_id="unknown",
                tenant_id="t1",
                confidence_delta=0.1,
            )


class TestReplay:
    """Test decision replay functionality."""

    @pytest.fixture
    def runtime(self):
        return DefaultEvaluationRuntime()

    @pytest.fixture
    def analysis(self):
        return _make_analysis(confidence=0.8)

    @pytest.mark.asyncio
    async def test_replay_returns_result(self, runtime, analysis):
        """Test that replay() returns a ReplayResult."""
        await runtime.evaluate(
            decision_id=analysis.decision_id,
            analysis=analysis,
            tenant_id="t1",
        )

        result = await runtime.replay(
            decision_id=analysis.decision_id,
            tenant_id="t1",
            against_evidence_ids=["ev_001"],
        )

        assert isinstance(result, ReplayResult)
        assert result.decision_id == analysis.decision_id
        assert result.evidence_changed is True  # provided specific evidence IDs

    @pytest.mark.asyncio
    async def test_replay_with_new_evidence(self, runtime, analysis):
        """Test replaying against specific evidence IDs."""
        await runtime.evaluate(
            decision_id=analysis.decision_id,
            analysis=analysis,
            tenant_id="t1",
        )

        result = await runtime.replay(
            decision_id=analysis.decision_id,
            tenant_id="t1",
            against_evidence_ids=["ev_001", "ev_002"],
        )

        assert result.evidence_changed is True

    @pytest.mark.asyncio
    async def test_replay_not_found(self, runtime):
        """Test error when decision not in store."""
        with pytest.raises(MetricError, match="not found"):
            await runtime.replay(
                decision_id="unknown",
                tenant_id="t1",
            )


class TestGoldenDataset:
    """Test golden dataset tracking."""

    @pytest.fixture
    def runtime(self):
        return DefaultEvaluationRuntime()

    @pytest.fixture
    def analysis(self):
        return _make_analysis()

    @pytest.mark.asyncio
    async def test_golden_dataset_empty(self, runtime):
        """Test that golden_dataset returns empty list when no decisions."""
        result = await runtime.golden_dataset(tenant_id="t1")
        assert result == []

    @pytest.mark.asyncio
    async def test_golden_dataset_after_evaluate(self, runtime, analysis):
        """Test that golden_dataset contains evaluated decisions."""
        await runtime.evaluate(
            decision_id=analysis.decision_id,
            analysis=analysis,
            tenant_id="t1",
        )

        result = await runtime.golden_dataset(tenant_id="t1")
        assert len(result) == 1
        assert result[0]["decision_id"] == "dec_001"
        assert result[0]["has_accuracy_label"] is False  # no actual_result

    @pytest.mark.asyncio
    async def test_golden_dataset_filter_by_goal(self, runtime):
        """Test filtering golden dataset by goal_id."""
        analysis_a = _make_analysis(decision_id="dec_a", confidence=0.7)
        analysis_b = _make_analysis(decision_id="dec_b", confidence=0.9)

        await runtime.evaluate(
            decision_id="dec_a",
            analysis=analysis_a,
            goal_id="goal_x",
            tenant_id="t1",
        )
        await runtime.evaluate(
            decision_id="dec_b",
            analysis=analysis_b,
            goal_id="goal_y",
            tenant_id="t1",
        )

        goal_x_records = await runtime.golden_dataset(goal_id="goal_x", tenant_id="t1")
        assert len(goal_x_records) == 1
        assert goal_x_records[0]["decision_id"] == "dec_a"
