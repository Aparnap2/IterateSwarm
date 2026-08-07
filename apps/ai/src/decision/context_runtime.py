# FROZEN — V6.0 M0.5
"""OntologyAI V6 — Decision Context Runtime Interface (ABC).

The Decision Context Runtime sits between the Knowledge Model and the
Decision Agent.  It assembles the **minimal, high-signal context** that
the LLM is allowed to consume — never the whole graph.

This module defines the **frozen contract** that all Decision Context
Runtime implementations must satisfy.  It contains **no execution logic** —
only the abstract interface, type contracts, and error hierarchy.

Pipeline stages
---------------
1. **retrieve** — Fetch relevant evidence + entities for a decision.
2. **rerank**   — Priority ordering by freshness, confidence, relevance.
3. **compress** — Token budget enforcement (truncate in priority order).
4. **assemble** — Build the minimal ``DecisionContext`` for the LLM.

Design constraints
------------------
* The LLM never sees the whole knowledge graph — only the assembled
  ``DecisionContext`` bounded by a token budget.
* Retrieval is **deterministic** — the vector store is pgvector (primary),
  kept behind a ``VectorStore`` abstraction.
* Compression drops low-priority evidence first, then low-confidence
  entities, then stale KPIs/policies.
* All methods are ``async`` to support non-blocking database and vector
  store access.

FROZEN — V6.0 M0.5
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.decision.contracts import DecisionContext, EvidenceRef, EntityRef


# ── Error hierarchy ──────────────────────────────────────────────────────


class ContextRuntimeError(Exception):
    """Base exception for all Decision Context Runtime failures."""


class RetrievalError(ContextRuntimeError):
    """Raised when evidence or entity retrieval fails.

    Parameters
    ----------
    decision_id : str
        The decision ULID for which retrieval was attempted.
    reason : str
        Human-readable explanation of the failure.
    """

    def __init__(self, decision_id: str, reason: str) -> None:
        self.decision_id = decision_id
        self.reason = reason
        super().__init__(
            f"Retrieval failed for decision '{decision_id}': {reason}"
        )


class RerankingError(ContextRuntimeError):
    """Raised when reranking of evidence/entities fails.

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
            f"Reranking failed for decision '{decision_id}': {reason}"
        )


class CompressionError(ContextRuntimeError):
    """Raised when token budget enforcement fails.

    Parameters
    ----------
    decision_id : str
        The decision ULID.
    budget_max : int
        The configured maximum token budget.
    budget_actual : int
        The actual token count after compression (should not exceed budget).
    """

    def __init__(self, decision_id: str, budget_max: int, budget_actual: int) -> None:
        self.decision_id = decision_id
        self.budget_max = budget_max
        self.budget_actual = budget_actual
        super().__init__(
            f"Compression failed for decision '{decision_id}': "
            f"budget {budget_max} exceeded ({budget_actual} actual)"
        )


