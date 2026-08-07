"""Tests for Workspace Schema contract."""
import pytest
from src.workspace.schema import (
    WorkspaceSchema,
    Component,
    ComponentType,
    build_revenue_workspace,
)


class TestWorkspaceSchema:

    def test_empty_schema(self):
        schema = WorkspaceSchema(
            workspace="test",
            title="Test",
            tenant_id="t1",
            components=[],
        )
        data = schema.to_json()
        assert data["workspace"] == "test"
        assert len(data["components"]) == 0

    def test_schema_with_components(self):
        schema = WorkspaceSchema(
            workspace="revenue",
            title="Revenue Dashboard",
            tenant_id="t1",
            components=[
                Component(
                    id="card-1",
                    type=ComponentType.KPI_CARD,
                    title="MRR",
                    props={"value": 50000},
                ),
            ],
        )
        data = schema.to_json()
        assert data["components"][0]["type"] == "kpi_card"
        assert data["components"][0]["props"]["value"] == 50000

    def test_revenue_workspace_factory(self):
        schema = build_revenue_workspace(
            tenant_id="t1",
            mission_id="m1",
            kpi_data={"mrr": 45000, "churn_rate": 3.2, "mrr_trend": "up"},
            deals=[],
            recommendations=["Follow up with at-risk accounts"],
            evidence_ids=["ev1"],
        )
        assert schema.workspace == "revenue-health"
        assert schema.mission_id == "m1"
        assert len(schema.components) > 0
        kpi_components = [c for c in schema.components if c.type == ComponentType.KPI_CARD]
        assert len(kpi_components) == 2  # MRR + churn cards

    def test_component_type_enum(self):
        assert ComponentType.KPI_CARD.value == "kpi_card"
        assert ComponentType.KNOWLEDGE_GRAPH.value == "knowledge_graph"
        assert ComponentType.RECOMMENDATION.value == "recommendation"
