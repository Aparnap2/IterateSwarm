"""Retry utilities with exponential backoff and circuit breaker for connectors.

Provides two resilience primitives consumed by every connector in this package:

* ``circuit_breaker`` — decorator that trips after *failure_threshold*
  consecutive failures and self-heals after *recovery_timeout* seconds.
* ``retry_with_backoff`` — helper that re-invokes a zero-arg callable with
  jittered exponential backoff.  An optional *retry_if* predicate lets callers
  distinguish transient from permanent exceptions (e.g. HTTP 5xx vs 4xx).

The circuit breaker comes in two flavours:

1. **In-memory** (``InMemoryCircuitBreaker``) — local dict, no dependencies.
2. **Redis-backed** (``RedisCircuitBreaker``) — distributed state shared across
   workers, with graceful fallback to in-memory when Redis is unavailable.

The module-level ``circuit_breaker`` decorator uses ``RedisCircuitBreaker``
when Redis is reachable, falling back to ``InMemoryCircuitBreaker`` otherwise.
"""

import json
import logging
import os
import random
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConnectorError(Exception):
    """Raised when a connector fails after exhausting all retry attempts."""


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is in the *open* state."""


# ---------------------------------------------------------------------------
# Circuit breaker backends
# ---------------------------------------------------------------------------


class InMemoryCircuitBreaker:
    """In-process circuit breaker using a module-level dict.

    State is scoped to the current process — acceptable for single-worker
    deployments or as a fallback when Redis is unavailable.
    """

    _state: dict[str, dict] = {}

    def _get_state(self, name: str) -> dict:
        return self._state.setdefault(
            name, {"failures": 0, "open": False, "last_failure": 0.0}
        )

    def is_open(self, name: str) -> bool:
        return self._get_state(name)["open"]

    def last_failure(self, name: str) -> float:
        return self._get_state(name)["last_failure"]

    def failures(self, name: str) -> int:
        return self._get_state(name)["failures"]

    def record_success(self, name: str) -> None:
        state = self._get_state(name)
        state["failures"] = 0
        state["open"] = False

    def record_failure(self, name: str) -> int:
        state = self._get_state(name)
        state["failures"] += 1
        state["last_failure"] = time.time()
        return state["failures"]

    def trip(self, name: str) -> None:
        self._get_state(name)["open"] = True

    def half_open(self, name: str) -> None:
        state = self._get_state(name)
        state["open"] = False
        state["failures"] = 0

    def reset(self, name: str) -> None:
        self._state.pop(name, None)

    def clear_all(self) -> None:
        self._state.clear()


class RedisCircuitBreaker:
    """Distributed circuit breaker backed by Redis.

    Uses the key pattern ``circuit_breaker:{name}:state`` storing a JSON
    document with ``open``, ``last_failure``, and ``failure_count`` fields.

    Gracefully falls back to an in-memory breaker if Redis is unavailable
    (detected at construction time — does *not* retry the connection).
    """

    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

    def __init__(self) -> None:
        self._fallback = InMemoryCircuitBreaker()
        self._redis = None
        self._available = False
        self._init_redis()

    def _init_redis(self) -> None:
        try:
            import redis as _redis_lib  # type: ignore[import-untyped]

            client = _redis_lib.from_url(
                self.REDIS_URL,
                decode_responses=True,
                socket_timeout=2,
            )
            client.ping()
            self._redis = client
            self._available = True
            logger.info("RedisCircuitBreaker: connected to Redis at %s", self.REDIS_URL)
        except Exception as exc:
            logger.warning(
                "RedisCircuitBreaker: Redis unavailable (%s), using in-memory fallback",
                exc,
            )
            self._available = False

    # -- key helpers -------------------------------------------------------

    @staticmethod
    def _state_key(name: str) -> str:
        return f"circuit_breaker:{name}:state"

    # -- read / write helpers ----------------------------------------------

    def _read_state(self, name: str) -> dict:
        if not self._available or self._redis is None:
            return self._fallback._get_state(name)
        try:
            raw = self._redis.get(self._state_key(name))
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return {"open": False, "last_failure": 0.0, "failure_count": 0}

    def _write_state(self, name: str, state: dict) -> None:
        if not self._available or self._redis is None:
            self._fallback._state[name] = state
            return
        try:
            self._redis.set(self._state_key(name), json.dumps(state))
        except Exception:
            # fallback: write to in-memory so we degrade gracefully
            self._fallback._state[name] = state

    # -- public API --------------------------------------------------------

    def is_open(self, name: str) -> bool:
        return self._read_state(name).get("open", False)

    def last_failure(self, name: str) -> float:
        return self._read_state(name).get("last_failure", 0.0)

    def failures(self, name: str) -> int:
        return self._read_state(name).get("failure_count", 0)

    def record_success(self, name: str) -> None:
        state = self._read_state(name)
        state["open"] = False
        state["failure_count"] = 0
        self._write_state(name, state)

    def record_failure(self, name: str) -> int:
        state = self._read_state(name)
        state["failure_count"] = state.get("failure_count", 0) + 1
        state["last_failure"] = time.time()
        self._write_state(name, state)
        return state["failure_count"]

    def trip(self, name: str) -> None:
        state = self._read_state(name)
        state["open"] = True
        self._write_state(name, state)

    def half_open(self, name: str) -> None:
        state = self._read_state(name)
        state["open"] = False
        state["failure_count"] = 0
        self._write_state(name, state)

    def reset(self, name: str) -> None:
        if self._available and self._redis is not None:
            try:
                self._redis.delete(self._state_key(name))
                return
            except Exception:
                pass
        self._fallback._state.pop(name, None)

    def clear_all(self) -> None:
        if self._available and self._redis is not None:
            try:
                keys = self._redis.keys("circuit_breaker:*")
                if keys:
                    self._redis.delete(*keys)
                return
            except Exception:
                pass
        self._fallback.clear_all()


# ---------------------------------------------------------------------------
# Shared circuit-breaker instance (auto-selects backend)
# ---------------------------------------------------------------------------

_circuit_breaker: InMemoryCircuitBreaker | RedisCircuitBreaker = (
    RedisCircuitBreaker()
)


def set_circuit_breaker(backend: InMemoryCircuitBreaker | RedisCircuitBreaker) -> None:
    """Override the shared circuit breaker (for testing).

    Usage::

        from src.integrations.retry import set_circuit_breaker, InMemoryCircuitBreaker
        set_circuit_breaker(InMemoryCircuitBreaker())
    """
    global _circuit_breaker
    _circuit_breaker = backend


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
):
    """Decorator implementing the circuit breaker pattern.

    After *failure_threshold* consecutive failures the circuit **opens** and
    all subsequent calls raise ``CircuitBreakerOpen`` for *recovery_timeout*
    seconds.  After that window a single **half-open** probe is allowed;
    success resets the circuit, another failure re-opens it.

    State is stored via the shared ``_circuit_breaker`` instance which tries
    Redis first and falls back to in-memory when Redis is unreachable.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            cb = _circuit_breaker

            if cb.is_open(name):
                if time.time() - cb.last_failure(name) > recovery_timeout:
                    cb.half_open(name)
                    logger.info(
                        "Circuit breaker %s: half-open, allowing probe request",
                        name,
                    )
                else:
                    raise CircuitBreakerOpen(
                        f"Circuit breaker {name} is open"
                    )

            try:
                result = func(*args, **kwargs)
                cb.record_success(name)
                return result
            except Exception:
                failure_count = cb.record_failure(name)
                if failure_count >= failure_threshold:
                    cb.trip(name)
                    logger.error(
                        "Circuit breaker %s: opened after %d consecutive failures",
                        name,
                        failure_count,
                    )
                raise

        return wrapper

    return decorator


