"""Mission Coordinator — the Enterprise Observer façade.

Observation the enterprise, not a single connector. One ingested enterprise
event can fan out to **every** mission subscribed to that source's domain
(e.g. a Slack message re-evaluates Revenue Health, Customer Health and Roadmap
missions simultaneously).

Responsibilities
----------------
- owns the set of live :class:`MissionOrchestrator` instances (per mission id);
- routes incoming evidence/events to all subscribed missions (domain fan-out);
- routes human **signals** to a single mission (pause/resume/redirect/...);
- runs the **proactive review loop** (wake missions that are due, even when idle);
- accumulates an event **outbox** for workspace / SSE consumers to drain.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from src.goal.models import GoalKPI, GoalStatus
from src.mission.orchestrator import (
    MissionEvent,
    MissionEventType,
    MissionOrchestrator,
    MissionPhase,
)
from src.mission.runtime import Mission

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MissionCoordinator:
    """Multi-mission coordinator — enter the Observer loop."""

    def __init__(
        self,
        tenant_id: str = "default",
        now_fn: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.tenant_id = tenant_id
        self._now_fn = now_fn
        self._orchestrators: dict[str, MissionOrchestrator] = {}
        # source-domain -> {mission_id, ...} subscription map for fan-out.
        self._subscriptions: dict[str, set[str]] = {}
        self._events: list[MissionEvent] = []

    def _now(self) -> datetime:
        return self._now_fn()

    # ── mission registry ─────────────────────────────────────────────────────

    def register(
        self,
        orchestrator: MissionOrchestrator,
        *,
        subscriptions: list[str] | None = None,
    ) -> None:
        self._orchestrators[orchestrator.mission.id] = orchestrator
        for domain in subscriptions or []:
            self._subscriptions.setdefault(domain, set()).add(orchestrator.mission.id)

    def create_mission(
        self,
        *,
        title: str,
        owner_id: str,
        description: str = "",
        kpis: list[GoalKPI] | None = None,
        employee_id: str | None = None,
        subscriptions: list[str] | None = None,
        priority: str = "medium",
    ) -> MissionOrchestrator:
        """Create, register and warm-start (CREATED→ACTIVE→WAITING) a mission."""
        mission = Mission(
            tenant_id=self.tenant_id,
            owner_id=owner_id,
            title=title,
            description=description,
            kpis=kpis or [],
            priority=priority,
        )
        orch = MissionOrchestrator(mission, now_fn=self._now_fn)
        orch.start(now=self._now())
        if employee_id:
            orch.assign_employee(employee_id)
        self.register(orch, subscriptions=subscriptions)
        self._events.extend(orch.events)
        return orch

    def get(self, mission_id: str) -> MissionOrchestrator | None:
        return self._orchestrators.get(mission_id)

    def list_missions(self) -> list[MissionOrchestrator]:
        return list(self._orchestrators.values())

    # ── fan-out (one event → many missions) ──────────────────────────────────

    def _match_missions(self, sources: list[str] | None) -> list[MissionOrchestrator]:
        if not sources:
            return []
        matched: set[str] = set()
        for src in sources:
            matched |= self._subscriptions.get(src, set())
        return [self._orchestrators[i] for i in matched if i in self._orchestrators]

    def ingest_event(
        self,
        evidence: Any,
        *,
        sources: list[str] | None = None,
    ) -> list[MissionEvent]:
        """Fan a single enterprise event out to every subscribed mission.

        Returns the emitted events (workspace/SSE consumers typically drain
        ``drain_events``).

        by domain. ``sources`` is a list of the source systems/domains this
        event touches (e.g. ``["slack:revenue-alerts", "salesforce"]``).
        """
        emitted: list[MissionEvent] = []
        for orch in self._match_missions(sources):
            emitted.extend(orch.on_event(evidence, now=self._now()))
        self._events.extend(emitted)
        return emitted

    def signal(self, mission_id: str, kind: str, **payload: Any) -> list[MissionEvent]:
        """Send a typed signal to a single mission (human interrupt +)."""
        orch = self._orchestrators[mission_id]
        emitted = orch.apply_signal(kind, now=self._now(), **payload)
        self._events.extend(emitted)
        return emitted

    # ── proactive review ─────────────────────────────────────────────────────

    def run_due_reviews(self, *, now: datetime | None = None) -> list[MissionEvent]:
        """Wake every mission whose review window has elapsed, even if nothing
        happened (the "mission never sleeps" guarantee)."""
        t = now or self._now()
        emitted: list[MissionEvent] = []
        for orch in self.list_missions():
            if orch.review_due(t):
                emitted.extend(orch.review(now=t))
        self._events.extend(emitted)
        return emitted

    # ── workspace / SSE outbox ───────────────────────────────────────────────

    def drain_events(self) -> list[MissionEvent]:
        """Consume and clear the emitted-event outbox (for SSE broadcast)."""
        batch = self._events
        self._events = []
        return batch

    def mission_card(self, mission_id: str) -> dict[str, Any] | None:
        """A serialisable "mission card" for the workspace (Monday-morning view)."""
        orch = self._orchestrators.get(mission_id)
        if orch is None:
            return None
        m = orch.mission
        return {
            "mission_id": orch.mission.id,
            "name": m.title,
            "owner": m.owner_id,
            "status": orch.phase.value,
            "confidence": round(m.confidence, 4),
            "evidence_count": orch.evidence_count,
            "priority": orch.priority,
            "worker": orch.current_employee_id,
            "directive": orch.active_directive,
            "last_observed_at": orch.last_observed_at.isoformat() if orch.last_observed_at else None,
            "next_review_at": orch.next_review_at.isoformat() if orch.next_review_at else None,
            "epoch": orch.epoch,
            "planned": orch.plan_id is not None,
        }


__all__ = ["MissionCoordinator"]