"""Typed trace context — the single identity carried through the pipeline.

A ``TraceContext`` bundles the three ids every stage must propagate:

* ``trace_id``       — one id for the *whole* end-to-end run (a single event's
  journey through every stage).
* ``correlation_id`` — the id that ties a logical business unit (e.g. one
  connector event) together; used for idempotency/dedup across retries.
* ``tenant_id``      — multi-tenant isolation scope.

The context is exposed through a :mod:`contextvars`-based helper so stages can
read the active ids without threading parameters through every call signature.
A stage that needs the ids simply calls :func:`get` (or :func:`current`).

Stdlib only.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from uuid import uuid4


@dataclass(frozen=True)
class TraceContext:
    """Immutable identity for one end-to-end pipeline run.

    ``trace_id`` and ``correlation_id`` default to fresh UUIDs when not
    supplied; ``tenant_id`` defaults to ``"default"``.
    """

    trace_id: str
    correlation_id: str
    tenant_id: str = "default"

    @classmethod
    def new(
        cls,
        *,
        tenant_id: str = "default",
        trace_id: str | None = None,
        correlation_id: str | None = None,
    ) -> "TraceContext":
        """Build a context, generating any missing ids."""
        return cls(
            trace_id=trace_id or str(uuid4()),
            correlation_id=correlation_id or str(uuid4()),
            tenant_id=tenant_id,
        )

    def as_payload(self) -> dict[str, str]:
        """Serialise the ids for embedding in persisted payloads (timeline,
        snapshot, evidence provenance) so they round-trip end-to-end."""
        return {
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "tenant_id": self.tenant_id,
        }


# The active context for the current async task / thread.
_current: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "trace_context", default=None
)


def current() -> TraceContext | None:
    """Return the active ``TraceContext`` or ``None`` if none is set."""
    return _current.get()


def get() -> TraceContext:
    """Return the active ``TraceContext`` or raise if none is set.

    Use inside a stage when the ids are required and their absence is a bug.
    """
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError(
            "No active trace context. Wrap the pipeline in trace_context(...)."
        )
    return ctx


@contextmanager
def trace_context(ctx: TraceContext) -> Iterator[TraceContext]:
    """Context manager that installs ``ctx`` as the active context for the
    duration of the block, restoring the previous value on exit.

    Usage::

        with trace_context(TraceContext.new(tenant_id="acme")):
            await run_stage(...)   # stages can call get() to read the ids
    """
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)