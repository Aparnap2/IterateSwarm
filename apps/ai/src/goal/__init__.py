"""Goal Runtime package for OntologyAI V6.

Exports the Goal domain models and runtime interfaces.

FROZEN — V6.0 M0.5
"""

from src.goal.models import (
    Goal,
    GoalKPI,
    GoalObservation,
    GoalPlan,
    GoalReview,
    GoalStatus,
)
from src.goal.runtime import (
    BaseGoalRuntime,
    DefaultGoalRuntime,
    GoalRuntime,
    GoalRuntimeError,
    PlanError,
)

__all__ = [
    "Goal",
    "GoalKPI",
    "GoalObservation",
    "GoalPlan",
    "GoalReview",
    "GoalStatus",
    "GoalRuntime",
    "BaseGoalRuntime",
    "DefaultGoalRuntime",
    "GoalRuntimeError",
    "PlanError",
]
