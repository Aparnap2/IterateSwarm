# FROZEN — V6.0 M0.5
"""OntologyAI V6 — Evidence Runtime Interface (ABC).

The Evidence Runtime is the **Layer 4** execution domain responsible for
ingesting raw signals from external connectors, normalising them into a
canonical ``EvidenceRecord``, validating them against deterministic rules,
and persisting them to storage.

This module defines the **frozen contract** that all Evidence Runtime
implementations must satisfy.  It contains **no execution logic** — only
the abstract interface, type contracts, and error hierarchy.

Pipeline stages
---------------
1. **observe** — Accept raw, connector-specific payloads.
2. **normalize** — Transform connector data → ``EvidenceRecord``.
3. **validate** — Deterministic schema + business-rule checks (BEFORE any LLM).
4. **persist** — Write to Postgres + vector store.

Design constraints
------------------
* Validation is always **deterministic** — no LLM calls before persist.
* Normalisation is dispatched per-source via a normalizer registry.
* Persistence writes to both the relational store and the vector index
  in a single transaction (best-effort fallback to relational-only).

FROZEN — V6.0 M0.5
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.evidence.models import EvidenceRecord


# ── Error hierarchy ──────────────────────────────────────────────────────


class EvidenceRuntimeError(Exception):
    """Base exception for all Evidence Runtime failures."""


class ObservationError(EvidenceRuntimeError):
    """Raised when raw evidence cannot be accepted from a connector.

    Parameters
    ----------
    connector : str
        The connector that produced the invalid payload.
    reason : str
        Human-readable explanation of the failure.
    """

    def __init__(self, connector: str, reason: str) -> None:
        self.connector = connector
        self.reason = reason
        super().__init__(f"Observation failed for connector '{connector}': {reason}")


class NormalizationError(EvidenceRuntimeError):
    """Raised when connector-specific data cannot be normalised.

    Parameters
    ----------
    source : str
        The source identifier (e.g. ``"stripe"``, ``"erpnext"``).
    reason : str
        Human-readable explanation of the failure.
    """

    def __init__(self, source: str, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"Normalisation failed for source '{source}': {reason}")


class ValidationError(EvidenceRuntimeError):
    """Raised when an ``EvidenceRecord`` fails deterministic validation.

    Parameters
    ----------
    evidence_id : str
        The ``evidence_id`` of the record that failed validation.
    violations : list[str]
        List of rule names or descriptions that were violated.
    """

    def __init__(self, evidence_id: str, violations: list[str]) -> None:
        self.evidence_id = evidence_id
        self.violations = violations
        detail = "; ".join(violations) if violations else "(no detail)"
        super().__init__(f"Evidence '{evidence_id}' failed validation: {detail}")


class PersistenceError(EvidenceRuntimeError):
    """Raised when an ``EvidenceRecord`` cannot be persisted to storage.

    Parameters
    ----------
    evidence_id : str
        The ``evidence_id`` of the record that could not be stored.
    reason : str
        Human-readable explanation of the failure.
    """

    def __init__(self, evidence_id: str, reason: str) -> None:
        self.evidence_id = evidence_id
        self.reason = reason
        super().__init__(f"Persistence failed for evidence '{evidence_id}': {reason}")


# ── Abstract Runtime Interface ───────────────────────────────────────────


class EvidenceRuntime(ABC):
    """Frozen interface for the Evidence Runtime (V6.0 M0.5).

    Every implementation of this ABC must satisfy the four-stage pipeline:

    1. ``observe``  — Accept raw payloads from connectors.
    2. ``normalize`` — Transform to ``EvidenceRecord``.
    3. ``validate``  — Deterministic schema + business-rule checks.
    4. ``persist``   — Write to Postgres + vector store.

    Implementations must be stateless or explicitly document any mutable
    state they hold (e.g. connection pools, caches).

    FROZEN — V6.0 M0.5 — Do not modify this interface.
    """

    @abstractmethod
    async def observe(
        self,
        connector: str,
        raw_payload: dict[str, Any],
        *,
        tenant_id: str,
        workspace_id: str = "",
    ) -> dict[str, Any]:
        """Accept a raw payload from *connector* and return a normalisable form.

        This is the entry point for all incoming evidence.  The method should
        perform minimal pre-processing (e.g. extracting relevant fields,
        adding metadata) and return a dict that ``normalize()`` can consume.

        Parameters
        ----------
        connector : str
            Canonical connector name (e.g. ``"stripe"``, ``"erpnext"``).
        raw_payload : dict[str, Any]
            The raw, unnormalised payload from the connector.  Its shape is
            connector-specific and may be an API response, webhook body, or
            file upload.
        tenant_id : str
            Multi-tenant isolation identifier.
        workspace_id : str, optional
            Workspace scope (may be empty for system-level ingestion).

        Returns
        -------
        dict[str, Any]
            A pre-processed payload suitable for ``normalize()``.

        Raises
        ------
        ObservationError
            If the payload cannot be accepted (e.g. missing required fields).
        """
        ...

    @abstractmethod
    async def normalize(
        self,
        connector: str,
        preprocessed: dict[str, Any],
        *,
        tenant_id: str,
    ) -> EvidenceRecord:
        """Transform a connector-specific payload into a canonical ``EvidenceRecord``.

        Dispatches to the registered ``EvidenceNormalizer`` for *connector*.
        If no specialized normalizer exists, a generic wrapper is used.

        Parameters
        ----------
        connector : str
            Canonical connector name.
        preprocessed : dict[str, Any]
            Output of ``observe()``.
        tenant_id : str
            Multi-tenant isolation identifier.

        Returns
        -------
        EvidenceRecord
            A fully-populated, schema-valid evidence record.

        Raises
        ------
        NormalizationError
            If the payload cannot be transformed to an ``EvidenceRecord``.
        """
        ...

    @abstractmethod
    async def validate(
        self,
        record: EvidenceRecord,
    ) -> EvidenceRecord:
        """Run deterministic validation on an ``EvidenceRecord``.

        Validation is performed **before** any LLM involvement and includes:

        * Pydantic schema validation (type correctness, field constraints).
        * Business rules: ``confidence`` in [0, 1], ``evidence_id`` non-empty,
          ``source`` in allowed set, ``timestamp`` not in the future, etc.
        * Source-specific rules dispatched to the normalizer's ``validate`` hook.

        Parameters
        ----------
        record : EvidenceRecord
            The normalised evidence record to validate.

        Returns
        -------
        EvidenceRecord
            The same record, confirmed valid.  Implementations may enrich
            the record (e.g. set ``extracted_at``) but must not alter
            semantically meaningful fields.

        Raises
        ------
        ValidationError
            If any deterministic check fails.  ``violations`` contains the
            list of failed rules.
        """
        ...

    @abstractmethod
    async def persist(
        self,
        record: EvidenceRecord,
    ) -> EvidenceRecord:
        """Persist a validated ``EvidenceRecord`` to storage.

        Writes to both the relational store (Postgres) and the vector index
        in a single logical transaction.  If the vector store is unavailable,
        the record is persisted to Postgres only (best-effort fallback).

        The ``evidence_id`` is used as the deduplication key — persisting
        the same ``evidence_id`` twice is a no-op (idempotent).

        Parameters
        ----------
        record : EvidenceRecord
            The validated evidence record to persist.

        Returns
        -------
        EvidenceRecord
            The persisted record, enriched with any storage-generated metadata
            (e.g. ``provenance["persisted_at"]``).

        Raises
        ------
        PersistenceError
            If the record cannot be written to any store.
        """
        ...


__all__ = [
    "EvidenceRuntime",
    "EvidenceRuntimeError",
    "ObservationError",
    "NormalizationError",
    "ValidationError",
    "PersistenceError",
]
