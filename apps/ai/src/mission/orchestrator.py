"""Mission Orchestrator — deterministic, replay-safe orchestration of persistent AI employees.

This is the operational heart that proves a *continuously operating AI
employee*: a mission survives for days, not requests.

The orchestrator owns the Temporal-workflow-equivalent behaviour:

- a FATAL, replay-safe event log (reconstruct identical state by replaying inputs);
- a **signal surface** for every human interrupt (pause / resume / redirect /
  escalate / reprioritize / interrupt / retry / approve / reject / replan);
- **ContinueAsNew** via ``snapshot()`` / ``resume_from()`` (compact serialisable
  state that survives restarts and time travel);
- an idempotent event ingestion path (duplicate evidence is a no-op);
- a **proactive Mission Review** loop: every mission wakes up on schedule even
  if nothing happened, checks assumptions / stale evidence / investigation need,
  then sleeps again.

Frozen mission phases (V6) — exactly eleven, do not invent more:

    CREATED, ACTIVE, WAITING, INVESTIGATING, AWAITING_APPROVAL, EXECUTING,
    MONITORING, COMPLETED, ARCHIVED, FAILED, PAUSED

Design constraints
------------------
- The orchestrator is a **pure state machine**. Every transition is a
  deterministic function of ``(current_phase, input)`` with an injected clock.
  No I/O, no randomness, no LLM calls inside.
- Side effects (running an employee, writing to the workspace, recording an
  evaluation) are *emitted* as :class:`MissionEvent` s and fed back in by a
  runner — mirroring Temporal activities.
- Event ids are deterministic (``{mission}:{type}:{seq}``) so a replayed input
  stream reproduces byte-identical state. See :meth:`MissionOrchestrator.replay`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable

from src.goal.models import GoalKPI
from src.mission.runtime import Mission, MissionStatus

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ───────────────────────────────────────────────────────────────────


class MissionPhase(str, Enum):
    """The eleven frozen operational phases of a mission."""

    CREATED = "created"
    ACTIVE = "active"
    WAITING = "waiting"
    INVESTIGATING = "investigating"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    FAILED = "failed"
    PAUSED = "paused"


class MissionEventType(str, Enum):
    """Typed, workspace-deciding events the orchestrator emits.

    Each event type maps (in the Go workspace adapter) to a specific SSE event
    name and the HTMX component it should update — the Workspace decides which
    component to refresh from the event type, not a generic ``workspace_refresh``.
    """

    MISSION_CREATED = "mission_created"
    MISSION_STATUS_CHANGED = "mission_status_changed"
    MISSION_CONFIDENCE_CHANGED = "mission_confidence_changed"
    NEW_EVIDENCE = "new_evidence"
    SIGNAL_APPLIED = "signal_applied"
    REVIEW_COMPLETED = "review_completed"
    MISSION_REPLANNED = "mission_replanned"
    NEW_RECOMMENDATION = "new_recommendation"
    EVALUATION_RECORDED = "evaluation_recorded"
    MISSION_ESCALATED = "mission_escalated"
    MISSION_INTERRUPTED = "mission_interrupted"
    MISSION_FAILED = "mission_failed"
    MISSION_COMPLETED = "mission_completed"
    MISSION_PAUSED = "mission_paused"
    MISSION_RETRIED = "mission_retried"

    # ── aliases (kept for backward compatibility with existing callers/tests) ──
    CREATED = MISSION_CREATED
    STATE_CHANGED = MISSION_STATUS_CHANGED
    CONFIDENCE_CHANGED = MISSION_CONFIDENCE_CHANGED
    REPLANNED = MISSION_REPLANNED
    ESCALATED = MISSION_ESCALATED
    INTERRUPTED = MISSION_INTERRUPTED


# ── Events ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MissionEvent:
    """An emitted event. Immutable so it is safe to fan out to SSE/workspace."""

    id: str
    mission_id: str
    type: MissionEventType
    payload: dict[str, Any]
    timestamp: str  # ISO-8601, injected for determinism
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "type": self.type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionEvent":
        return cls(
            id=data["id"],
            mission_id=data["mission_id"],
            type=MissionEventType(data["type"]),
            payload=data.get("payload", {}),
            timestamp=data["timestamp"],
            version=data.get("version", 1),
        )


# Frozen phase → high-level MissionStatus mapping (for persistence/reporting).
_PHASE_TO_STATUS: dict[MissionPhase, MissionStatus] = {
    MissionPhase.CREATED: MissionStatus.PENDING,
    MissionPhase.ACTIVE: MissionStatus.ACTIVE,
    MissionPhase.WAITING: MissionStatus.ACTIVE,
    MissionPhase.INVESTIGATING: MissionStatus.ACTIVE,
    MissionPhase.AWAITING_APPROVAL: MissionStatus.ACTIVE,
    MissionPhase.EXECUTING: MissionStatus.ACTIVE,
    MissionPhase.MONITORING: MissionStatus.ACTIVE,
    MissionPhase.PAUSED: MissionStatus.STALLED,
    MissionPhase.COMPLETED: MissionStatus.COMPLETED,
    MissionPhase.ARCHIVED: MissionStatus.ARCHIVED,
    MissionPhase.FAILED: MissionStatus.FAILED,
}

# Terminal / non-interruptible phases.
_TERMINAL_PHASES = {
    MissionPhase.COMPLETED,
    MissionPhase.ARCHIVED,
    MissionPhase.FAILED,
}


# ── Serialization helpers ───────────────────────────────────────────────────


def _mission_to_dict(mission: Mission) -> dict[str, Any]:
    return {
        "id": mission.id,
        "tenant_id": mission.tenant_id,
        "title": mission.title,
        "description": mission.description,
        "owner_id": mission.owner_id,
        "status": mission.status.value,
        "kpis": [k.model_dump(mode="json") for k in mission.kpis],
        "kpi_scores": dict(mission.kpi_scores),
        "confidence": mission.confidence,
        "priority": mission.priority,
        "evidence_ids": list(mission.evidence_ids),
        "knowledge_ids": list(mission.knowledge_ids),
        "decision_ids": list(mission.decision_ids),
        "temporal_workflow_id": mission.temporal_workflow_id,
        "created_at": mission.created_at.isoformat(),
        "updated_at": mission.updated_at.isoformat(),
    }


def _mission_from_dict(data: dict[str, Any]) -> Mission:
    return Mission(
        id=data["id"],
        tenant_id=data["tenant_id"],
        title=data["title"],
        description=data.get("description", ""),
        owner_id=data.get("owner_id", ""),
        status=MissionStatus(data["status"]),
        kpis=[GoalKPI.model_validate(k) for k in data.get("kpis", [])],
        kpi_scores=data.get("kpi_scores", {}),
        confidence=data.get("confidence", 0.0),
        priority=data.get("priority", "medium"),
        evidence_ids=data.get("evidence_ids", []),
        knowledge_ids=data.get("knowledge_ids", []),
        decision_ids=data.get("decision_ids", []),
        temporal_workflow_id=data.get("temporal_workflow_id"),
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
    )


# ── Orchestrator ────────────────────────────────────────────────────────────


class MissionOrchestrator:
    """Deterministic, replay-safe orchestrator for a single persistent mission.

    A runner drives it: call the signal/event methods, collect the emitted
    :class:`MissionEvent` s, execute employees as activities, and feed the
    results back (``investigate`` / ``execution_complete``).
    """

    #: Confidence delta considered material (triggers a confidence_changed event).
    CONFIDENCE_MATERIALITY = 0.05
    #: Evidence older than this is flagged as stale during review.
    STALE_AFTER = timedelta(hours=24)
    #: Default mission-review cadence (wake up even if nothing happened).
    DEFAULT_REVIEW_INTERVAL = timedelta(hours=12)

    def __init__(
        self,
        mission: Mission,
        *,
        now_fn: Callable[[], datetime] = _utcnow,
        review_interval: timedelta = DEFAULT_REVIEW_INTERVAL,
    ) -> None:
        self.mission = mission
        self._now_fn = now_fn
        self.review_interval = review_interval

        self.phase: MissionPhase = MissionPhase.CREATED
        self.epoch: int = 0
        self.priority: str = "medium"
        self.current_employee_id: str | None = None
        self.active_directive: str | None = None
        self.plan_id: str | None = None
        self.retry_count: int = 0
        self.interruption_count: int = 0
        self.escalation_count: int = 0
        self.resume_from_phase: str | None = None
        self.last_observed_at: datetime | None = None
        self._next_review_at: datetime | None = None

        self._seq: int = 0
        self._processed: set[str] = set()
        self._log: list[MissionEvent] = []
        self._input_log: list[dict[str, Any]] = []

    # ── clock ────────────────────────────────────────────────────────────────

    def _now(self, now: datetime | None = None) -> datetime:
        return now or self._now_fn()

    # ── primitives ───────────────────────────────────────────────────────────

    def _emit(self, type_: MissionEventType, payload: dict[str, Any], now: datetime) -> MissionEvent:
        """Append a new event with a deterministic id derived from the sequence."""
        self._seq += 1
        event = MissionEvent(
            id=f"{self.mission.id}:{type_.value}:{self._seq}",
            mission_id=self.mission.id,
            type=type_,
            payload=payload,
            timestamp=now.isoformat(),
        )
        self._log.append(event)
        return event

    def _transition(self, new_phase: MissionPhase, cause: str, now: datetime) -> MissionEvent:
        prev = self.phase
        self.phase = new_phase
        self.mission.status = _PHASE_TO_STATUS[new_phase]
        self.mission.updated_at = now
        return self._emit(
            MissionEventType.MISSION_STATUS_CHANGED,
            {"from": prev.value, "to": new_phase.value, "cause": cause},
            now,
        )

    def _kpi_confidence(self, kpi: GoalKPI) -> float:
        """Direction-aware KPI confidence (mirrors GoalRuntime math, deterministic)."""
        if kpi.current_value is None:
            return 0.0
        baseline = kpi.baseline_value
        target = kpi.target_value
        current = kpi.current_value
        total_span = abs(target - baseline)
        if total_span == 0:
            return 1.0
        if kpi.direction == "decrease":
            progress = (baseline - current) / total_span
        else:
            progress = (current - baseline) / total_span
        return max(0.0, min(1.0, progress))

    def _recompute_confidence(self) -> float:
        if not self.mission.kpis:
            # no KPI targets → keep current confidence
            return self.mission.confidence
        scores = [self._kpi_confidence(k) for k in self.mission.kpis]
        return sum(scores) / len(scores)

    # ── lifecycle: start & observe ───────────────────────────────────────────

    def start(self, *, now: datetime | None = None) -> list[MissionEvent]:
        """CREATED → ACTIVE → WAITING. Schedules the first proactive review."""
        if self.phase != MissionPhase.CREATED:
            return []
        t = self._now(now)
        events = [self._transition(MissionPhase.ACTIVE, "mission_started", t)]
        events.append(self._transition(MissionPhase.WAITING, "idle_waiting_for_work", t))
        self._next_review_at = t + self.review_interval
        events.append(
            self._emit(MissionEventType.MISSION_CREATED, {"title": self.mission.title}, t)
        )
        self._record_input("start", {}, t)
        return events

    def assign_employee(self, employee_id: str) -> None:
        """Bind an AI employee (worker) to this mission."""
        self.current_employee_id = employee_id
        self._record_input("assign_employee", {"employee_id": employee_id}, self._now())

    def on_event(self, evidence: Any, *, now: datetime | None = None) -> list[MissionEvent]:
        """Ingest one EvidenceRecord / enterprise event (idempotent).

        WAITING / MONITORING → INVESTIGATING. Re-evaluates confidence from
        evidence + tracked KPIs. Duplicate evidence ids are no-ops.
        """
        t = self._now(now)
        evidence_id, structured = self._normalize_evidence(evidence)
        if evidence_id in self._processed:
            return []
        if self.phase in _TERMINAL_PHASES or self.phase == MissionPhase.PAUSED:
            return []
        self._processed.add(evidence_id)
        self._record_input("on_event", {"evidence_id": evidence_id, "kpi_scores": structured.get("kpi_scores")}, t)

        if evidence_id not in self.mission.evidence_ids:
            self.mission.evidence_ids.append(evidence_id)
        self.last_observed_at = t

        # Apply KPI deltas carried by the evidence (structured_data["kpi_scores"]).
        kpi_scores = structured.get("kpi_scores")
        if kpi_scores and self.mission.kpis:
            for kpi in self.mission.kpis:
                if kpi.name in kpi_scores:
                    kpi.current_value = float(kpi_scores[kpi.name])

        prev = self.mission.confidence
        self.mission.confidence = self._recompute_confidence()
        self.mission.updated_at = t

        events: list[MissionEvent] = [
            self._emit(MissionEventType.NEW_EVIDENCE, {"evidence_id": evidence_id}, t)
        ]
        if abs(self.mission.confidence - prev) >= self.CONFIDENCE_MATERIALITY:
            events.append(
                self._emit(
                    MissionEventType.MISSION_CONFIDENCE_CHANGED,
                    {"from": prev, "to": self.mission.confidence, "evidence_id": evidence_id},
                    t,
                )
            )

        if self.phase in (MissionPhase.WAITING, MissionPhase.MONITORING, MissionPhase.ACTIVE):
            events.append(self._transition(MissionPhase.INVESTIGATING, "new_evidence", t))
        return events

    @staticmethod
    def _normalize_evidence(evidence: Any) -> tuple[str, dict[str, Any]]:
        """Extract ``(evidence_id, structured_data)`` from a record or dict."""
        if isinstance(evidence, dict):
            structured = evidence.get("structured_data") or {}
            return str(evidence.get("id") or ""), structured
        return str(getattr(evidence, "id", "")), getattr(evidence, "structured_data", None) or {}

    def investigate(
        self,
        *,
        needs_approval: bool = False,
        evidence_ids: list[str] | None = None,
        employee_id: str | None = None,
        now: datetime | None = None,
    ) -> list[MissionEvent]:
        """Finish investigation (an activity result). Route to approval/executing."""
        if self.phase != MissionPhase.INVESTIGATING:
            return []
        t = self._now(now)
        if employee_id:
            self.current_employee_id = employee_id
        self._record_input(
            "investigate",
            {
                "needs_approval": needs_approval,
                "evidence_ids": evidence_ids or list(self.mission.evidence_ids),
                "employee_id": employee_id,
            },
            t,
        )
        if needs_approval:
            events = [self._transition(MissionPhase.AWAITING_APPROVAL, "risk_requires_approval", t)]
        else:
            events = [self._transition(MissionPhase.EXECUTING, "investigation_complete", t)]
        events.append(
            self._emit(
                MissionEventType.NEW_RECOMMENDATION,
                {"needs_approval": needs_approval, "mission_id": self.mission.id},
                t,
            )
        )
        return events

    # ── approval ─────────────────────────────────────────────────────────────

    def approve(self, *, now: datetime | None = None) -> list[MissionEvent]:
        """Human approves the plan: AWAITING_APPROVAL → EXECUTING."""
        if self.phase != MissionPhase.AWAITING_APPROVAL:
            return []
        t = self._now(now)
        self._record_input("approve", {}, t)
        return [self._transition(MissionPhase.EXECUTING, "approved", t)]

    def reject(self, *, now: datetime | None = None) -> list[MissionEvent]:
        """Human rejects: AWAITING_APPROVAL → WAITING (worker replans)."""
        if self.phase != MissionPhase.AWAITING_APPROVAL:
            return []
        t = self._now(now)
        self._record_input("reject", {}, t)
        events = [self._transition(MissionPhase.WAITING, "rejected", t)]
        events.append(self._emit(MissionEventType.MISSION_REPLANNED, {"cause": "rejected"}, t))
        return events

    # ── execution ────────────────────────────────────────────────────────────

    def execution_complete(
        self,
        *,
        success: bool,
        kpi_updates: dict[str, float] | None = None,
        outcome: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> list[MissionEvent]:
        """Record an activity result: EXECUTING → MONITORING (success) or FAILED."""
        if self.phase != MissionPhase.EXECUTING:
            return []
        t = self._now(now)

        if kpi_updates and self.mission.kpis:
            for kpi in self.mission.kpis:
                if kpi.name in kpi_updates:
                    kpi.current_value = float(kpi_updates[kpi.name])
        prev = self.mission.confidence
        self.mission.confidence = self._recompute_confidence()
        self._record_input(
            "execution",
            {"success": success, "kpi_updates": kpi_updates, "outcome": outcome},
            t,
        )

        events: list[MissionEvent] = []
        # Operational Learning: record expected → actual → delta → confidence.
        events.append(
            self._emit(
                MissionEventType.EVALUATION_RECORDED,
                {
                    "expected": prev,
                    "actual": self.mission.confidence,
                    "delta": round(self.mission.confidence - prev, 4),
                    "confidence": self.mission.confidence,
                    "outcome": outcome or {},
                },
                t,
            )
        )

        if success:
            events.append(self._transition(MissionPhase.MONITORING, "execution_succeeded", t))
            if self._next_review_at is None:
                self._next_review_at = t + self.review_interval
            if self.mission.confidence >= 0.9:
                events.append(self._transition(MissionPhase.COMPLETED, "kpis_met", t))
                events.append(
                    self._emit(MissionEventType.MISSION_COMPLETED, {}, t)
                )
        else:
            events.append(self._transition(MissionPhase.FAILED, "execution_failed", t))
            events.append(self._emit(MissionEventType.MISSION_FAILED, {}, t))
        return events

    def retry(self, *, now: datetime | None = None) -> list[MissionEvent]:
        """FAILED → INVESTIGATING (retry the execution path)."""
        if self.phase != MissionPhase.FAILED:
            return []
        t = self._now(now)
        self.retry_count += 1
        self._record_input("retry", {"retry_count": self.retry_count}, t)
        events = [self._transition(MissionPhase.INVESTIGATING, "retry", t)]
        events.append(
            self._emit(MissionEventType.MISSION_RETRIED, {"retry_count": self.retry_count}, t)
        )
        return events

    # ── human interrupt signals ──────────────────────────────────────────────

    def pause(self, *, now: datetime | None = None) -> list[MissionEvent]:
        """Pause a mission (idempotent). Remembers where it was."""
        if self.phase == MissionPhase.PAUSED or self.phase in _TERMINAL_PHASES:
            return []
        t = self._now(now)
        self.resume_from_phase = self.phase.value
        self._record_input("pause", {}, t)
        events = [self._transition(MissionPhase.PAUSED, "paused", t)]
        events.append(self._emit(MissionEventType.MISSION_PAUSED, {"resume_from": self.resume_from_phase}, t))
        return events

    def resume(self, *, to_phase: str | None = None, now: datetime | None = None) -> list[MissionEvent]:
        """Resume a paused mission back to its previous phase."""
        if self.phase != MissionPhase.PAUSED:
            return []
        t = self._now(now)
        target = to_phase or self.resume_from_phase or MissionPhase.WAITING.value
        # Resuming always lands in a listening phase so the loop can re-observe.
        if target in (MissionPhase.INVESTIGATING.value, MissionPhase.EXECUTING.value):
            target = MissionPhase.INVESTIGATING.value
        self.resume_from_phase = None
        self._next_review_at = t + self.review_interval
        self._record_input("resume", {"to_phase": target}, t)
        events = [self._transition(MissionPhase(target), "resumed", t)]
        events.append(self._emit(MissionEventType.SIGNAL_APPLIED, {"signal": "resume"}, t))
        return events

    def reprioritize(self, priority: str, *, now: datetime | None = None) -> list[MissionEvent]:
        """Change mission priority (idempotent if unchanged)."""
        if priority == self.priority:
            return []
        if self.phase in _TERMINAL_PHASES:
            return []
        self.priority = priority
        t = self._now(now)
        self._record_input("reprioritize", {"priority": priority}, t)
        events = [
            self._emit(
                MissionEventType.SIGNAL_APPLIED,
                {"signal": "reprioritize", "priority": priority},
                t,
            ),
        ]
        return events

    def escalate(self, *, reason: str = "", now: datetime | None = None) -> list[MissionEvent]:
        """Escalate: bump priority and surface for human attention."""
        if self.phase in _TERMINAL_PHASES or self.phase == MissionPhase.PAUSED:
            return []
        t = self._now(now)
        self.escalation_count += 1
        if self.priority == "low":
            self.priority = "medium"
        elif self.priority == "medium":
            self.priority = "high"
        elif self.priority == "high":
            self.priority = "critical"
        self._record_input("escalate", {"reason": reason, "priority": self.priority}, t)
        events: list[MissionEvent] = [
            self._emit(
                MissionEventType.MISSION_ESCALATED,
                {"priority": self.priority, "reason": reason},
                t,
            ),
        ]
        # Idle missions go to approval to ensure a human attends to the escalation.
        if self.phase in (
            MissionPhase.WAITING,
            MissionPhase.MONITORING,
            MissionPhase.INVESTIGATING,
        ):
            events.append(self._transition(MissionPhase.AWAITING_APPROVAL, "escalated", t))
        return events

    def redirect(
        self,
        employee_id: str | None = None,
        directive: str | None = None,
        *,
        now: datetime | None = None,
    ) -> list[MissionEvent]:
        """Human redirects the worker / adds a directive. Interrupts and replans."""
        if self.phase in _TERMINAL_PHASES or self.phase == MissionPhase.PAUSED:
            return []
        t = self._now(now)
        if employee_id:
            self.current_employee_id = employee_id
        if directive:
            self.active_directive = directive
        self._record_input(
            "redirect",
            {"employee_id": employee_id, "directive": directive},
            t,
        )
        events: list[MissionEvent] = []
        if self.phase in (MissionPhase.EXECUTING, MissionPhase.INVESTIGATING):
            events.append(self._transition(MissionPhase.WAITING, "interrupted_by_redirect", t))
            self.interruption_count += 1
            events.append(self._emit(MissionEventType.MISSION_INTERRUPTED, {"cause": "redirect"}, t))
        events.append(self._transition(MissionPhase.INVESTIGATING, "redirect", t))
        events.append(
            self._emit(
                MissionEventType.MISSION_REPLANNED,
                {"cause": "redirect", "directive": directive},
                t,
            )
        )
        return events

    def interrupt(self, *, now: datetime | None = None) -> list[MissionEvent]:
        """Interrupt active work back to WAITING."""
        if self.phase not in (
            MissionPhase.EXECUTING,
            MissionPhase.INVESTIGATING,
            MissionPhase.AWAITING_APPROVAL,
        ):
            return []
        t = self._now(now)
        self.interruption_count += 1
        self._record_input("interrupt", {}, t)
        events = [self._transition(MissionPhase.WAITING, "interrupted", t)]
        events.append(self._emit(MissionEventType.MISSION_INTERRUPTED, {"cause": "human_interrupt"}, t))
        return events

    def replan(self, *, employee_id: str | None = None, now: datetime | None = None) -> list[MissionEvent]:
        """Force a replan from any active phase → INVESTIGATING."""
        if self.phase in _TERMINAL_PHASES or self.phase == MissionPhase.PAUSED:
            return []
        if employee_id:
            self.current_employee_id = employee_id
        t = self._now(now)
        self._record_input("replan", {"employee_id": employee_id}, t)
        events: list[MissionEvent] = []
        if self.phase != MissionPhase.INVESTIGATING:
            events.append(self._transition(MissionPhase.INVESTIGATING, "force_replan", t))
        events.append(self._emit(MissionEventType.MISSION_REPLANNED, {"cause": "manual"}, t))
        return events

    # ── proactive review ─────────────────────────────────────────────────────

    def review_due(self, now: datetime | None = None) -> bool:
        t = self._now(now)
        if self._next_review_at is None:
            return False
        return t >= self._next_review_at

    def review(self, *, now: datetime | None = None) -> list[MissionEvent]:
        """Proactive wake-up: even with no new event, evaluate the mission.

        Flags stale evidence / missing investigation / KPI drift; if any,
        replans -> INVESTIGATING. Otherwise reschedules and stays idle.
        """
        if self.phase not in (MissionPhase.WAITING, MissionPhase.MONITORING):
            return []
        t = self._now(now)
        findings: list[str] = []

        if not self.mission.evidence_ids:
            findings.append("no_evidence_yet")
        if self.last_observed_at is None or (t - self.last_observed_at) > self.STALE_AFTER:
            findings.append("stale_evidence")
        low_kpis = [k.name for k in self.mission.kpis if self._kpi_confidence(k) < 0.3]
        if low_kpis:
            findings.append(f"kpi_drift:{','.join(low_kpis)}")

        self._next_review_at = t + self.review_interval
        self._record_input("review", {}, t)
        events: list[MissionEvent] = [self._emit(MissionEventType.REVIEW_COMPLETED, {"findings": findings}, t)]
        if findings:
            events.append(self._transition(MissionPhase.INVESTIGATING, "review_needs_work", t))
            events.append(self._emit(MissionEventType.MISSION_REPLANNED, {"cause": "periodic_review"}, t))
        return events

    # ── signal dispatch (mirrors Temporal signal handler surface) ───────────

    def apply_signal(self, kind: str, *, now: datetime | None = None, **payload: Any) -> list[MissionEvent]:
        """Route a named signal to its handler (Temporal-style)."""
        dispatcher: dict[str, Callable[[], list[MissionEvent]]] = {
            "pause": lambda: self.pause(now=now),
            "resume": lambda: self.resume(now=now),
            "redirect": lambda: self.redirect(payload.get("employee_id"), payload.get("directive"), now=now),
            "escalate": lambda: self.escalate(now=now, reason=payload.get("reason", "")),
            "reprioritize": lambda: self.reprioritize(payload.get("priority", "medium"), now=now),
            "interrupt": lambda: self.interrupt(now=now),
            "retry": lambda: self.retry(now=now),
            "approve": lambda: self.approve(now=now),
            "reject": lambda: self.reject(now=now),
            "replan": lambda: self.replan(now=now, employee_id=payload.get("employee_id")),
        }
        handler = dispatcher.get(kind)
        if handler is None:
            raise ValueError(f"Unknown mission signal: {kind}")
        return handler()

    # ── snapshot / ContinueAsNew ─────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Serialise the full orchestrator state (ContinueAsNew input)."""
        return {
            "mission": _mission_to_dict(self.mission),
            "phase": self.phase.value,
            "epoch": self.epoch,
            "seq": self._seq,
            "processed": sorted(self._processed),
            "log": [e.to_dict() for e in self._log],
            "inputs": list(self._input_log),
            "priority": self.priority,
            "current_employee_id": self.current_employee_id,
            "active_directive": self.active_directive,
            "plan_id": self.plan_id,
            "retry_count": self.retry_count,
            "interruption_count": self.interruption_count,
            "escalation_count": self.escalation_count,
            "resume_from_phase": self.resume_from_phase,
            "next_review_at": self._next_review_at.isoformat() if self._next_review_at else None,
            "last_observed_at": self.last_observed_at.isoformat() if self.last_observed_at else None,
        }

    @classmethod
    def resume_from(cls, state: dict[str, Any], *, now_fn: Callable[[], datetime] = _utcnow) -> "MissionOrchestrator":
        """Rebuild / continue from a snapshot (ContinueAsNew) with a fresh epoch."""
        orch = cls(_mission_from_dict(state["mission"]), now_fn=now_fn)
        orch.phase = MissionPhase(state["phase"])
        orch.epoch = int(state["epoch"]) + 1
        orch._seq = int(state["seq"])
        orch._processed = set(state.get("processed", []))
        orch._log = [MissionEvent.from_dict(e) for e in state.get("log", [])]
        orch._input_log = list(state.get("inputs", []))
        orch.priority = state.get("priority", "medium")
        orch.current_employee_id = state.get("current_employee_id")
        orch.active_directive = state.get("active_directive")
        orch.plan_id = state.get("plan_id")
        orch.retry_count = int(state.get("retry_count", 0))
        orch.interruption_count = int(state.get("interruption_count", 0))
        orch.escalation_count = int(state.get("escalation_count", 0))
        orch.resume_from_phase = state.get("resume_from_phase")
        orch._next_review_at = (
            datetime.fromisoformat(state["next_review_at"]) if state.get("next_review_at") else None
        )
        orch.last_observed_at = (
            datetime.fromisoformat(state["last_observed_at"]) if state.get("last_observed_at") else None
        )
        return orch

    # ── replay safety ────────────────────────────────────────────────────────

    def _record_input(self, kind: str, payload: dict[str, Any], now: datetime) -> None:
        """Record a deterministic input so the stream can be replayed."""
        self._input_log.append({"kind": kind, "payload": payload, "timestamp": now.isoformat()})

    def _replay_one(self, kind: str, payload: dict[str, Any], now: datetime) -> list[MissionEvent]:
        """Re-apply a single recorded input (ephemeral dispatch for replay)."""
        if kind == "start":
            return self.start(now=now)
        if kind == "on_event":
            return self.on_event(
                {"id": payload["evidence_id"], "structured_data": {"kpi_scores": payload.get("kpi_scores")}},
                now=now,
            )
        if kind == "assign_employee":
            self.assign_employee(payload["employee_id"])
            return []
        if kind == "investigate":
            return self.investigate(
                needs_approval=payload.get("needs_approval", False),
                employee_id=payload.get("employee_id"),
                now=now,
            )
        if kind == "execution":
            return self.execution_complete(
                success=payload.get("success", True),
                kpi_updates=payload.get("kpi_updates"),
                outcome=payload.get("outcome"),
                now=now,
            )
        if kind == "signal":
            return self.apply_signal(payload["kind"], now=now, **payload.get("args", {}))
        if kind == "review":
            return self.review(now=now)

        # Direct signal-kinds (each public mutator records its own input).
        signal_fn = {
            "approve": lambda: self.approve(now=now),
            "reject": lambda: self.reject(now=now),
            "retry": lambda: self.retry(now=now),
            "pause": lambda: self.pause(now=now),
            "resume": lambda: self.resume(now=now, to_phase=payload.get("to_phase")),
            "reprioritize": lambda: self.reprioritize(payload.get("priority", "medium"), now=now),
            "escalate": lambda: self.escalate(now=now, reason=payload.get("reason", "")),
            "redirect": lambda: self.redirect(payload.get("employee_id"), payload.get("directive"), now=now),
            "interrupt": lambda: self.interrupt(now=now),
            "replan": lambda: self.replan(now=now, employee_id=payload.get("employee_id")),
        }.get(kind)
        if signal_fn is None:
            raise ValueError(f"Unknown replay input: {kind}")
        return signal_fn()

    def replay(self, inputs: list[tuple[str, dict[str, Any]]] | None = None) -> "MissionOrchestrator":
        """Reproduce a byte-identical orchestrator by replaying recorded inputs.

        Defaults to replaying this instance's own ``_input_log``. Returns a
        fresh orchestrator whose observable state equals the original — the
        Temporal determinism / ContinueAsNew property.
        """
        stream = inputs if inputs is not None else [
            (e["kind"], e["payload"], e["timestamp"]) for e in self._input_log
        ]
        replay = MissionOrchestrator(
            Mission(
                id=self.mission.id,
                tenant_id=self.mission.tenant_id,
                title=self.mission.title,
                owner_id=self.mission.owner_id,
                kpis=[k.model_copy(deep=True) for k in self.mission.kpis],
            ),
            now_fn=self._now_fn,
            review_interval=self.review_interval,
        )
        for kind, payload, ts in stream:
            t = datetime.fromisoformat(ts)
            replay._replay_one(kind, payload, t)
        return replay

    def state_equals(self, other: "MissionOrchestrator") -> bool:
        """Compare observable state (not log/seq) for replay-equality checks."""
        return (
            self.phase == other.phase
            and self.priority == other.priority
            and self.mission.confidence == other.mission.confidence
            and self.mission.evidence_ids == other.mission.evidence_ids
            and self.evidence_count == other.evidence_count
            and self.retry_count == other.retry_count
            and self.interruption_count == other.interruption_count
            and self.escalation_count == other.escalation_count
            and self._next_review_at == other._next_review_at
            and self.current_employee_id == other.current_employee_id
            and self.active_directive == other.active_directive
        )

    def _empty_like(self, mission_id: str) -> "MissionOrchestrator":
        """A blank orchestrator sharing this mission's id (for replay)."""
        m = Mission(id=mission_id, tenant_id=self.mission.tenant_id, title=self.mission.title)
        return MissionOrchestrator(m, now_fn=self._now_fn, review_interval=self.review_interval)

    # ── introspection ────────────────────────────────────────────────────────

    @property
    def events(self) -> list[MissionEvent]:
        """Every event emitted by this orchestrator (log tail)."""
        return list(self._log)

    @property
    def mission_status(self) -> MissionStatus:
        return self.mission.status

    @property
    def next_review_at(self) -> datetime | None:
        return self._next_review_at

    @property
    def evidence_count(self) -> int:
        return len(self.mission.evidence_ids)


__all__ = [
    "MissionPhase",
    "MissionEventType",
    "MissionEvent",
    "MissionOrchestrator",
    "_PHASE_TO_STATUS",
]