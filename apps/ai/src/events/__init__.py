"""Events package for OntologyAI — canonical bus is Redpanda."""

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# Canonical bus: Redpanda (used for Go↔Python interop)
# Redis Streams (bus.py) is deprecated — enable via ENABLE_REDIS_STREAMS=on
_USE_REDPANDA = os.getenv("ENABLE_REDIS_STREAMS") != "on"

if _USE_REDPANDA:
    try:
        import aiokafka  # noqa: F401 — detect availability
    except ImportError:
        log.warning("aiokafka not installed — falling back to Redis Streams event bus")
        _USE_REDPANDA = False

if _USE_REDPANDA:
    from src.events.redpanda import publish_guardian_result, get_producer

    async def emit(topic: str, tenant_id: str, payload: dict[str, Any]) -> bool:
        """Emit event via canonical Redpanda bus (deprecated bus.py interface)."""
        pub = await get_producer()
        return await pub.publish(
            topic=topic,
            tenant_id=tenant_id,
            event_type="ORCHESTRATION_EVENT",
            source="orchestration",
            payload=payload,
        )

    __all__ = [
        "emit",
        "publish_guardian_result",
    ]
else:
    # Legacy Redis Streams fallback (either user opted in via ENABLE_REDIS_STREAMS=on,
    # or aiokafka is not installed)
    from src.events.bus import (  # noqa: F401
        EventBus,
        emit,
        consume,
        acknowledge,
        get_event_bus,
    )

    __all__ = [
        "EventBus",
        "emit",
        "consume",
        "acknowledge",
        "get_event_bus",
    ]