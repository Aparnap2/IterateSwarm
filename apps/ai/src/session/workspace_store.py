"""Async workspace CRUD using ``asyncpg``.

Workspaces are the top-level organisational unit for V6.  All entities,
decisions, and artifacts are scoped to a single workspace (and therefore
a single tenant).  This module provides the direct database access layer;
callers should use the service layer for business-logic-enriched operations.
"""

from __future__ import annotations

import logging
from typing import Any

from src.entities.models import Workspace

logger = logging.getLogger(__name__)


# ── CRUD ────────────────────────────────────────────────────────────────


async def create_workspace(
    conn: Any,
    workspace: Workspace,
) -> Workspace:
    """Insert a new workspace row.

    Parameters
    ----------
    conn:
        An ``asyncpg.Connection`` (or compatible duck-typed pool connection).
    workspace:
        The workspace model to persist.  ``id`` and ``tenant_id`` must be set.

    Returns
    -------
    Workspace
        The created workspace (with server-generated defaults populated).
    """
    raise NotImplementedError(
        "Implement with: INSERT INTO workspaces (id, tenant_id, name, purpose, status) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING *"
    )


async def get_workspace(
    conn: Any,
    workspace_id: str,
) -> Workspace | None:
    """Fetch a workspace by its ULID.

    Parameters
    ----------
    conn:
        An ``asyncpg.Connection``.
    workspace_id:
        The ULID of the workspace.

    Returns
    -------
    Workspace | None
        The workspace if found, else ``None``.
    """
    raise NotImplementedError("Implement with: SELECT * FROM workspaces WHERE id = $1")


async def update_workspace_status(
    conn: Any,
    workspace_id: str,
    status: str,
) -> None:
    """Update the status of a workspace.

    Parameters
    ----------
    conn:
        An ``asyncpg.Connection``.
    workspace_id:
        The ULID of the workspace.
    status:
        New status value (``"active"``, ``"archived"``, or ``"closed"``).
    """
    raise NotImplementedError(
        "Implement with: UPDATE workspaces SET status = $2, updated_at = NOW() WHERE id = $1"
    )


async def list_workspaces(
    conn: Any,
    tenant_id: str,
) -> list[Workspace]:
    """List all workspaces for a given tenant.

    Parameters
    ----------
    conn:
        An ``asyncpg.Connection``.
    tenant_id:
        The ULID of the tenant.

    Returns
    -------
    list[Workspace]
        All workspaces belonging to the tenant.
    """
    raise NotImplementedError(
        "Implement with: SELECT * FROM workspaces WHERE tenant_id = $1 ORDER BY name"
    )


# ── Entity membership ───────────────────────────────────────────────────


async def add_entity_to_workspace(
    conn: Any,
    workspace_id: str,
    entity_id: str,
) -> None:
    """Link an entity to a workspace via the ``workspace_entities`` join table.

    This creates a ``CONTAINS`` relationship in the relational store.
    The Neo4j graph is updated separately by the pipeline.

    Parameters
    ----------
    conn:
        An ``asyncpg.Connection``.
    workspace_id:
        The ULID of the workspace.
    entity_id:
        The ULID of the entity to add.
    """
    raise NotImplementedError(
        "Implement with: INSERT INTO workspace_entities (workspace_id, entity_id) VALUES ($1, $2) "
        "ON CONFLICT DO NOTHING"
    )


async def remove_entity_from_workspace(
    conn: Any,
    workspace_id: str,
    entity_id: str,
) -> None:
    """Remove an entity link from a workspace.

    This does **not** delete the entity itself — only the workspace
    membership relationship.

    Parameters
    ----------
    conn:
        An ``asyncpg.Connection``.
    workspace_id:
        The ULID of the workspace.
    entity_id:
        The ULID of the entity to remove.
    """
    raise NotImplementedError(
        "Implement with: DELETE FROM workspace_entities WHERE workspace_id = $1 AND entity_id = $2"
    )


async def get_workspace_entities(
    conn: Any,
    workspace_id: str,
) -> list[str]:
    """Return the list of entity ULIDs linked to a workspace.

    Parameters
    ----------
    conn:
        An ``asyncpg.Connection``.
    workspace_id:
        The ULID of the workspace.

    Returns
    -------
    list[str]
        Entity ULIDs linked to this workspace.
    """
    raise NotImplementedError(
        "Implement with: SELECT entity_id FROM workspace_entities WHERE workspace_id = $1"
    )