def reset_circuit_state() -> None:
    """Clear all circuit breaker state.  Intended for test teardown."""
    _circuit_breaker.clear_all()


# ---------------------------------------------------------------------------
# Backoff helpers
# ---------------------------------------------------------------------------

def compute_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
) -> float:
    """Return a jittered exponential-backoff delay for *attempt* (0-indexed).

    The formula is::

        delay = min(base * factor^attempt, max) * uniform(0.5, 1.5)

    Adding jitter (the ``* uniform(...)``) prevents thundering-herd effects
    when multiple workers retry in lock-step.
    """
    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
    delay *= 0.5 + random.random()  # jitter: [0.5, 1.5) × delay
    return delay


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def retry_with_backoff(
    func: Callable[..., T],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    retry_if: Optional[Callable[[Exception], bool]] = None,
) -> T:
    """Execute *func* with jittered exponential-backoff retry.

    Parameters
    ----------
    func:
        Zero-argument callable to execute.
    max_attempts:
        Total number of attempts (1 = no retry).
    base_delay / max_delay / backoff_factor:
        Backoff tuning knobs (see :func:`compute_backoff_delay`).
    exceptions:
        Tuple of exception types eligible for retry.
    retry_if:
        Optional predicate ``(exc) -> bool``.  When provided, only exceptions
        for which the predicate returns *True* are retried; all others are
        re-raised immediately.  When ``None`` (the default), every exception
        matching the *exceptions* tuple is retried.

    Raises
    ------
    ConnectorError
        If all attempts fail.
    """
    last_exception: Optional[Exception] = None

    for attempt in range(max_attempts):
        try:
            return func()
        except exceptions as exc:
            # honour the optional retry predicate
            if retry_if is not None and not retry_if(exc):
                raise

            last_exception = exc

            if attempt < max_attempts - 1:
                delay = compute_backoff_delay(
                    attempt, base_delay, max_delay, backoff_factor
                )
                logger.warning(
                    "Retry %d/%d for %s: %s (waiting %.1fs)",
                    attempt + 1,
                    max_attempts,
                    getattr(func, "__name__", str(func)),
                    exc,
                    delay,
                )
                time.sleep(delay)

    raise ConnectorError(
        f"Failed after {max_attempts} attempts: {last_exception}"
    )



