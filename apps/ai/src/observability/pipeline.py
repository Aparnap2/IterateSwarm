"""Typed pipeline runner — per-stage input, output, latency, retries, status.

A :class:`PipelineRun` records every stage of an end-to-end flow so a caller
can prove, after the fact, that each stage ran, what it consumed/produced, how
long it took, how many times it was retried, and whether it succeeded.

:func:`run_stage` wraps a single stage callable with bounded retries on
*transient* exceptions and records a :class:`StageResult` into the run. It
supports both async and sync (blocking) callables — sync callables are executed
in a worker thread so they never block the event loop.

Stdlib only — no new runtime dependencies.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable

from src.observability.trace_context import TraceContext

logger = logging.getLogger(__name__)

# Exceptions treated as *transient* (worth retrying). Callers may pass a wider
# set (e.g. provider SDK network errors) via ``run_stage(..., transient=...)``.
TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


class StageStatus(str, Enum):
    """Lifecycle status of a single pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class StageResult:
    """Outcome of one stage execution (mutable while the stage runs)."""

    stage: str
    trace_id: str
    correlation_id: str
    status: StageStatus = StageStatus.PENDING
    input: Any = None
    output: Any = None
    error: str | None = None
    latency_ms: float = 0.0
    retry_count: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def ok(self) -> bool:
        return self.status == StageStatus.SUCCESS


@dataclass
class PipelineRun:
    """A full end-to-end run: the trace identity plus every stage result.

    ``stages`` preserves insertion order so the caller can replay the exact
    sequence of stages that executed.
    """

    trace: TraceContext
    stages: list[StageResult] = field(default_factory=list)

    def add(self, result: StageResult) -> None:
        self.stages.append(result)

    def stage(self, name: str) -> StageResult | None:
        """Return the last recorded result for ``name`` (or ``None``)."""
        for result in reversed(self.stages):
            if result.stage == name:
                return result
        return None

    def all_successful(self) -> bool:
        """True when every recorded stage succeeded."""
        return bool(self.stages) and all(s.ok() for s in self.stages)

    def failed_stages(self) -> list[StageResult]:
        return [s for s in self.stages if not s.ok()]

    def summary(self) -> dict[str, Any]:
        """Compact, serialisable summary for logs/assertions."""
        return {
            "trace_id": self.trace.trace_id,
            "correlation_id": self.trace.correlation_id,
            "tenant_id": self.trace.tenant_id,
            "stages": [
                {
                    "stage": s.stage,
                    "status": s.status.value,
                    "latency_ms": round(s.latency_ms, 3),
                    "retry_count": s.retry_count,
                    "error": s.error,
                }
                for s in self.stages
            ],
            "all_successful": self.all_successful(),
        }


async def _invoke(func: Callable[[], Any]) -> Any:
    """Call ``func`` and return its resolved value.

    * Coroutine functions are awaited directly.
    * Sync (blocking) callables run in a worker thread so they never block the
      event loop (e.g. the synchronous LLM ``decide`` call).
    * A sync callable that *returns* an awaitable (e.g. a lambda wrapping an
      async stage) is awaited too, so callers never receive a bare coroutine.
    """
    if inspect.iscoroutinefunction(func):
        return await func()
    result = await asyncio.to_thread(func)
    if inspect.isawaitable(result):
        return await result
    return result


async def run_stage(
    func: Callable[[], Any],
    *,
    stage: str,
    trace: TraceContext,
    retries: int = 2,
    timeout_s: float = 10.0,
    run: PipelineRun | None = None,
    stage_input: Any = None,
    transient: Iterable[type[BaseException]] | None = None,
) -> StageResult:
    """Run one pipeline stage with bounded retries and record its result.

    Parameters
    ----------
    func:
        Zero-argument callable for the stage. May be async or sync; sync
        blocking callables run in a worker thread.
    stage:
        Human-readable stage name (e.g. ``"evidence"``, ``"decision"``).
    trace:
        The :class:`TraceContext` identity for this run.
    retries:
        Number of *additional* attempts after the first (default 2 → up to 3
        total attempts).
    timeout_s:
        Per-attempt timeout in seconds.
    run:
        Optional :class:`PipelineRun` to record the result into. If omitted, a
        fresh run is created.
    stage_input:
        Optional value consumed by the stage, recorded on the result so the
        caller can audit exactly what each stage received.
    transient:
        Optional extra exception types to treat as transient. Always includes
        :data:`TRANSIENT_EXCEPTIONS`.

    Returns
    -------
    StageResult
        The recorded outcome (status, latency, retry count, output/error).
    """
    transient_set = tuple(TRANSIENT_EXCEPTIONS) + tuple(transient or ())
    run = run or PipelineRun(trace=trace)
    result = StageResult(
        stage=stage,
        trace_id=trace.trace_id,
        correlation_id=trace.correlation_id,
        input=stage_input,
    )
    run.add(result)

    for attempt in range(retries + 1):
        result.retry_count = attempt
        t0 = time.monotonic()
        try:
            output = await asyncio.wait_for(_invoke(func), timeout=timeout_s)
        except asyncio.TimeoutError:
            result.latency_ms = (time.monotonic() - t0) * 1000
            result.error = f"timeout after {timeout_s}s"
            if attempt < retries:
                await asyncio.sleep(_backoff(attempt))
                continue
            result.status = StageStatus.FAILED
            break
        except transient_set as exc:  # type: ignore[misc]
            result.latency_ms = (time.monotonic() - t0) * 1000
            result.error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                await asyncio.sleep(_backoff(attempt))
                continue
            result.status = StageStatus.FAILED
            break
        except Exception as exc:  # non-transient — fail immediately
            result.latency_ms = (time.monotonic() - t0) * 1000
            result.error = f"{type(exc).__name__}: {exc}"
            result.status = StageStatus.FAILED
            break
        else:
            result.output = output
            result.status = StageStatus.SUCCESS
            result.latency_ms = (time.monotonic() - t0) * 1000
            break

    if result.status == StageStatus.FAILED:
        logger.warning(
            "stage=%s failed after %d attempts: %s",
            stage,
            result.retry_count + 1,
            result.error,
        )
    return result


def _backoff(attempt: int) -> float:
    """Small linear backoff between retries (0.2s, 0.4s, ...)."""
    return 0.2 * (attempt + 1)