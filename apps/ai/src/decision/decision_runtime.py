# FROZEN — V6.0 M0.5
"""OntologyAI V6 — Decision Runtime Interface (ABC).

The Decision Runtime is the **Layer 6** execution domain responsible for
LLM-led reasoning on options, tradeoffs, and risks, producing a single
recommendation with confidence and readiness tier, deterministic feasibility
scoring, and (future) what-if simulation.

This module defines the **frozen contract** that all Decision Runtime
implementations must satisfy.  It contains **no execution logic** — only
the abstract interface, type contracts, and error hierarchy.

Pipeline stages
---------------
1. **analyze**    — LLM leads reasoning on options, tradeoffs, risks.
2. **recommend**  — Single recommendation with confidence + readiness tier.
3. **simulate**   — What-if analysis (placeholder for M1).
4. **score**      — Deterministic feasibility scoring (8 dimensions).

Design constraints
------------------
* The LLM is the **lead author** of narrative fields (``root_cause``,
  ``rationale``, ``impact_summary``).  Structured fields are validated
  strictly via Pydantic.
* Recommendations are **advisory** — a human (or the risk-tiered policy
  engine) governs final approval.
* Feasibility scoring is **deterministic** — no LLM involvement.
* Simulation is a **placeholder** for M1; ``simulate()`` returns a
  stub result at M0.5.

FROZEN — V6.0 M0.5
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.decision.contracts import (
    DecisionAnalysis,
    DecisionContext,
    DecisionOption,
    FeasibilityResult,
    ReadinessTier,
    TradeOff,
)


# ── Error hierarchy ──────────────────────────────────────────────────────


class DecisionRuntimeError(Exception):
    """Base exception for all Decision Runtime failures."""


class AnalysisError(DecisionRuntimeError):
    """Raised when the LLM-driven analysis fails.

    Parameters
    ----------
    decision_id : str
        The decision ULID that failed analysis.
    reason : str
        Human-readable explanation.
    """

    def __init__(self, decision_id: str, reason: str) -> None:
        self.decision_id = decision_id
        self.reason = reason
        super().__init__(
            f"Analysis failed for decision '{decision_id}': {reason}"
        )


class RecommendationError(DecisionRuntimeError):
    """Raised when a recommendation cannot be produced.

    Parameters
    ----------
    decision_id : str
        The decision ULID.
    reason : str
        Human-readable explanation.
    """

    def __init__(self, decision_id: str, reason: str) -> None:
        self.decision_id = decision_id
        self.reason = reason
        super().__init__(
            f"Recommendation failed for decision '{decision_id}': {reason}"
        )


class SimulationError(DecisionRuntimeError):
    """Raised when what-if simulation fails.

    Parameters
    ----------
    decision_id : str
        The decision ULID.
    scenario : str
        Description of the scenario that was simulated.
    reason : str
        Human-readable explanation.
    """

    def __init__(self, decision_id: str, scenario: str, reason: str) -> None:
        self.decision_id = decision_id
        self.scenario = scenario
        self.reason = reason
        super().__init__(
            f"Simulation failed for decision '{decision_id}' "
            f"(scenario: {scenario}): {reason}"
        )


class ScoringError(DecisionRuntimeError):
    """Raised when deterministic feasibility scoring fails.

    Parameters
    ----------
    option_id : str
        The option ULID that could not be scored.
    reason : str
        Human-readable explanation.
    """

    def __init__(self, option_id: str, reason: str) -> None:
        self.option_id = option_id
        self.reason = reason
        super().__init__(
            f"Scoring failed for option '{option_id}': {reason}"
        )


# ── Value objects ────────────────────────────────────────────────────────


class SimulationResult:
    """Placeholder result for what-if simulation (M1).

    At M0.5 this is a stub that indicates simulation is not yet
    implemented.

    Parameters
    ----------
    decision_id : str
        The decision ULID.
    scenario : str
        Description of the what-if scenario.
    simulated_at : str
        ISO timestamp of when the simulation was (would be) run.
    outcome : str
        Simulated outcome description (stub at M0.5).
    confidence : float
        Confidence in the simulated outcome (0.0 at M0.5).
    """

    __slots__ = (
        "decision_id",
        "scenario",
        "simulated_at",
        "outcome",
        "confidence",
    )

    def __init__(
        self,
        decision_id: str,
        scenario: str,
        simulated_at: str,
        outcome: str,
        confidence: float,
    ) -> None:
        self.decision_id = decision_id
        self.scenario = scenario
        self.simulated_at = simulated_at
        self.outcome = outcome
        self.confidence = confidence

    def __repr__(self) -> str:
        return (
            f"SimulationResult(decision={self.decision_id!r}, "
            f"scenario={self.scenario!r}, conf={self.confidence:.2f})"
        )


# ── Abstract Runtime Interface ───────────────────────────────────────────


class DecisionRuntime(ABC):
    """Frozen interface for the Decision Runtime (V6.0 M0.5).

    Every implementation of this ABC must satisfy the four-stage pipeline:

    1. ``analyze``   — LLM leads reasoning on options, tradeoffs, risks.
    2. ``recommend`` — Single recommendation with confidence + readiness.
    3. ``simulate``  — What-if analysis (placeholder at M0.5).
    4. ``score``     — Deterministic feasibility scoring (8 dimensions).

    FROZEN — V6.0 M0.5 — Do not modify this interface.
    """

    @abstractmethod
    async def analyze(
        self,
        context: DecisionContext,
        *,
        tenant_id: str,
        options: list[DecisionOption] | None = None,
    ) -> DecisionAnalysis:
        """LLM-led reasoning on options, tradeoffs, and risks.

        The LLM is the **lead author** of the narrative fields:
        ``root_cause``, ``rationale``, and ``impact_summary``.  Structured
        fields (options, tradeoffs, risks) are validated strictly via
        Pydantic before being returned.

        Parameters
        ----------
        context : DecisionContext
            The assembled decision context from the Decision Context Runtime.
        tenant_id : str
            Multi-tenant isolation identifier.
        options : list[DecisionOption] | None
            Pre-generated options.  If ``None``, the runtime generates
            two default options (M0.5 behaviour).

        Returns
        -------
        DecisionAnalysis
            The full reasoning output including options, tradeoffs,
            risks, and a recommendation.

        Raises
        ------
        AnalysisError
            If the LLM call fails, the output cannot be parsed, or the
            generated analysis fails Pydantic validation.
        """
        ...

    @abstractmethod
    async def recommend(
        self,
        analysis: DecisionAnalysis,
        *,
        tenant_id: str,
    ) -> tuple[str, float, ReadinessTier]:
        """Produce a single recommendation with confidence and readiness tier.

        Selects the best option from the analysis and attaches a confidence
        score (0.0–1.0) and a readiness tier:

        * ``publish`` — Ready for immediate execution.
        * ``caveat``  — Ready with documented caveats.
        * ``review``  — Requires human review before action.
        * ``block``   — Not ready; blocking issues must be resolved.

        Parameters
        ----------
        analysis : DecisionAnalysis
            The completed analysis from ``analyze()``.
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        tuple[str, float, ReadinessTier]
            ``(recommended_option_id, confidence, readiness)``.

        Raises
        ------
        RecommendationError
            If no recommendation can be produced (e.g. no viable options).
        """
        ...

    @abstractmethod
    async def simulate(
        self,
        decision_id: str,
        scenario: str,
        *,
        tenant_id: str,
    ) -> SimulationResult:
        """Perform what-if analysis for a given scenario.

        **Placeholder for M1.** At M0.5 this returns a stub result
        indicating that simulation is not yet implemented.

        Parameters
        ----------
        decision_id : str
            The decision ULID to simulate.
        scenario : str
            Description of the what-if scenario.
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        SimulationResult
            The simulation outcome (stub at M0.5).

        Raises
        ------
        SimulationError
            If the simulation infrastructure is unavailable (should not
            happen at M0.5 since it always returns a stub).
        """
        ...

    @abstractmethod
    async def score(
        self,
        option: DecisionOption,
        *,
        tenant_id: str,
    ) -> FeasibilityResult:
        """Deterministic feasibility scoring across 8 dimensions.

        This method is **fully deterministic** — no LLM involvement.
        The 8 dimensions are:

        1. **Cost**         — Financial feasibility (budget alignment).
        2. **Time**         — Timeline feasibility (deadline alignment).
        3. **Quality**      — Expected quality improvement.
        4. **Risk**         — Risk profile (lower = more feasible).
        5. **Capacity**     — Team/resource availability.
        6. **Alignment**    — Strategic alignment score.
        7. **Complexity**   — Technical complexity (lower = more feasible).
        8. **Dependencies** — Dependency count and criticality.

        Each dimension produces a score 0.0–100.0.  The weighted total
        determines the readiness tier.

        Parameters
        ----------
        option : DecisionOption
            The option to score.
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        FeasibilityResult
            The 8-dimension feasibility score with readiness tier.

        Raises
        ------
        ScoringError
            If the scoring algorithm fails (e.g. missing required data).
        """
        ...


__all__ = [
    "DecisionRuntime",
    "DecisionRuntimeError",
    "AnalysisError",
    "RecommendationError",
    "SimulationError",
    "ScoringError",
    "SimulationResult",
]
