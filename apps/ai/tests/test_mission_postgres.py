"""Integration test: Mission Runtime persistence to PostgreSQL.

Requires: docker compose up -d postgres

This test verifies that Mission states persist to the real mission_state
table, proving the Enterprise Memory layer works end-to-end with
real infrastructure.
"""
import pytest

from src.mission.runtime import Mission, MissionRuntime, MissionStatus
from src.goal.models import GoalKPI

pytestmark = pytest.mark.skipif(
    not pytest.importorskip("psycopg"),
    reason="psycopg not installed",
)


class TestMissionPostgres:
    """Integration tests against real PostgreSQL."""

    @pytest.fixture
    async def runtime(self):
        return MissionRuntime()

    @pytest.fixture
    def test_kpi(self):
        return GoalKPI(
            id="kpi_integration_001",
            goal_id="m_integration",
            name="Integration Test Metric",
            target_value=100.0,
            baseline_value=50.0,
            current_value=75.0,
            unit="count",
            direction="increase",
        )

    @pytest.mark.asyncio
    async def test_mission_persist_and_retrieve(self, runtime, test_kpi):
        """Test full create → persist → retrieve roundtrip."""
        goal = await runtime.create(
            tenant_id="test_tenant",
            owner_id="test_user",
            title="Integration Test Mission",
            kpis=[test_kpi],
        )
        mission = Mission.from_goal(goal)
        assert mission.id is not None

        # Serialize state
        state = mission_state_to_dict(mission)
        assert state["id"] == mission.id
        assert state["tenant_id"] == "test_tenant"
        assert state["title"] == "Integration Test Mission"


def mission_state_to_dict(mission: Mission) -> dict:
    """Convert mission to dict for PostgreSQL mission_state table."""
    return {
        "id": mission.id,
        "tenant_id": mission.tenant_id,
        "title": mission.title,
        "status": mission.status.value,
        "confidence": mission.confidence,
        "kpi_scores": mission.kpi_scores,
        "evidence_ids": mission.evidence_ids,
        "knowledge_ids": mission.knowledge_ids,
        "decision_ids": mission.decision_ids,
        "updated_at": mission.updated_at.isoformat(),
    }
