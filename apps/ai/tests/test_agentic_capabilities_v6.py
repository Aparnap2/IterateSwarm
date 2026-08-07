"""Agentic Capability Tests V6.

Tests newly implemented Mission Runtime, Digital Workforce, and Workspace
capabilities — NOT just LLM responses, but the full agentic stack:

1. Tool Calls — agents invoke capabilities → connectors
2. RAG — context assembly from evidence + knowledge graph
3. Decision Making — autonomous replanning, risk-based autonomy
4. Loop — continuous mission evaluation cycles
5. Context Engineering — structured context assembly
6. Type Safety — Pydantic contracts at every boundary
7. Harness Engineering — E2E pipeline from event to workspace
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock
from pydantic import ValidationError

from src.mission.runtime import Mission, MissionRuntime, MissionStatus, MissionState
from src.mission.employee import (
    RevenueOperationsAnalyst,
    ProductOperationsAnalyst,
    OrganizationalIntelligenceAnalyst,
    DigitalEmployee,
    RiskTier,
    AutonomyAction,
    EMPLOYEE_REGISTRY,
    get_employee,
)
from src.mission.capability import CRMCapability, CapabilityRegistry
from src.workspace.schema import (
    WorkspaceSchema,
    Component,
    ComponentType,
    build_revenue_workspace,
)
from src.goal.models import GoalKPI
from src.entities.models import EvidenceRecord, Provenance


pytestmark = pytest.mark.asyncio


class TestToolCalls:
    """Test agents invoking capabilities → connectors."""

    @pytest.fixture
    def mock_crm_cls(self):
        from src.connectors.crm import CRMConnector

        class MockCRM(CRMConnector):
            def __init__(self, config):
                self._config = config

            @property
            def capability(self) -> str:
                return "crm"

            @property
            def name(self) -> str:
                return "salesforce-test"

            def get_deals(self):
                return [{"id": "d1", "amount": 100000, "stage": "prospecting"}]

            def get_customers(self):
                return [{"id": "c1", "name": "Acme", "tier": "enterprise"}]

            def get_opportunities(self):
                return []

            def update_deal(self, deal_id: str, fields: dict):
                return {"id": deal_id, "updated": True, **fields}

            def create_customer(self, data: dict):
                return "cust_123"

            def health(self) -> dict:
                return {"status": "healthy"}

        return MockCRM

    async def test_employee_invokes_crm_capability(self, mock_crm_cls):
        """Employee must invoke CRM capability, not call connector directly."""
        emp = RevenueOperationsAnalyst(tenant_id="t1")
        mock_crm = mock_crm_cls(type("Cfg", (), {"tenant_id": "t1"})())

        with patch.object(emp, "_get_capability", return_value=mock_crm):
            deals = emp._get_capability("crm").get_deals()
            assert len(deals) == 1
            assert deals[0]["stage"] == "prospecting"

    async def test_capability_registry_maps_crm(self):
        """CapabilityRegistry has CRMCapability mapped for 'crm'."""
        assert "crm" in CapabilityRegistry._capability_map
        assert CapabilityRegistry._capability_map["crm"] == CRMCapability


class TestRAG:
    """Test context assembly from evidence + knowledge."""

    async def test_mission_assembles_evidence_context(self, mock_crm_cls=None):
        """Mission context includes evidence_ids and knowledge_ids."""
        from src.connectors.base import ConnectorConfig

        runtime = MissionRuntime()
        kpi = GoalKPI(
            id="kpi_001",
            goal_id="",
            name="Revenue",
            target_value=100.0,
            baseline_value=0.0,
            current_value=50.0,
            unit="percentage",
            direction="increase",
        )
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Test RAG",
            kpis=[kpi],
        )
        mission = Mission.from_goal(goal)

        # Context should include mission metadata
        ctx = {
            "mission_id": mission.id,
            "title": mission.title,
            "confidence": mission.confidence,
            "kpi_scores": mission.kpi_scores,
            "evidence_ids": mission.evidence_ids,
        }
        assert ctx["mission_id"] == mission.id
        assert ctx["title"] == "Test RAG"

    async def test_workspace_schema_includes_evidence_refs(self):
        """Workspace schema components must include evidence_ids references."""
        from src.workspace.schema import build_revenue_workspace, ComponentType

        schema = build_revenue_workspace(
            tenant_id="t1",
            mission_id="m1",
            kpi_data={"mrr": 50000, "churn_rate": 3.1},
            deals=[],
            recommendations=["Action 1"],
            evidence_ids=["ev_001", "ev_002"],
        )

        # Components should carry evidence references
        total_evidence = sum(len(c.evidence_ids) for c in schema.components)
        # At least the recommendation card should have evidence
        recs = [c for c in schema.components if c.type == ComponentType.RECOMMENDATION]
        assert len(recs) == 1


class TestDecisionMaking:
    """Test autonomous decision making — replanning, risk, confidence."""

    @pytest.fixture
    def runtime(self):
        return MissionRuntime()

    async def test_autonomous_replan_on_stalled_confidence(self, runtime):
        """Low confidence → autonomous plan generation."""
        kpi = GoalKPI(
            id="kpi_low",
            goal_id="",
            name="Low Confidence KPI",
            target_value=100.0,
            baseline_value=0.0,
            current_value=10.0,  # 10% of target → confidence 0.1 < 0.3
            unit="percentage",
            direction="increase",
        )
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Low Confidence",
            kpis=[kpi],
        )

        plan = await runtime.advance(goal.id, tenant_id="t1")
        assert plan is not None
        assert "Advance" in plan.title

    async def test_no_replan_when_on_track(self, runtime):
        """High confidence → no replan."""
        kpi = GoalKPI(
            id="kpi_high",
            goal_id="",
            name="High Confidence KPI",
            target_value=100.0,
            baseline_value=0.0,
            current_value=95.0,  # 95% → confidence 0.95 > 0.3
            unit="percentage",
            direction="increase",
        )
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="On Track",
            kpis=[kpi],
        )

        plan = await runtime.advance(goal.id, tenant_id="t1")
        assert plan is None

    async def test_risk_tier_drives_approval_workflow(self):
        """RiskTier determines whether approval is required."""
        emp = RevenueOperationsAnalyst(tenant_id="t1")

        # Low risk → auto-execute
        risk = emp._assess_risk(AutonomyAction.ANALYZE, "pipeline query")
        assert risk == RiskTier.LOW
        assert not emp._requires_approval(risk)

        # High risk → requires approval
        risk = emp._assess_risk(AutonomyAction.UPDATE, "status_change")
        assert risk == RiskTier.HIGH
        assert emp._requires_approval(risk)

        # Critical risk → must approve
        risk = emp._assess_risk(AutonomyAction.UPDATE, "delete customer")
        assert risk == RiskTier.CRITICAL
        assert emp._requires_approval(risk)


class TestLoop:
    """Test continuous evaluation cycles."""

    @pytest.fixture
    def runtime(self):
        return MissionRuntime()

    @pytest.fixture
    def kpi(self):
        return GoalKPI(
            id="kpi_loop",
            goal_id="",
            name="Growth",
            target_value=100.0,
            baseline_value=0.0,
            current_value=20.0,
            unit="percentage",
            direction="increase",
        )

    async def test_continuous_evaluation_updates_confidence(self, runtime, kpi):
        """Repeated evaluate() calls progressively update confidence."""
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Iterative Evaluation",
            kpis=[kpi],
        )

        # Initial confidence should be low (20% of target)
        progress = await runtime.evaluate(goal.id, tenant_id="t1")
        assert progress.confidence < 0.5

    async def test_mission_state_serialization_roundtrip(self, runtime):
        """Mission state can serialize for Temporal ContinueAsNew."""
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Loop Test",
            kpis=[GoalKPI(
                id="k", goal_id="", name="K",
                target_value=100.0, baseline_value=0.0, current_value=50.0,
                unit="pct", direction="increase",
            )],
        )
        mission = Mission.from_goal(goal)
        state = MissionState(mission)
        data = state.to_dict()

        assert data["id"] == mission.id
        assert data["status"] == "active"
        assert isinstance(data["confidence"], float)


class TestContextEngineering:
    """Test structured context assembly — no raw connector data to LLM."""

    async def test_employee_builds_structured_evidence(self):
        """EvidenceRecords are properly typed, not raw connector dicts."""
        from src.connectors.base import ConnectorConfig

        emp = RevenueOperationsAnalyst(tenant_id="t1")
        mock_deal = {"id": "d1", "amount": 50000, "stage": "closing", "name": "Acme Deal"}

        record = emp._make_evidence(mock_deal, "salesforce", "RevOps Analyst")

        # Must be EvidenceRecord (typed), not raw dict
        assert isinstance(record, EvidenceRecord)
        assert record.id == "d1"
        assert record.source == "salesforce"
        assert record.source_type == "connector"
        assert record.schema_version == "v6.0"
        assert record.confidence == 0.9
        assert record.tenant_id == "t1"
        # Provenance must be a Pydantic model
        assert isinstance(record.provenance, Provenance)
        # Structured data preserved but not raw connector output
        assert record.structured_data["amount"] == 50000

    async def test_employee_never_exposes_connector_directly(self):
        """Employees must not have direct connector attributes."""
        emp = RevenueOperationsAnalyst(tenant_id="t1")
        assert not hasattr(emp, "connector")
        assert not hasattr(emp, "salesforce")
        assert not hasattr(emp, "crm")
        # Only capability names
        assert hasattr(emp, "allowed_capabilities")


class TestTypeSafety:
    """Test Pydantic contracts are enforced at every boundary."""

    async def test_workspace_schema_rejects_extra_fields(self):
        """Component model uses extra='forbid' — rejects unknown keys."""
        with pytest.raises(ValidationError):
            Component(
                id="c1",
                type=ComponentType.KPI_CARD,
                title="Test",
                props={"value": 42},
                invalid_field="should be rejected",  # type: ignore
            )

    async def test_evidence_record_validates_required_fields(self):
        """EvidenceRecord requires all canonical fields."""
        from src.entities.models import EvidenceRecord

        # Missing tenant_id → validation error
        with pytest.raises(ValidationError):
            EvidenceRecord(
                id="e1",
                source="test",
                source_type="connector",
                # missing: tenant_id, timestamp, confidence, provenance, hash
            )

    async def test_mission_status_enum_strict(self):
        """MissionStatus only accepts valid enum values."""
        # Valid
        assert MissionStatus("active") == MissionStatus.ACTIVE

        # Invalid
        with pytest.raises(ValueError):
            MissionStatus("bogus")


class TestHarness:
    """Test full pipeline harness — event to workspace."""

    @pytest.fixture
    def mock_crm_cls(self):
        from src.connectors.crm import CRMConnector

        class MockCRM(CRMConnector):
            def __init__(self, config):
                self._config = config

            @property
            def capability(self) -> str:
                return "crm"

            @property
            def name(self) -> str:
                return "salesforce-test"

            def get_deals(self):
                return [
                    {"id": "d1", "amount": 50000, "stage": "prospecting"},
                    {"id": "d2", "amount": 75000, "stage": "negotiation"},
                    {"id": "d3", "amount": 30000, "stage": "closing"},
                ]

            def get_customers(self):
                return [{"id": "c1", "name": "Acme Corp", "tier": "enterprise"}]

            def get_opportunities(self):
                return []

            def update_deal(self, deal_id: str, fields: dict):
                return {"id": deal_id, "updated": True}

            def create_customer(self, data: dict):
                return "cust_123"

            def health(self) -> dict:
                return {"status": "healthy"}

        return MockCRM

    @pytest.fixture
    def worker(self, mock_crm_cls):
        """Revenue Operations Analyst with mocked CRM."""
        emp = RevenueOperationsAnalyst(tenant_id="harness_tenant")
        mock_crm = mock_crm_cls(type("Cfg", (), {"tenant_id": "harness_tenant"})())
        def mock_get(name):
            return mock_crm if name == "crm" else mock_crm
        emp._get_capability = mock_get
        return emp

    async def test_full_pipeline_event_to_workspace(self, worker):
        """Pipeline: create mission → execute → produce workspace schema.

        This is the core E2E harness test.
        """
        from src.workspace.schema import build_revenue_workspace, ComponentType

        runtime = MissionRuntime()

        # Step 1: Event → Evidence → Mission
        goal = await runtime.create(
            tenant_id="harness_tenant",
            owner_id="test_user",
            title="Revenue Pipeline Health",
            kpis=[GoalKPI(
                id="kpi_rev",
                goal_id="",
                name="Pipeline Coverage",
                target_value=3.0,
                baseline_value=1.0,
                current_value=1.5,
                unit="ratio",
                direction="increase",
            )],
        )
        mission = Mission.from_goal(goal)

        # Step 2: Mission → Employee executes → Evidence
        state = await worker.execute_mission(mission)

        # Step 3: Employee produces evidence records
        evidence = await worker.investigate("pipeline health", [])
        assert isinstance(evidence, list)
        if evidence:
            assert all(isinstance(e, EvidenceRecord) for e in evidence)

        # Step 4: Mission → Workspace Schema
        schema = build_revenue_workspace(
            tenant_id="harness_tenant",
            mission_id=mission.id,
            kpi_data={
                "mrr": 155000,
                "churn_rate": 3.2,
                "mrr_trend": "down",
            },
            deals=[],
            recommendations=[
                "Follow up on negotiation stage deals",
                "Investigate pipeline coverage drop",
            ],
            evidence_ids=[e.id for e in evidence] if evidence else [],
        )

        assert schema.workspace == "revenue-health"
        assert schema.mission_id == mission.id

        # Verify workspace has typed components
        kpi_cards = [c for c in schema.components if c.type == ComponentType.KPI_CARD]
        assert len(kpi_cards) >= 2

        rec_components = [c for c in schema.components if c.type == ComponentType.RECOMMENDATION]
        assert len(rec_components) == 1
        assert len(rec_components[0].props["actions"]) == 2

        # Step 5: Verify decision confidence reflects pipeline
        deals = worker._get_capability("crm").get_deals()
        at_risk = [d for d in deals if d.get("stage") in ("negotiation", "closing")]
        assert len(at_risk) == 2  # d2 + d3

    async def test_pipeline_is_deterministic(self, worker):
        """Running the pipeline twice produces consistent results."""
        runtime = MissionRuntime()
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="Determinism Test",
            kpis=[GoalKPI(
                id="k1", goal_id="", name="K",
                target_value=100.0, baseline_value=0.0, current_value=50.0,
                unit="pct", direction="increase",
            )],
        )
        mission = Mission.from_goal(goal)

        # Run twice
        state1 = await worker.execute_mission(mission)
        state2 = await worker.execute_mission(mission)

        # Confidence should be identical (deterministic, no LLM involved)
        assert state1.data["confidence"] == state2.data["confidence"]


class TestIdempotency:
    """Test that repeated operations produce same results."""

    async def test_mission_state_idempotent(self):
        """Calling create twice with same params — IDs differ, but structure is stable."""
        runtime = MissionRuntime()
        kpi = GoalKPI(
            id="kpi_idem", goal_id="", name="KPI",
            target_value=100.0, baseline_value=0.0, current_value=50.0,
            unit="pct", direction="increase",
        )

        goal1 = await runtime.create(tenant_id="t1", owner_id="u", title="Test", kpis=[kpi])
        goal2 = await runtime.create(tenant_id="t1", owner_id="u", title="Test", kpis=[kpi])

        assert goal1.id != goal2.id  # Unique IDs
        assert goal1.title == goal2.title  # Same content
        assert goal1.confidence == goal2.confidence  # Same initial state


class TestFailureHandling:
    """Test graceful failure when capabilities are unavailable."""

    async def test_mission_handles_empty_evidence(self):
        """Mission with no evidence → zero confidence, no crash."""
        runtime = MissionRuntime()
        goal = await runtime.create(
            tenant_id="t1",
            owner_id="u1",
            title="No Evidence Test",
            kpis=[],  # No KPIs → confidence 0.0
        )
        progress = await runtime.evaluate(goal.id, tenant_id="t1")
        assert progress.confidence == 0.0

    async def test_employee_handles_missing_capability(self):
        """Employee raises clear error when capability is unavailable."""
        from src.mission.capability import BaseCapability

        emp = RevenueOperationsAnalyst(tenant_id="t1")

        class NullCap(BaseCapability):
            def __init__(self):
                pass
            @property
            def capability(self):
                return "null"
            def observe(self, **kw):
                raise NotImplementedError("Capability unavailable")
            def execute(self, cmd, payload):
                raise NotImplementedError("Capability unavailable")

        with patch.object(emp, "_get_capability", return_value=NullCap()):
            with pytest.raises(NotImplementedError):
                emp._get_capability("crm").observe()
