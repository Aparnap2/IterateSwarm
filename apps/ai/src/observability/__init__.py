"""Pipeline traceability & observability harness for the mission pipeline.

Sprint A — E2E pipeline validation. Provides a small, dependency-free toolkit
so every stage of the flow

    connector-event → evidence → mission → decision → snapshot → timeline

carries a single ``trace_id`` + ``correlation_id`` end-to-end without threading
parameters through every call signature.

Modules
-------
* :mod:`src.observability.trace_context` — typed ``TraceContext`` dataclass +
  a ``contextvars``-based entry/exit helper so stages can read the active ids
  without explicit plumbing.
* :mod:`src.observability.pipeline` — typed ``PipelineRun`` (per-stage latency,
  retry count, status) + a ``run_stage`` wrapper that retries transient
  failures and records results.

Stdlib only — no new runtime dependencies.
"""
from __future__ import annotations

from src.observability.pipeline import (
    PipelineRun,
    StageResult,
    StageStatus,
    TRANSIENT_EXCEPTIONS,
    run_stage,
)
from src.observability.trace_context import (
    TraceContext,
    current,
    get,
    trace_context,
)

__all__ = [
    "PipelineRun",
    "StageResult",
    "StageStatus",
    "TRANSIENT_EXCEPTIONS",
    "TraceContext",
    "current",
    "get",
    "run_stage",
    "trace_context",
]