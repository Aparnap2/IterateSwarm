"""
Base Connector ABC — capability-based abstraction for all data connectors.

Every connector in this package inherits from :class:`Connector` and receives
a :class:`ConnectorConfig` with tenant identity, credentials, and mock-mode
flag.  Subclasses must implement ``name``, ``capability``, and ``health``.

Design principles
-----------------
* **Graceful degradation** — connector methods return partial data + error
  metadata dicts on failure; they never raise unhandled exceptions.
* **Mock support** — activated by ``config.mock_mode``; returns realistic
  seed data without network calls.
* **Evidence-ready** — all data dicts carry ``source`` and ``fetched_at``
  metadata so an Evidence layer can wrap them transparently.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, ClassVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connector Configuration
# ---------------------------------------------------------------------------


class ConnectorConfig(BaseModel):
    """Pydantic model for connector configuration.

    Every connector receives one of these in ``__init__``.  Credentials are
    passed as a flat dict so the same model works for all providers.
    """

    tenant_id: str
    credentials: dict[str, str] = {}
    mock_mode: bool = False


# ---------------------------------------------------------------------------
# Base Connector ABC
# ---------------------------------------------------------------------------


class Connector(ABC):
    """Abstract base class for all capability-based connectors.

    Subclasses are registered in the :mod:`connectors` registry under a
    capability string (``"crm"``, ``"erp"``, ``"accounting"``, etc.) and
    looked up at runtime by ``get_connector(capability, config)``.

    Parameters
    ----------
    config: :class:`ConnectorConfig`
        Tenant configuration including credentials and mock-mode flag.
    """

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config

    # ── Abstract interface ────────────────────────────────────────────

    @abstractmethod
    def name(self) -> str:
        """Human-readable connector name (e.g. ``"erpnext"``, ``"salesforce"``)."""
        ...

    @abstractmethod
    def capability(self) -> str:
        """Capability string (e.g. ``"crm"``, ``"erp"``, ``"accounting"``, ``"messaging"``)."""
        ...

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return current connector health.

        Returns a dict with at minimum:

        .. code-block:: python

            {"status": "ok" | "degraded" | "down", "latency_ms": <int>}
        """
        ...

    # ── Shared helpers ────────────────────────────────────────────────

    @staticmethod
    def _add_metadata(data: dict[str, Any], source: str) -> dict[str, Any]:
        """Attach source and timestamp metadata to a response dict.

        All public connector methods should run their return value through
        this helper so callers always have provenance information.
        """
        result = data.copy()
        result["source"] = source
        result["fetched_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return result

    @staticmethod
    def _error_result(
        source: str,
        partial_data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Build a graceful-degradation result dict.

        Returns *partial_data* enriched with ``source``, ``fetched_at``, and
        an optional ``error`` key.  Callers can check ``"error" in result``
        to detect partial failures.
        """
        data = dict(partial_data) if partial_data else {}
        data["source"] = source
        data["fetched_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if error:
            data["error"] = error
        return data
