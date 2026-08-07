"""Tests for Mission Runtime."""
from datetime import datetime, timezone

import pytest

from src.mission.runtime import Mission, MissionRuntime, MissionStatus, MissionState
from src.goal.models import GoalKPI


class TestMissionRuntime:

    @pytest.fixture
    def runtime(self):
        return MissionRuntime()

    @pytest.fixture
    def rev_kpi(self):
        return GoalKPI(
            id="kpi_rev_001",
            goal_id="",
            name="MRR",
            target_value=50000.0,
            baseline_value=25000.0,
            current_value=25000.0,
            unit="USD",
            direction="increase",
        )

    @pytest.mark.asyncio
    async def test_create_mission_from_goal(self, runtime, rev_kpi):
        """Test that GoalRuntime.create produces a Mission."""
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Increase MRR to $50K",
            kpis=[rev_kpi],
        )
        mission = Mission.from_goal(goal)

        assert mission.title == "Increase MRR to $50K"
        assert mission.tenant_id == "t1"
        assert mission.status == MissionStatus.ACTIVE
        assert mission.confidence == 0.0

    @pytest.mark.asyncio
    async def test_mission_to_goal_roundtrip(self, runtime, rev_kpi):
        """Test that Mission.to_goal preserves data."""
        mission = Mission(
            tenant_id="t1",
            owner_id="u1",
            title="Test Mission",
            kpis=[rev_kpi],
            evidence_ids=["ev1"],
            decision_ids=["dec1"],
        )
        goal = mission.to_goal()

        assert goal.title == "Test Mission"
        assert goal.tenant_id == "t1"
        assert goal.kpis[0].name == "MRR"
        assert goal.metadata["evidence_ids"] == ["ev1"]
        assert goal.metadata["decision_ids"] == ["dec1"]

    @pytest.mark.asyncio
    async def test_mission_state_serialization(self, runtime, rev_kpi):
        """Test that MissionState serializes correctly."""
        mission = Mission(
            id="m1",
            tenant_id="t1",
            title="Test",
            confidence=0.75,
            kpi_scores={"MRR": 0.5},
        )
        state = MissionState(mission)
        data = state.to_dict()

        assert data["id"] == "m1"
        assert data["confidence"] == 0.75
        assert data["kpi_scores"] == {"MRR": 0.5}

    @pytest.mark.asyncio
    async def test_advance_mission_on_track(self, runtime, rev_kpi):
        """Test advancing a mission that is on track."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="MRR Growth",
            target_value=100.0,
            baseline_value=0.0,
            current_value=95.0,  # 95% of target
            unit="percentage",
            direction="increase",
        )
        mission = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Grow MRR",
            kpis=[kpi],
        )
        plan = await runtime.advance(mission.id, tenant_id="t1")
        # On-track goal (confidence high, all KPIs pass) → no plan needed
        assert plan is None

    @pytest.mark.asyncio
    async def test_force_replan(self, runtime):
        """Test forced replanning."""
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="MRR Growth",
            target_value=100.0,
            baseline_value=0.0,
            current_value=20.0,
            unit="percentage",
            direction="increase",
        )
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Grow MRR",
            kpis=[kpi],
        )
        # Confidence is 0.2 (below 0.3 threshold) → should replan
        plan = await runtime.advance(goal.id, tenant_id="t1")
        assert plan is not None  # stalled → should generate plan
        assert plan is not None  # confidence low → should generate plan
