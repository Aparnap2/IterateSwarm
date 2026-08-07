"""Mission Runtime for OntologyAI V6.

Persistent long-running business objectives that AI Employees advance continuously.

Reframes the Goal Runtime as Missions with:
- PostgreSQL persistence via sqlc (mission_state table already exists)
- Temporal ContinueAsNew support
- Signal-aware for human interrupts

Reuses: src/goal/ (GoalRuntime, Goal, GoalKPI, etc.)
"""
from src.mission.runtime import (
    MissionRuntime,
    Mission,
    MissionState,
    MissionStatus,
)
from src.mission.orchestrator import (
    MissionOrchestrator,
    MissionPhase,
    MissionEvent,
    MissionEventType,
)
from src.mission.coordinator import MissionCoordinator

__all__ = [
    "MissionRuntime",
    "Mission",
    "MissionState",
    "MissionStatus",
    "MissionOrchestrator",
    "MissionPhase",
    "MissionEvent",
    "MissionEventType",
    "MissionCoordinator",
]
