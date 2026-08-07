"""Workspace Schema — typed JSON contract for Decision Workspace.

The backend produces a WorkspaceSchema. HTMX (Go) renders it.
This abstraction allows future React/Svelte frontend without backend changes.

Schema:
  workspace → components[] → props + layout + permissions + state
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ComponentType(str, Enum):
    """Available workspace components."""
    KPI_CARD = "kpi_card"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    TIMELINE = "timeline"
    DECISION_CARD = "decision_card"
    RECOMMENDATION = "recommendation"
    APPROVAL_CARD = "approval_card"
    MISSION_STATE = "mission_state"
    LOGS = "logs"
    CHAT_PANEL = "chat_panel"
    ACTIVITY_FEED = "activity_feed"
    EVIDENCE_LIST = "evidence_list"
    RISK_INDICATOR = "risk_indicator"
    DEPENDENCY_MAP = "dependency_map"
    FORECAST_VIEW = "forecast_view"


class ComponentProp(BaseModel):
    """A single property slot for a component."""
    name: str
    value: Any


class ComponentState(BaseModel):
    """Runtime state for a component."""
    loading: bool = False
    error: str | None = None
    version: str = "v6"


class Component(BaseModel):
    """A single workspace component."""
    model_config = ConfigDict(extra="forbid")

    id: str
    type: ComponentType
    title: str = ""
    props: dict[str, Any] = Field(default_factory=dict)
    state: ComponentState = Field(default_factory=ComponentState)
    layout: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class LayoutSpec(BaseModel):
    """Layout specification for the workspace."""
    grid_cols: int = 12
    gap: str = "2"
    responsive: bool = True


class WorkspacePermissions(BaseModel):
    """Permissions for a workspace."""
    can_view: bool = True
    can_edit: bool = False
    can_execute: bool = False
    can_approve: bool = False


class WorkspaceSchema(BaseModel):
    """Top-level workspace schema.

    Produced by Python Decision Runtime.
    Rendered by Go HTMX renderer.
    """
    workspace: str
    title: str
    tenant_id: str
    mission_id: str | None = None
    components: list[Component]
    layout: LayoutSpec = Field(default_factory=LayoutSpec)
    permissions: WorkspacePermissions = Field(default_factory=WorkspacePermissions)
    state: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        """Export as JSON-serializable dict."""
        return self.model_dump()


def build_revenue_workspace(
    tenant_id: str,
    mission_id: str,
    kpi_data: dict[str, Any],
    deals: list[dict[str, Any]],
    recommendations: list[str],
    evidence_ids: list[str],
) -> WorkspaceSchema:
    """Build a revenue health workspace schema."""
    revenue = kpi_data.get("mrr", 0)
    churn = kpi_data.get("churn_rate", 0)
    at_risk = kpi_data.get("at_risk_deals", 0)

    return WorkspaceSchema(
        workspace="revenue-health",
        title="Revenue Health Dashboard",
        tenant_id=tenant_id,
        mission_id=mission_id,
        components=[
            Component(
                id="revenue-card",
                type=ComponentType.KPI_CARD,
                title="Monthly Recurring Revenue",
                props={"value": revenue, "currency": "USD", "trend": kpi_data.get("mrr_trend", "stable")},
            ),
            Component(
                id="churn-card",
                type=ComponentType.KPI_CARD,
                title="Churn Rate",
                props={"value": churn, "unit": "percentage", "threshold": 5.0},
            ),
            Component(
                id="health-graph",
                type=ComponentType.KNOWLEDGE_GRAPH,
                title="Revenue Entity Graph",
                props={"nodes": [], "edges": [], "center": "revenue"},
            ),
            Component(
                id="deal-timeline",
                type=ComponentType.TIMELINE,
                title="Deal Timeline",
                props={"events": [], "focus": "deals"},
            ),
            Component(
                id="revops-recommendation",
                type=ComponentType.RECOMMENDATION,
                title="Recommended Actions",
                props={"actions": recommendations},
            ),
        ],
    )
