"""
Connector Registry — capability-based connector lookup.

Provides a global registry mapping capability strings (``"crm"``, ``"erp"``,
``"accounting"``, ``"messaging"``) to concrete :class:`Connector` classes so
that callers can resolve connectors at runtime without import-time coupling.

Usage::

    from src.connectors import get_connector, ConnectorConfig, list_available_capabilities

    cfg = ConnectorConfig(tenant_id="startup_abc", mock_mode=True)
    crm = get_connector("crm", cfg)
    customers = crm.get_customers()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import Connector, ConnectorConfig

if TYPE_CHECKING:
    from collections.abc import ValuesView

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_connector_registry: dict[str, type[Connector]] = {}


def register_connector(capability: str, connector_cls: type[Connector]) -> None:
    """Register *connector_cls* for the given *capability* string.

    If the capability already has a registered connector, the new one
    *replaces* it — this allows override precedence (e.g. the most
    recently imported connector for a given capability wins).
    """
    existing = _connector_registry.get(capability)
    if existing is connector_cls:
        return
    if existing is not None:
        logger.info(
            "Replacing connector for capability %r: %s -> %s",
            capability,
            existing.__name__,
            connector_cls.__name__,
        )
    _connector_registry[capability] = connector_cls
    logger.debug("Registered connector %s for capability %r", connector_cls.__name__, capability)


def get_connector(capability: str, config: ConnectorConfig) -> Connector:
    """Look up a connector by *capability* and instantiate it with *config*.

    Raises
    ------
    KeyError
        If *capability* has not been registered.
    """
    try:
        cls = _connector_registry[capability]
    except KeyError:
        raise KeyError(
            f"No connector registered for capability {capability!r}. "
            f"Available: {list(_connector_registry)}"
        ) from None
    return cls(config)


def list_available_capabilities() -> list[str]:
    """Return sorted list of registered capability strings."""
    return sorted(_connector_registry)


# ---------------------------------------------------------------------------
# Auto-register known connectors at import time
# ---------------------------------------------------------------------------

# Lazy-import to avoid circular dependencies — the registry is populated at
# module level after all classes are defined.
def _auto_register() -> None:
    from .erpnext_connector import ERPNextConnector
    from .quickbooks_connector import QuickBooksConnector
    from .stripe_connector import StripeConnector
    from .mock.mock_crm import MockCRMConnector
    from .mock.mock_erp import MockERPConnector

    # Production-grade connectors (preferred when credentials exist)
    register_connector("erp", ERPNextConnector)
    register_connector("accounting", QuickBooksConnector)
    register_connector("accounting", StripeConnector)  # duplicate: last wins for same capability

    # Mock connectors — registered under capability + "_mock" so they can be
    # explicitly requested, but also serve as fallback in *mock_mode*.
    register_connector("crm_mock", MockCRMConnector)
    register_connector("erp_mock", MockERPConnector)


_auto_register()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "Connector",
    "ConnectorConfig",
    "get_connector",
    "list_available_capabilities",
    "register_connector",
]
