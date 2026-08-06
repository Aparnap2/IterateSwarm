"""Normalizer registry — maps ``source_type`` to normalizer functions.

Each normalizer accepts a raw ``dict`` (as returned by a connector or
upload handler) and returns a canonical ``EvidenceRecord``.

Usage::

    registry = NormalizerRegistry()

    @registry.register("slack")
    def normalize_slack(raw: dict) -> EvidenceRecord:
        ...

    record = registry.normalize("slack", raw_data)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.entities.models import EvidenceRecord

logger = logging.getLogger(__name__)

# Type alias for a normalizer function: raw dict → EvidenceRecord.
NormalizerFn = Callable[[dict[str, Any]], EvidenceRecord]


class NormalizerRegistry:
    """Maps ``source_type`` strings to normalizer functions.

    Thread-safe for concurrent reads after registration (no mutex is
    needed because the registry is populated at import / init time and
    never mutated during normal operation).
    """

    def __init__(self) -> None:
        self._registry: dict[str, NormalizerFn] = {}

    # ── Public API ──────────────────────────────────────────────────────

    def register(self, source_type: str) -> Callable[[NormalizerFn], NormalizerFn]:
        """Decorator that registers a normalizer for *source_type*.

        Usage::

            registry = NormalizerRegistry()

            @registry.register("slack")
            def normalize_slack(raw: dict) -> EvidenceRecord:
                ...
        """

        def decorator(fn: NormalizerFn) -> NormalizerFn:
            if source_type in self._registry:
                logger.warning(
                    "Overwriting existing normalizer for source_type=%r", source_type
                )
            self._registry[source_type] = fn
            logger.debug("Registered normalizer for source_type=%r", source_type)
            return fn

        return decorator

    def normalize(self, source_type: str, raw_data: dict[str, Any]) -> EvidenceRecord:
        """Look up the normalizer for *source_type* and apply it to *raw_data*.

        Raises
        ------
        KeyError
            If no normalizer is registered for *source_type*.
        """
        try:
            normalizer = self._registry[source_type]
        except KeyError:
            raise KeyError(
                f"No normalizer registered for source_type={source_type!r}. "
                f"Available: {list(self._registry)}"
            ) from None
        return normalizer(raw_data)

    @property
    def registered_types(self) -> list[str]:
        """Return sorted list of registered source type keys."""
        return sorted(self._registry)

    def __contains__(self, source_type: str) -> bool:
        return source_type in self._registry

    def __len__(self) -> int:
        return len(self._registry)


# ── Module-level singleton (convenience for simple use-cases) ───────────

_default_registry: NormalizerRegistry | None = None


def get_default_registry() -> NormalizerRegistry:
    """Return (or create) the module-level singleton registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = NormalizerRegistry()
    return _default_registry


def register(source_type: str) -> Callable[[NormalizerFn], NormalizerFn]:
    """Decorator that registers on the default singleton registry."""
    return get_default_registry().register(source_type)


def normalize(source_type: str, raw_data: dict[str, Any]) -> EvidenceRecord:
    """Convenience: normalise *raw_data* via the default singleton registry."""
    return get_default_registry().normalize(source_type, raw_data)