class AssemblyError(ContextRuntimeError):
    """Raised when the ``DecisionContext`` cannot be assembled.

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
            f"Assembly failed for decision '{decision_id}': {reason}"
        )


# ── Abstract Runtime Interface ───────────────────────────────────────────


class ContextRuntime(ABC):
    """Frozen interface for the Decision Context Runtime (V6.0 M0.5).

    Every implementation of this ABC must satisfy the four-stage pipeline:

    1. ``retrieve`` — Fetch evidence + entities relevant to a decision.
    2. ``rerank``   — Priority order by freshness, confidence, relevance.
    3. ``compress`` — Enforce token budget; truncate low-priority items first.
    4. ``assemble`` — Build the minimal ``DecisionContext`` for the LLM.

    The output of ``assemble()`` is the **only** context the Decision
    Agent's LLM is allowed to consume.

    FROZEN — V6.0 M0.5 — Do not modify this interface.
    """

    @abstractmethod
    async def retrieve(
        self,
        decision_id: str,
        *,
        tenant_id: str,
        workspace_id: str,
        evidence_limit: int = 20,
        entity_limit: int = 50,
    ) -> tuple[list[EvidenceRef], list[EntityRef]]:
        """Fetch evidence and entities relevant to *decision_id*.

        Retrieves from both the relational store (evidence links) and the
        vector store (semantic similarity).  Results are unranked — use
        ``rerank()`` to order by priority.

        Parameters
        ----------
        decision_id : str
            The decision ULID to gather context for.
        tenant_id : str
            Multi-tenant isolation identifier.
        workspace_id : str
            Workspace scope for the decision.
        evidence_limit : int
            Maximum number of ``EvidenceRef`` to retrieve.
        entity_limit : int
            Maximum number of ``EntityRef`` to retrieve.

        Returns
        -------
        tuple[list[EvidenceRef], list[EntityRef]]
            ``(evidence_refs, entity_refs)`` — raw retrieval results.

        Raises
        ------
        RetrievalError
            If the retrieval query fails or times out.
        """
        ...

    @abstractmethod
    async def rerank(
        self,
        evidence_refs: list[EvidenceRef],
        entity_refs: list[EntityRef],
        *,
        decision_id: str,
    ) -> tuple[list[EvidenceRef], list[EntityRef]]:
        """Priority-order evidence and entities for the decision.

        Ranking factors (in priority order):

        1. **Freshness** — More recent evidence ranks higher.
        2. **Confidence** — Higher confidence evidence ranks higher.
        3. **Relevance** — Semantic similarity to the decision question.

        Parameters
        ----------
        evidence_refs : list[EvidenceRef]
            Raw evidence references from ``retrieve()``.
        entity_refs : list[EntityRef]
            Raw entity references from ``retrieve()``.
        decision_id : str
            The decision ULID (used for relevance scoring).

        Returns
        -------
        tuple[list[EvidenceRef], list[EntityRef]]
            ``(evidence_refs, entity_refs)`` — re-ranked, most relevant first.

        Raises
        ------
        RerankingError
            If the reranking algorithm fails.
        """
        ...

    @abstractmethod
    async def compress(
        self,
        evidence_refs: list[EvidenceRef],
        entity_refs: list[EvidenceRef],
        *,
        decision_id: str,
        token_budget: int = 32000,
    ) -> tuple[list[EvidenceRef], list[EntityRef]]:
        """Enforce a token budget by truncating low-priority items first.

        Truncation order (last items dropped first):

        1. Low-confidence evidence (< 0.3).
        2. Stale evidence (older than 90 days).
        3. Low-confidence entities.
        4. Stale KPIs and policies.
        5. Any remaining items beyond budget.

        Parameters
        ----------
        evidence_refs : list[EvidenceRef]
            Re-ranked evidence references.
        entity_refs : list[EvidenceRef]
            Re-ranked entity references.
        decision_id : str
            The decision ULID.
        token_budget : int
            Maximum tokens the assembled context may consume.

        Returns
        -------
        tuple[list[EvidenceRef], list[EntityRef]]
            ``(evidence_refs, entity_refs)`` — compressed to fit the budget.

        Raises
        ------
        CompressionError
            If the compressed context still exceeds the budget (should not
            happen with correct truncation logic).
        """
        ...

    @abstractmethod
    async def assemble(
        self,
        decision_id: str,
        *,
        tenant_id: str,
        workspace_id: str,
        question: str = "",
        token_budget: int = 32000,
    ) -> DecisionContext:
        """Build the minimal ``DecisionContext`` for the Decision Agent.

        This is the **main entry point** that orchestrates the full pipeline:

        1. ``retrieve`` → raw evidence + entities.
        2. ``rerank``   → priority-ordered evidence + entities.
        3. ``compress`` → token-budget-enforced evidence + entities.
        4. ``assemble`` → build and return the ``DecisionContext``.

        Parameters
        ----------
        decision_id : str
            The decision ULID.
        tenant_id : str
            Multi-tenant isolation identifier.
        workspace_id : str
            Workspace scope.
        question : str
            The decision question (optional, may be included in context).
        token_budget : int
            Maximum tokens for the assembled context.

        Returns
        -------
        DecisionContext
            The minimal, high-signal context for the Decision Agent.

        Raises
        ------
        RetrievalError | RerankingError | CompressionError | AssemblyError
            If any pipeline stage fails.
        """
        ...


__all__ = [
    "ContextRuntime",
    "ContextRuntimeError",
    "RetrievalError",
    "RerankingError",
    "CompressionError",
    "AssemblyError",
]
