"""V6 Connector Registry — maps source names to V6 connector classes.

Provides a registry that maps connector source names (e.g. ``"notion"``,
``"slack"``) to their corresponding :class:`BaseV6Connector` subclasses so
the pipeline can resolve and run connectors at runtime without import-time
coupling.

Usage::

    from src.connectors.registry import V6ConnectorRegistry

    # Get a connector class
    cls = V6ConnectorRegistry.get("notion")

    # Run all registered connectors
    results = await V6ConnectorRegistry.run_all(tenant_id="my-tenant")
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.connectors.base import ConnectorConfig
from src.connectors.v6_base import BaseV6Connector
from src.entities.models import EvidenceRecord

logger = logging.getLogger(__name__)


class V6ConnectorRegistry:
    """Maps connector source names to connector classes.

    Connectors are registered at import time via :meth:`register` and can
    be looked up by source name for direct use or run collectively via
    :meth:`run_all`.
    """

    _connectors: dict[str, type[BaseV6Connector]] = {}

    @classmethod
    def register(cls, source: str, connector_cls: type[BaseV6Connector]) -> None:
        """Register *connector_cls* under *source* name.

        If the source already has a registered connector, the new one
        replaces it (last-registered wins).
        """
        existing = cls._connectors.get(source)
        if existing is connector_cls:
            return
        if existing is not None:
            logger.info(
                "Replacing connector for source %r: %s -> %s",
                source,
                existing.__name__,
                connector_cls.__name__,
            )
        cls._connectors[source] = connector_cls
        logger.debug(
            "Registered connector %s for source %r",
            connector_cls.__name__,
            source,
        )

    @classmethod
    def get(cls, source: str) -> type[BaseV6Connector]:
        """Get connector class by source name.

        Raises
        ------
        KeyError
            If *source* has not been registered.
        """
        try:
            return cls._connectors[source]
        except KeyError:
            raise KeyError(
                f"No V6 connector registered for source {source!r}. "
                f"Available: {cls.list_sources()}"
            ) from None

    @classmethod
    def list_sources(cls) -> list[str]:
        """Return all registered source names, sorted."""
        return sorted(cls._connectors)

    @classmethod
    async def run_all(
        cls,
        tenant_id: str,
        since: datetime | None = None,
        sources: list[str] | None = None,
    ) -> dict[str, list[EvidenceRecord]]:
        """Run all (or specified) registered connectors and return results.

        For each source, a default :class:`ConnectorConfig` is created with
        the given *tenant_id* and empty credentials — each connector's own
        ``__init__`` provides sensible defaults (e.g. ``localhost:3001-3004``
        for Mockoon).

        Parameters
        ----------
        tenant_id:
            Tenant identifier passed to each connector's config.
        since:
            Optional timestamp to filter records (passed to ``fetch()``).
        sources:
            Optional subset of sources to run.  If ``None``, runs all
            registered connectors.

        Returns
        -------
        dict[str, list[EvidenceRecord]]
            Mapping of ``{source_name: [records]}``.
        """
        to_run: list[str] = sources or cls.list_sources()
        results: dict[str, list[EvidenceRecord]] = {}

        for source in to_run:
            try:
                connector_cls = cls.get(source)
                config = ConnectorConfig(tenant_id=tenant_id)
                connector = connector_cls(config)
                try:
                    await connector.connect()
                    records = await connector.fetch(since=since)
                    results[source] = records
                    logger.info(
                        "V6ConnectorRegistry[%s]: fetched %d records",
                        source,
                        len(records),
                    )
                finally:
                    await connector.close()
            except Exception as exc:
                logger.warning(
                    "V6ConnectorRegistry[%s]: failed — %s",
                    source,
                    exc,
                )
                results[source] = []

        return results


# ── Auto-register V6 connectors at import time ────────────────────────────


def _auto_register() -> None:
    """Import and register all known V6 connectors."""
    from src.connectors.notion import NotionConnector
    from src.connectors.slack_v6 import SlackV6Connector
    from src.connectors.jira import JiraConnector
    from src.connectors.salesforce_v6 import SalesforceV6Connector

    V6ConnectorRegistry.register("notion", NotionConnector)
    V6ConnectorRegistry.register("slack", SlackV6Connector)
    V6ConnectorRegistry.register("jira", JiraConnector)
    V6ConnectorRegistry.register("salesforce", SalesforceV6Connector)


_auto_register()

__all__ = [
    "V6ConnectorRegistry",
]
