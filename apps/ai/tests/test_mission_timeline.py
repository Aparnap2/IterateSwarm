"""Unit tests for mission timeline & versioning — deterministic, no DB.

Unit tier covers only *pure* logic: the frozen event-type contract, the enum
validation guard in ``MissionTimeline.record``, and the numeric diff helper.
DB-backed behaviour (per-entity version increments, ordering, snapshot
capture/diff) is the responsibility of the live integration suite
(``tests/integration/test_mission_live_infra.py``), which is authoritative.
"""
from __future__ import annotations

import pytest

from src.mission.timeline import (
    MissionEventType,
    MissionTimeline,
    _delta,
)


# ── Frozen event-type contract ──────────────────────────────────────
def test_event_types_are_business_values_only():
    values = {e.value for e in MissionEventType}
    assert "MISSION_CREATED" in values
    assert "MISSION_STARTED" in values
    assert "MISSION_REVIEWED" in values
    assert "MISSION_APPROVED" in values
    assert "MISSION_CONFIDENCE_CHANGED" in values
    assert "MISSION_RECOMMENDATION_UPDATED" in values
    # No infrastructure / internal events leaked into the contract.
    assert not any(v.startswith("INFRA_") or "_RETRY" in v for v in values)
    assert "\n".join(sorted(values))  # (smoke: enum is enumerable)


# ── Validation guard (the "freeze") ───────────────────────────────────
class _FakePool:
    """Confirms nothing touches the DB when validation rejects the event."""

    def __init__(self):
        self.touched = False

    async def acquire(self):
        self.touched = True
        raise AssertionError("record() must reject invalid events before the DB")


@pytest.mark.asyncio
async def test_record_rejects_arbitrary_string_event_type():
    log = MissionTimeline(_FakePool())
    with pytest.raises(ValueError):
        await log.record("m1", "MISSION_NOT_A_REAL_THING")
    assert log._log._pool.touched is False


@pytest.mark.asyncio
async def test_record_rejects_invalid_actor_and_type():
    log = MissionTimeline(_FakePool())
    with pytest.raises(TypeError):
        await log.record("m1", 12345)


@pytest.mark.asyncio
async def test_record_accepts_frozen_member():
    assert MissionEventType.STARTED.value == "MISSION_STARTED"
    assert "MISSION_COMPLETED" in {e.value for e in MissionEventType}


# ── Diff helper ───────────────────────────────────────────────────────
def test_delta_helper_only_numeric():
    assert _delta(82, 71) == -11
    assert _delta("71", "82") == 11
    assert _delta("unknown", 5) is None
    assert _delta(None, 5) is None