"""Decision Engine — creates decisions and generates options.

For the V6 vertical slice, this engine:

1. Creates a ``Decision`` entity for "Improve Onboarding Process".
2. Generates two mutually exclusive options:
   - Option A: "Automate onboarding workflow" (high-tech)
   - Option B: "Streamline manual process" (low-tech)
3. Returns the decision and both options.

When no database is available, entities are returned as plain dicts
and tracked in-memory.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.entities.models import Decision, Option

logger = logging.getLogger(__name__)

# ── Fixed ULIDs for reproducibility ──────────────────────────────────────

DECISION_ID = "01J0X8X8X8X8X8X8X8X8X8X8X8DE"
OPTION_A_ID = "01J0X8X8X8X8X8X8X8X8X8X8X8OA"
OPTION_B_ID = "01J0X8X8X8X8X8X8X8X8X8X8X8OB"

# ── Result model ─────────────────────────────────────────────────────────


class DecisionEngineResult(BaseModel):
    """Result produced by the Decision Engine.

    Attributes
    ----------
    decision:
        The created Decision entity (as a dict for serialisation).
    options:
        The generated Option entities (as dicts).
    summary:
        Human-readable summary of what was decided.
    """

    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    decision: dict[str, Any]
    options: list[dict[str, Any]]
    summary: str = ""


class DecisionEngine:
    """Creates decisions and generates options from evidence context.

    Parameters
    ----------
    db_pool:
        An ``asyncpg.Pool`` (or compatible). May be ``None``.
    """

    def __init__(self, db_pool) -> None:
        self._pool = db_pool

    async def create_decision(
        self,
        title: str,
        workspace_id: str,
        tenant_id: str,
        owner_id: str = "",
        description: str = "",
    ) -> Decision:
        """Create a new Decision entity.

        Parameters
        ----------
        title:
            Decision title (max 200 chars).
        workspace_id:
            ULID of the owning workspace.
        tenant_id:
            ULID of the owning tenant.
        owner_id:
            ULID of the stakeholder who owns the decision.
        description:
            Longer description (max 5000 chars).

        Returns
        -------
        Decision
            The created decision model instance.
        """
        decision = Decision(
            id=DECISION_ID,
            tenant_id=tenant_id,
            title=title,
            description=description,
            workspace_id=workspace_id,
            owner_id=owner_id,
            status="assessing",
            created_at=datetime.now(timezone.utc),
        )
        logger.info("Created decision %s: %s", decision.id, decision.title)
        return decision

    async def generate_options(
        self,
        decision: Decision,
    ) -> list[Option]:
        """Generate two candidate options for a decision.

        Parameters
        ----------
        decision:
            The decision these options are generated for.

        Returns
        -------
        list[Option]
            Two Option entities: automation vs. process-improvement.
        """
        option_a = Option(
            id=OPTION_A_ID,
            tenant_id=decision.tenant_id,
            decision_id=decision.id,
            title="Automate onboarding workflow",
            description=(
                "Implement automated approval routing via Slack workflows "
                "and Okta SCIM provisioning. Target: reduce onboarding from "
                "21 days to 5 days. Requires integration with People Ops "
                "tools and ~6 weeks of engineering effort."
            ),
            status="proposed",
        )

        option_b = Option(
            id=OPTION_B_ID,
            tenant_id=decision.tenant_id,
            decision_id=decision.id,
            title="Streamline manual process",
            description=(
                "Reduce manual bottlenecks without automation: set SLA on "
                "manager approvals (4hr response), create shared onboarding "
                "checklist, assign dedicated onboarding buddy. Target: reduce "
                "onboarding from 21 days to 12 days. Minimal engineering "
                "effort, mainly process change."
            ),
            status="proposed",
        )

        logger.info(
            "Generated %d options for decision %s",
            2,
            decision.id,
        )
        return [option_a, option_b]

    async def run(
        self,
        workspace_id: str,
        tenant_id: str,
    ) -> DecisionEngineResult:
        """Full decision analysis run.

        Convenience method that calls ``create_decision`` and
        ``generate_options`` in sequence.

        Parameters
        ----------
        workspace_id:
            ULID of the owning workspace.
        tenant_id:
            ULID of the owning tenant.

        Returns
        -------
        DecisionEngineResult
            The decision, options, and a summary narrative.
        """
        decision = await self.create_decision(
            title="Improve onboarding process",
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            owner_id="",
            description=(
                "Evidence from customer interviews and KPI data shows "
                "that the current onboarding process has a 40% user "
                "drop-off rate and takes 21 days. This decision evaluates "
                "options to improve the onboarding experience."
            ),
        )

        options = await self.generate_options(decision)

        return DecisionEngineResult(
            decision=decision.model_dump(),
            options=[o.model_dump() for o in options],
            summary=(
                f"Decision '{decision.title}' created with {len(options)} "
                f"options: {[o.title for o in options]}"
            ),
        )
