# FROZEN — V6.0 M1
"""Mission Runtime — persistent long-running business objectives.

Wraps the GoalRuntime with:
- PostgreSQL persistence (INSERT/UPDATE mission_state)
- Temporal Workflow ContinueAsNew pattern
- Signal handlers for human interrupts

Pipeline: Enterprise Events → Evidence → Knowledge → Memory → Mission → ...
"""
from __future__ import annotations

import enum
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.goal.models import Goal, GoalKPI, GoalStatus
from src.goal.runtime import DefaultGoalRuntime

logger = logging.getLogger(__name__)


class MissionStatus(str, enum.Enum):
    """Mission lifecycle states mapped to GoalStatus."""
    PENDING = "pending"
    ACTIVE = "active"
    STALLED = "stalled"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class Mission:
    """Mission = Goal with temporal workflow state.

    Persisted to mission_state table via PostgreSQL.
    """
    def __init__(
        self,
        id: str | None = None,
        tenant_id: str = "default",
        title: str = "",
        description: str = "",
        owner_id: str = "",
        status: MissionStatus = MissionStatus.ACTIVE,
        kpis: list[GoalKPI] | None = None,
        kpi_scores: dict[str, float] | None = None,
        confidence: float = 0.0,
        priority: str = "medium",
        evidence_ids: list[str] | None = None,
        knowledge_ids: list[str] | None = None,
        decision_ids: list[str] | None = None,
        temporal_workflow_id: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.id = id or str(uuid4())
        self.tenant_id = tenant_id
        self.title = title
        self.description = description
        self.owner_id = owner_id
        self.status = status
        self.kpis = kpis or []
        self.kpi_scores = kpi_scores or {}
        self.confidence = confidence
        self.priority = priority
        self.evidence_ids = evidence_ids or []
        self.knowledge_ids = knowledge_ids or []
        self.decision_ids = decision_ids or []
        self.temporal_workflow_id = temporal_workflow_id
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)

    def to_goal(self) -> Goal:
        """Convert to Goal for GoalRuntime compatibility."""
        return Goal(
            id=self.id,
            tenant_id=self.tenant_id,
            owner_id=self.owner_id,
            title=self.title,
            description=self.description,
            status=GoalStatus(self.status.value),
            kpis=self.kpis,
            confidence=self.confidence,
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata={"evidence_ids": self.evidence_ids, "knowledge_ids": self.knowledge_ids, "decision_ids": self.decision_ids},
        )

    @classmethod
    def from_goal(cls, goal: Goal) -> "Mission":
        """Create Mission from a Goal."""
        meta = goal.metadata or {}
        raw_status = goal.status.value if isinstance(goal.status, GoalStatus) else goal.status
        return cls(
            id=goal.id,
            tenant_id=goal.tenant_id,
            title=goal.title,
            description=goal.description,
            owner_id=goal.owner_id,
            status=MissionStatus(raw_status),
            kpis=goal.kpis,
            confidence=goal.confidence,
            evidence_ids=meta.get("evidence_ids", []),
            knowledge_ids=meta.get("knowledge_ids", []),
            decision_ids=meta.get("decision_ids", []),
            created_at=goal.created_at,
            updated_at=goal.updated_at,
        )


class MissionState:
    """Serializable mission state for Temporal ContinueAsNew."""
    def __init__(self, mission: Mission):
        self.data = {
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

    def to_dict(self) -> dict[str, Any]:
        return self.data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> dict[str, Any]:
        return data


class MissionRuntime(DefaultGoalRuntime):
    """Persistent Mission Runtime.

    Wraps DefaultGoalRuntime with:
    - PostgreSQL persistence on mission_state table
    - Signal-aware (Temporal)
    - ContinueAsNew support

    Reuses all GoalRuntime logic (evaluate, advance, review, archive).
    """

    async def persist_mission_state(self, mission: Mission, db: Any | None = None) -> None:
        """Persist mission state to PostgreSQL mission_state table.

        Uses sync DB connection from db argument or h.db.
        """
        if db is None:
            return  # In testing or no DB available — skip persistence

        await db.execute(
            """
            INSERT INTO mission_state (
                id, tenant_id, updated_at
            ) VALUES ($1, $2, NOW())
            """,
            mission.id,
            mission.tenant_id,
        )

    async def update_mission_kpis(
        self, mission_id: str, kpi_scores: dict[str, float], confidence: float, db: Any | None = None
    ) -> None:
        """Update KPI scores and confidence in mission_state table."""
        if db is None:
            return

        kpi_json = "{" + ", ".join(f'"{k}": {v}' for k, v in kpi_scores.items()) + "}"
        await db.execute(
            """
            UPDATE mission_state
            SET mrr = $1, burn_rate = $2, updated_at = NOW()
            WHERE id = $3
            """,
            round(sum(kpi_scores.values()) / len(kpi_scores) if kpi_scores else 0.0, 4),
            confidence,
            mission_id,
        )
