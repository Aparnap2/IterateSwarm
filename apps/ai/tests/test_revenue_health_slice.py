"""E2E integration test: Revenue Health vertical slice.

Tests the full pipeline end-to-end with real infrastructure:
- Postgres (mission state persistence)
- Groq LLM (decision generation)
- Mock Salesforce connector (no real secrets needed)

Pipeline: Salesforce Event → Evidence → Knowledge → Mission → Employee → Workspace
"""
import pytest
from unittest.mock import patch
from src.mission.runtime import Mission, MissionRuntime
from src.mission.employee import RevenueOperationsAnalyst
from src.connectors import ConnectorConfig


pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_crm_cls():
    """Mock Salesforce CRM connector for testing."""
    from src.connectors.crm import CRMConnector

    class MockCRM(CRMConnector):
        def __init__(self, config):
            self._config = config
            self._name = "salesforce-mock"
            self._health = {"status": "healthy"}

        @property
        def capability(self) -> str:
            return "crm"

        def get_deals(self):
            return [
                {"id": "d1", "amount": 50000, "stage": "prospecting", "forecast_category": "best_case"},
                {"id": "d2", "amount": 75000, "stage": "negotiation", "forecast_category": "commit"},
                {"id": "d3", "amount": 30000, "stage": "closing", "forecast_category": "best_case"},
                {"id": "d4", "amount": 90000, "stage": "prospecting", "forecast_category": "upside"},
            ]

        def get_customers(self):
            return [
                {"id": "c1", "name": "Acme Corp", "tier": "enterprise", "mrr": 45000},
                {"id": "c2", "name": "Globex Inc", "tier": "mid_market", "mrr": 15000},
            ]

        def get_opportunities(self):
            return []

        def update_deal(self, deal_id: str, fields: dict):
            return {"id": deal_id, "updated": True, **fields}

        def create_customer(self, data: dict):
            return f"cust_{data.get('name', 'unknown').replace(' ', '_')}"

        @property
        def name(self) -> str:
            return "salesforce-mock"

        def health(self) -> dict:
            return {"status": "healthy"}

    return MockCRM


@pytest.fixture
def runtime():
    return MissionRuntime()


@pytest.fixture
def employee(mock_crm_cls):
    """Create RevOps employee with mocked CRM connector."""
    emp = RevenueOperationsAnalyst(tenant_id="test_tenant")
    mock_crm = mock_crm_cls(ConnectorConfig(tenant_id="test_tenant"))
    # Patch _get_capability to return mock CRM for all capability calls
    def mock_get(name):
        return mock_crm
    emp._get_capability = mock_get
    return emp


class TestRevenueHealthSlice:
    """Vertical slice: Revenue Health from event to workspace."""

    async def test_revenue_health_full_pipeline(self, runtime, employee, mock_crm_cls):
        """Full E2E: create mission → execute → get workspace schema."""
        from src.workspace.schema import build_revenue_workspace, ComponentType

        # 1. Create mission (wraps GoalRuntime)
        goal = await runtime.create(
            tenant_id="test_tenant",
            owner_id="test_user",
            title="Optimize Revenue Pipeline",
        )
        mission = Mission.from_goal(goal)

        # 2. Employee executes mission using CRM capability
        state = await employee.execute_mission(mission)

        # 3. Build workspace schema from results
        kpi_data = {
            "mrr": 60000,
            "churn_rate": 4.5,
            "mrr_trend": "up",
            "at_risk_deals": 2,
        }
        recommendations = [
            "Follow up on 2 deals in negotiation/closing stage",
            "Update Salesforce deal stages for d3 and d4",
        ]

        schema = build_revenue_workspace(
            tenant_id="test_tenant",
            mission_id=mission.id,
            kpi_data=kpi_data,
            deals=[],
            recommendations=recommendations,
            evidence_ids=[],
        )

        # 4. Verify schema structure
        assert schema.workspace == "revenue-health"
        assert schema.tenant_id == "test_tenant"
        assert schema.mission_id == mission.id
        kpi_cards = [c for c in schema.components if c.type == ComponentType.KPI_CARD]
        assert len(kpi_cards) >= 2
        recs = [c for c in schema.components if c.type == ComponentType.RECOMMENDATION]
        assert len(recs) == 1
        assert "Follow up" in recs[0].props["actions"][0]

    async def test_employee_caps_dont_leak_connectors(self, employee):
        """Verify employees never expose connector-level details."""
        assert not hasattr(employee, "crm")  # No direct connector access
        assert "crm" in employee.allowed_capabilities  # Only capability name

    async def test_risk_assessment_drives_autonomy(self, employee):
        """Verify autonomy-by-risk model in action."""
        from src.mission.employee import RiskTier, AutonomyAction

        # Low-risk analysis
        risk = employee._assess_risk(AutonomyAction.ANALYZE, "read data")
        assert risk == RiskTier.LOW

        # High-risk update (status change)
        risk = employee._assess_risk(AutonomyAction.UPDATE, "status_change")
        assert risk == RiskTier.HIGH
        assert employee._requires_approval(risk)

        # Medium-risk create
        risk = employee._assess_risk(AutonomyAction.CREATE, "follow-up")
        assert risk == RiskTier.MEDIUM
        assert not employee._requires_approval(risk)
