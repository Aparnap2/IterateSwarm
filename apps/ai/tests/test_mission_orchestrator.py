"""Tests for the Mission Orchestrator — persistent, continuously operating missions.

Covers:
- the eleven frozen phases and status mapping;
- the full signal surface (pause/resume/redirect/escalate/reprioritize/interrupt/retry/approve/reject/replan);
- idempotency (duplicate evidence + no-op signals);
- replay safety (Temporal determinism) and ContinueAsNew (snapshot/resume_from);
- the proactive review loop (missions wake up even when nothing happened);
- MissionCoordinator fan-out (one enterprise event → many missions).
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.goal.models import GoalKPI
from src.mission.coordinator import MissionCoordinator
from src.mission.orchestrator import (
    MissionEventType,
    MissionOrchestrator,
    MissionPhase,
)
from src.mission.runtime import Mission, MissionStatus


def _kpi(name="MRR", current=50.0, target=100.0, direction="increase"):
    return GoalKPI(
        id=f"kpi_{name}",
        goal_id="",
        name=name,
        target_value=target,
        baseline_value=0.0,
        current_value=current,
        unit="USD",
        direction=direction,
    )


def _mission(kpi=None, mission_id="m-1", title="Revenue Health"):
    return Mission(
        id=mission_id,
        tenant_id="t1",
        title=title,
        owner_id="ceo@co.com",
        kpis=[kpi] if kpi else [],
    )


def _mk(**kwargs):
    kwargs.setdefault("kpi", _kpi())
    kwargs.setdefault("mission_id", "m-1")
    return MissionOrchestrator(_mission(**kwargs))


class TestFrozenPhases:

    def test_exactly_eleven_frozen_phases(self):
        expected = {
            "created", "active", "waiting", "investigating", "awaiting_approval",
            "executing", "monitoring", "completed", "archived", "failed", "paused",
        }
        assert {p.value for p in MissionPhase} == expected

    def test_status_mapping(self):
        assert _PHASE_TO_STATUS[MissionPhase.CREATED] == MissionStatus.PENDING
        assert _PHASE_TO_STATUS[MissionPhase.WAITING] == MissionStatus.ACTIVE
        assert _PHASE_TO_STATUS[MissionPhase.PAUSED] == MissionStatus.STALLED
        assert _PHASE_TO_STATUS[MissionPhase.COMPLETED] == MissionStatus.COMPLETED
        assert _PHASE_TO_STATUS[MissionPhase.FAILED] == MissionStatus.FAILED
        assert _PHASE_TO_STATUS[MissionPhase.ARCHIVED] == MissionStatus.ARCHIVED


class TestLifecycle:

    def test_start_transitions_created_to_waiting(self):
        o = _mk()
        assert o.phase == MissionPhase.CREATED
        o.start()
        assert o.phase == MissionPhase.WAITING
        assert o.mission_status == MissionStatus.ACTIVE
        assert o.next_review_at is not None

    def test_start_is_idempotent(self):
        o = _mk()
        o.start()
        events = o.start()
        assert events == []
        assert o.phase == MissionPhase.WAITING

    def test_event_triggers_investigating(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {}})
        assert o.phase == MissionPhase.INVESTIGATING
        assert o.evidence_count == 1

    def test_duplicate_event_is_noop(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {}})
        o.on_event({"id": "ev1", "structured_data": {}})
        assert o.evidence_count == 1

    def test_low_risk_executes_without_approval(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {}})
        o.investigate(needs_approval=False)
        assert o.phase == MissionPhase.EXECUTING

    def test_high_risk_awaits_approval(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {}})
        o.investigate(needs_approval=True)
        assert o.phase == MissionPhase.AWAITING_APPROVAL

    def test_approve_to_executing(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {}})
        o.investigate(needs_approval=True)
        o.approve()
        assert o.phase == MissionPhase.EXECUTING

    def test_reject_returns_to_waiting_and_replans(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {}})
        o.investigate(needs_approval=True)
        o.reject()
        assert o.phase == MissionPhase.WAITING
        assert any(e.type == MissionEventType.REPLANNED for e in o.events)

    def test_successful_execution_goes_monitoring(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {"kpi_scores": {"MRR": 40}}})
        o.investigate(needs_approval=False)
        o.execution_complete(success=True, kpi_updates={"MRR": 55})
        assert o.phase == MissionPhase.MONITORING
        assert o.mission.confidence == pytest.approx(0.55)

    def test_failed_execution_and_retry(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {}})
        o.investigate(needs_approval=False)
        o.execution_complete(success=False)
        assert o.phase == MissionPhase.FAILED
        o.retry()
        assert o.phase == MissionPhase.INVESTIGATING
        assert o.retry_count == 1

    def test_retry_only_from_failed(self):
        o = _mk()
        o.start()
        assert o.retry() == []
        assert o.retry_count == 0


class TestSignals:

    def test_pause_resume(self):
        o = _mk()
        o.start()
        o.pause()
        assert o.phase == MissionPhase.PAUSED
        assert o.resume_from_phase == "waiting"
        o.resume()
        assert o.phase == MissionPhase.WAITING

    def test_pause_is_idempotent(self):
        o = _mk()
        o.start()
        o.pause()
        assert o.pause() == []

    def test_resume_not_paused_is_noop(self):
        o = _mk()
        o.start()
        assert o.resume() == []

    def test_paused_mission_ignores_events(self):
        o = _mk()
        o.start()
        o.pause()
        assert o.on_event({"id": "ev1", "structured_data": {}}) == []
        assert o.evidence_count == 0

    def test_reprioritize_idempotent(self):
        o = _mk()
        o.start()
        o.reprioritize("high")
        assert o.priority == "high"
        assert o.reprioritize("high") == []  # same value → no-op

    def test_escalate_bumps_priority_and_requests_attention(self):
        o = _mk()
        o.start()
        o.escalate(reason="kpi dropping")
        assert o.priority == "high"
        assert o.escalation_count == 1
        assert o.phase == MissionPhase.AWAITING_APPROVAL

    def test_redirect_interrupts_and_replans(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {}})
        o.investigate(needs_approval=False)
        o.redirect(employee_id="revops-analyst", directive="Ignore SMB. Focus Enterprise.")
        assert o.phase == MissionPhase.INVESTIGATING
        assert o.current_employee_id == "revops-analyst"
        assert o.active_directive == "Ignore SMB. Focus Enterprise."
        assert o.interruption_count == 1
        assert any(e.type == MissionEventType.REPLANNED for e in o.events)

    def test_interrupt_returns_to_waiting(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {}})
        o.investigate(needs_approval=False)
        o.interrupt()
        assert o.phase == MissionPhase.WAITING
        assert o.interruption_count == 1

    def test_apply_signal_dispatch_and_unknown(self):
        o = _mk()
        o.start()
        o.apply_signal("pause")
        assert o.phase == MissionPhase.PAUSED
        o.apply_signal("resume")
        assert o.phase == MissionPhase.WAITING
        with pytest.raises(ValueError, match="Unknown mission signal"):
            o.apply_signal("delete_everything")


class TestContinueAsNewAndReplay:

    def test_snapshot_resume_increments_epoch(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {"kpi_scores": {"MRR": 40}}})
        o.investigate(needs_approval=False)
        o.execution_complete(success=True, kpi_updates={"MRR": 55})
        state = o.snapshot()

        o2 = MissionOrchestrator.resume_from(state)
        assert o2.epoch == o.epoch + 1
        assert o2.phase == o.phase
        assert o2.mission.confidence == o.mission.confidence
        assert o2.evidence_count == o.evidence_count

    def test_replay_reproduces_identical_state(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {"kpi_scores": {"MRR": 40}}})
        o.investigate(needs_approval=True)
        o.apply_signal("approve")
        o.execution_complete(success=True, kpi_updates={"MRR": 55})
        o.apply_signal("redirect", employee_id="revops-analyst", directive="focus enterprise")
        o.apply_signal("escalate", reason="dropping")
        o.interrupt()

        r = o.replay()
        assert r.state_equals(o)
        assert r.mission.confidence == o.mission.confidence
        assert r.priority == o.priority
        assert r.interruption_count == o.interruption_count
        assert r.escalation_count == o.escalation_count
        assert r.mission.evidence_ids == o.mission.evidence_ids

    def test_continue_as_new_replay_across_epochs(self):
        """A mission that survives a restart still replays to identical state."""
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {"kpi_scores": {"MRR": 40}}})
        o.execution_complete(success=True, kpi_updates={"MRR": 55})

        o2 = MissionOrchestrator.resume_from(o.snapshot())
        o2.on_event({"id": "ev2", "structured_data": {"kpi_scores": {"MRR": 60}}})
        o2.investigate(needs_approval=False)
        o2.execution_complete(success=True, kpi_updates={"MRR": 62})

        r = o2.replay()
        assert r.state_equals(o2)
        assert r.mission.confidence == pytest.approx(0.62)
        assert r.evidence_count == 2


class TestProactiveReview:

    def test_review_due_after_interval(self):
        t0 = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
        o = _mk()
        o.start(now=t0)
        assert not o.review_due(t0)
        assert o.review_due(t0 + timedelta(hours=12))

    def test_review_with_stale_evidence_replans(self):
        t0 = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
        o = _mk()
        o.start(now=t0)
        o.on_event({"id": "ev1", "structured_data": {}}, now=t0 + timedelta(minutes=1))
        o.investigate(needs_approval=False)
        o.execution_complete(success=True, now=t0 + timedelta(minutes=5))

        # 36 hours later, no events → evidence is stale → review replans.
        late = t0 + timedelta(hours=36)
        o.review(now=late)
        assert o.phase == MissionPhase.INVESTIGATING
        assert any(e.type == MissionEventType.REPLANNED for e in o.events)

    def test_review_with_fresh_evidence_stays_monitoring(self):
        t0 = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
        o = _mk()
        o.start(now=t0)
        o.on_event({"id": "ev1", "structured_data": {}}, now=t0 + timedelta(hours=2))
        o.investigate(needs_approval=False)
        o.execution_complete(success=True, now=t0 + timedelta(hours=3))

        o.review(now=t0 + timedelta(hours=12))
        assert o.phase == MissionPhase.MONITORING  # nothing stale
        assert o.next_review_at is not None  # rescheduled

    def test_review_only_when_idle(self):
        o = _mk()
        o.start()
        o.on_event({"id": "ev1", "structured_data": {}})
        assert o.review() == []  # INVESTIGATING → no self-review


class TestCoordinatorFanOut:

    def test_one_event_updates_many_missions(self):
        t0 = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
        c = MissionCoordinator(tenant_id="t1", now_fn=lambda: t0)
        rev = c.create_mission(
            title="Revenue Health", owner_id="ceo", kpis=[_kpi()],
            subscriptions=["salesforce", "slack:revenue-alerts"],
        )
        cus = c.create_mission(
            title="Customer Health", owner_id="cso",
            subscriptions=["salesforce", "slack:customer-alerts"],
        )
        roadmap = c.create_mission(
            title="Roadmap", owner_id="cto", subscriptions=["jira"],
        )

        # One Salesforce event touches Revenue + Customer, not Roadmap.
        emitted = c.ingest_event(
            {"id": "sf-1", "structured_data": {"kpi_scores": {"MRR": 40}}},
            sources=["salesforce"],
        )
        assert rev.phase == MissionPhase.INVESTIGATING
        assert cus.phase == MissionPhase.INVESTIGATING
        assert roadmap.phase == MissionPhase.WAITING
        assert emitted  # events were produced

    def test_mission_card_shape(self):
        t0 = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
        c = MissionCoordinator(tenant_id="t1", now_fn=lambda: t0)
        orch = c.create_mission(
            title="Revenue Health", owner_id="ceo@co.com", kpis=[_kpi()],
            employee_id="revops-analyst", subscriptions=["salesforce"],
        )
        card = c.mission_card(orch.mission.id)
        assert card["name"] == "Revenue Health"
        assert card["owner"] == "ceo@co.com"
        assert card["worker"] == "revops-analyst"
        assert card["status"] == "waiting"

    def test_run_due_reviews_wakes_sleeping_missions(self):
        t0 = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
        clock = [t0]
        c = MissionCoordinator(tenant_id="t1", now_fn=lambda: clock[0])
        c.create_mission(title="Revenue Health", owner_id="ceo", kpis=[_kpi()])

        clock[0] = t0 + timedelta(days=2)  # nothing happened for 2 days
        emitted = c.run_due_reviews()
        assert emitted
        orch = c.list_missions()[0]
        assert any(e.type == MissionEventType.REVIEW_COMPLETED for e in orch.events)
        assert any(e.type == MissionEventType.REPLANNED for e in orch.events)

    def test_drain_events_clears_outbox(self):
        c = MissionCoordinator(tenant_id="t1")
        c.create_mission(title="Revenue Health", owner_id="ceo", kpis=[_kpi()])
        first = c.drain_events()
        assert first  # creation events buffered
        assert c.drain_events() == []


# expose for the mapping test
from src.mission.orchestrator import _PHASE_TO_STATUS  # noqa: E402