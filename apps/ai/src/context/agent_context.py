"""Agent context assembly for OntologyAI V6.

Per §10 of the V6 spec, context is assembled in strict 8-layer order and
bounded by a 32 000 token budget.  Deterministic pipeline stages receive
no LLM context — only LLM-augmented stages (Parse, Entity Build, Decision
Analysis, Artifact Projection) get the full assembled ``AgentContext``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.entities.models import EvidenceRecord
from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


# ── AgentContext ────────────────────────────────────────────────────────


class AgentContext(BaseModel):
    """Assembled context window for LLM-augmented pipeline stages.

    Composed of 8 ordered layers.  The total token budget is 32 000 tokens.
    If the assembled context exceeds this budget, layers are truncated in
    priority order: evidence_slice → knowledge_slice → decision_slice
    (cut from the bottom).
    """

    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    # Layer 1: Tenant
    tenant: dict = Field(default_factory=dict)

    # Layer 2: Workspace
    workspace: dict | None = None

    # Layer 3: Stakeholder
    stakeholder: dict | None = None

    # Layer 4: Evidence Slice — max 20 records or 8K tokens
    evidence_slice: list[EvidenceRecord] = Field(default_factory=list, max_length=20)

    # Layer 5: Knowledge Slice — Neo4j nodes + edges, max 3 hops
    knowledge_slice: list[dict] = Field(default_factory=list)

    # Layer 6: Decision Slice — active + recent decisions
    decision_slice: list[dict] = Field(default_factory=list)

    # Layer 7: Artifact Slice — titles + statuses only
    artifact_slice: list[dict] = Field(default_factory=list)

    # Layer 8: Policy Slice — applicable business rules
    policy_slice: list[dict] = Field(default_factory=list)

    # Budget tracking
    total_tokens: int = 0  # max 32 000


# ── ContextAssembler ────────────────────────────────────────────────────


class ContextAssembler:
    """Assembles an ``AgentContext`` for a given workspace.

    Parameters
    ----------
    neo4j:
        Initialised async Neo4j client for graph traversal.
    db_pool:
        An asyncpg connection pool (or compatible) for relational queries.
    """

    def __init__(
        self,
        neo4j: Neo4jClient,
        db_pool: Any,  # asyncpg.Pool (avoid hard runtime dep)
    ) -> None:
        self._neo4j = neo4j
        self._db_pool = db_pool

    async def assemble(
        self,
        workspace_id: str,
        stakeholder_id: str | None = None,
    ) -> AgentContext:
        """Assemble the full 8-layer context for *workspace_id*.

        Layers are fetched in order: tenant → workspace → stakeholder →
        evidence → knowledge → decisions → artifacts → policies.

        Parameters
        ----------
        workspace_id:
            ULID of the target workspace.
        stakeholder_id:
            Optional ULID of the requesting stakeholder (for Layer 3).

        Returns
        -------
        AgentContext
            Fully assembled context, respecting the 32K token budget.

        Raises
        ------
        ValueError
            If *workspace_id* does not resolve to an existing workspace.
        """
        ctx = AgentContext()

        # Layer 1: Tenant context
        ctx.tenant = await self._load_tenant(workspace_id)

        # Layer 2: Workspace context
        workspace = await self._load_workspace(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace {workspace_id} not found")
        ctx.workspace = workspace

        # Layer 3: Stakeholder context (optional)
        if stakeholder_id is not None:
            ctx.stakeholder = await self._load_stakeholder(stakeholder_id)

        # Layer 4: Evidence slice — top 20 by confidence
        ctx.evidence_slice = await self._load_evidence_slice(workspace_id)

        # Layer 5: Knowledge slice — graph traversal from workspace entities
        ctx.knowledge_slice = await self._load_knowledge_slice(workspace_id)

        # Layer 6: Decision slice — active + recent
        ctx.decision_slice = await self._load_decision_slice(workspace_id)

        # Layer 7: Artifact slice — titles + statuses only
        ctx.artifact_slice = await self._load_artifact_slice(workspace_id)

        # Layer 8: Policy slice — applicable business rules
        ctx.policy_slice = await self._load_policy_slice(workspace_id)

        # Track token budget (approximate)
        ctx.total_tokens = self._estimate_tokens(ctx)

        return ctx

    # ── Layer loaders (each raises NotImplementedError) ─────────────────

    async def _load_tenant(self, workspace_id: str) -> dict:
        """Load tenant context from the workspace's tenant."""
        ...

    async def _load_workspace(self, workspace_id: str) -> dict | None:
        """Load workspace metadata from PostgreSQL."""
        ...

    async def _load_stakeholder(self, stakeholder_id: str) -> dict | None:
        """Load stakeholder profile from Neo4j."""
        ...

    async def _load_evidence_slice(self, workspace_id: str) -> list[EvidenceRecord]:
        """Load top-20 evidence records for this workspace."""
        ...

    async def _load_knowledge_slice(self, workspace_id: str) -> list[dict]:
        """Traverse the Neo4j graph from workspace entities, max 3 hops."""
        ...

    async def _load_decision_slice(self, workspace_id: str) -> list[dict]:
        """Load active + recent decisions for this workspace."""
        ...

    async def _load_artifact_slice(self, workspace_id: str) -> list[dict]:
        """Load artifact titles and statuses (no content)."""
        ...

    async def _load_policy_slice(self, workspace_id: str) -> list[dict]:
        """Load applicable business rules for this workspace."""
        ...

    # ── Budget helper ───────────────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(ctx: AgentContext) -> int:
        """Rough token count estimate (4 chars ≈ 1 token).

        This is a placeholder — production should use an actual tokenizer
        (``tiktoken``) for accurate budget enforcement.
        """
        total_chars = 0

        total_chars += len(str(ctx.tenant))
        total_chars += len(str(ctx.workspace or {}))
        total_chars += len(str(ctx.stakeholder or {}))
        total_chars += sum(len(str(r.model_dump())) for r in ctx.evidence_slice)
        total_chars += sum(len(str(d)) for d in ctx.knowledge_slice)
        total_chars += sum(len(str(d)) for d in ctx.decision_slice)
        total_chars += sum(len(str(d)) for d in ctx.artifact_slice)
        total_chars += sum(len(str(d)) for d in ctx.policy_slice)

        return total_chars // 4  # rough: 4 chars ~ 1 token
