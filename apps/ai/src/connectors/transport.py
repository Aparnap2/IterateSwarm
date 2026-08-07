"""V6 Connector Transport Layer — HTTP abstraction for all connectors.

Provides a ``Transport`` protocol that decouples connector logic from
the raw HTTP client, enabling easy unit testing via ``MockTransport``.

Usage::

    from src.connectors.transport import HttpxTransport, TransportResponse

    transport = HttpxTransport(timeout=30.0)
    resp = await transport.get("https://api.example.com/items")
    print(resp.status_code, resp.json)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

# ── Response Model ────────────────────────────────────────────────────────


@dataclass
class TransportResponse:
    """Normalised HTTP response returned by all ``Transport`` implementations.

    Attributes
    ----------
    status_code:
        HTTP status code (``0`` for transport/connection errors).
    headers:
        Response headers as a dict.
    json:
        Parsed JSON body, if the content-type is JSON.
    text:
        Raw response body as a string.
    elapsed_ms:
        Request duration in milliseconds.
    """

    status_code: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    json: dict | list | None = None
    text: str = ""
    elapsed_ms: int = 0

    @property
    def is_success(self) -> bool:
        """Return ``True`` if the status code indicates success (2xx)."""
        return 200 <= self.status_code < 300

    @property
    def is_rate_limited(self) -> bool:
        """Return ``True`` if the response is a 429 rate-limit signal."""
        return self.status_code == 429

    @property
    def retry_after(self) -> float | None:
        """Return the ``Retry-After`` header value in seconds, if present."""
        raw = self.headers.get("Retry-After") or self.headers.get("retry-after")
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None


# ── Transport Protocol ────────────────────────────────────────────────────


class Transport(Protocol):
    """HTTP transport abstraction for V6 connectors.

    Implementations must be safe to use across multiple concurrent
    ``fetch()`` calls.  No authentication is handled here — that is
    the connector's responsibility.
    """

    async def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse:
        """Perform an HTTP GET request."""
        ...

    async def post(
        self,
        url: str,
        json: dict | list | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse:
        """Perform an HTTP POST request."""
        ...


# ── HttpxTransport ────────────────────────────────────────────────────────


class HttpxTransport:
    """Production HTTP transport backed by ``httpx.AsyncClient``.

    Features
    --------
    * Configurable timeout (default 30 seconds).
    * Automatic retry on 429 (rate-limit) and 5xx (server-error) statuses.
    * Exponential backoff: 1 s, 2 s, 4 s (max 3 retries).
    * Respects the ``Retry-After`` header when present on 429 responses.
    * Graceful handling of connection errors and timeouts.
    """

    _RETRYABLE_CODES = {429, 502, 503, 504}
    _MAX_RETRIES = 3
    _BACKOFF_SECONDS = [1.0, 2.0, 4.0]

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries if max_retries is not None else self._MAX_RETRIES
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialise the shared ``httpx.AsyncClient``."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse:
        """Perform an HTTP GET with retry and backoff."""
        return await self._request("GET", url, params=params, headers=headers)

    async def post(
        self,
        url: str,
        json: dict | list | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse:
        """Perform an HTTP POST with retry and backoff."""
        return await self._request("POST", url, json=json, headers=headers)

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
        json: dict | list | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse:
        """Execute *method* against *url* with retry logic."""
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                client = await self._get_client()
                start = asyncio.get_event_loop().time()

                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    headers=headers,
                )

                elapsed_ms = int((asyncio.get_event_loop().time() - start) * 1000)

                resp = TransportResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    text=response.text,
                    elapsed_ms=elapsed_ms,
                )

                # Attempt JSON parsing — best-effort.
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    try:
                        resp.json = response.json()
                    except (ValueError, TypeError):
                        pass

                # Retry on retryable status codes.
                if resp.status_code in self._RETRYABLE_CODES and attempt < self._max_retries:
                    delay = self._resolve_delay(resp, attempt)
                    logger.warning(
                        "Retryable status %s on %s %s — attempt %s/%s, waiting %.1fs",
                        resp.status_code,
                        method,
                        url,
                        attempt + 1,
                        self._max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                return resp

            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning("Timeout on %s %s — attempt %s/%s", method, url, attempt + 1, self._max_retries)
                if attempt < self._max_retries:
                    await asyncio.sleep(self._BACKOFF_SECONDS[attempt])
                    continue
            except httpx.ConnectError as exc:
                last_error = exc
                logger.warning("Connection error on %s %s — attempt %s/%s", method, url, attempt + 1, self._max_retries)
                if attempt < self._max_retries:
                    await asyncio.sleep(self._BACKOFF_SECONDS[attempt])
                    continue
            except httpx.HTTPError as exc:
                last_error = exc
                logger.error("HTTP error on %s %s: %s", method, url, exc)
                if attempt < self._max_retries:
                    await asyncio.sleep(self._BACKOFF_SECONDS[attempt])
                    continue

        # All retries exhausted — return an error response.
        error_text = f"Request failed after {self._max_retries + 1} attempts"
        if last_error:
            error_text += f": {last_error}"
        logger.error("%s — %s %s", error_text, method, url)
        return TransportResponse(status_code=0, text=error_text)

    def _resolve_delay(self, resp: TransportResponse, attempt: int) -> float:
        """Determine how long to wait before the next retry.

        Uses the ``Retry-After`` header when present on 429 responses,
        otherwise falls back to exponential backoff.
        """
        if resp.is_rate_limited:
            retry_after = resp.retry_after
            if retry_after is not None:
                return min(retry_after, 30.0)  # cap at 30 s
        return self._BACKOFF_SECONDS[min(attempt, len(self._BACKOFF_SECONDS) - 1)]

    async def close(self) -> None:
        """Close the underlying ``httpx.AsyncClient``."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> HttpxTransport:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: object | None = None,
    ) -> None:
        await self.close()


# ── MockTransport ─────────────────────────────────────────────────────────


class MockTransport:
    """Mock HTTP transport for unit testing V6 connectors.

    Takes a dictionary of ``method+path -> list[TransportResponse]`` and
    cycles through the response list on each matching call.  This lets
    tests simulate multi-step sequences (e.g. rate-limit then success).

    Parameters
    ----------
    responses:
        Mapping of ``"{http_method} {path}"`` (e.g. ``"GET /api/items"``)
        to a list of ``TransportResponse`` objects.  The list is cycled
        through with ``itertools.cycle``.
    default_response:
        Fallback response for unmatched routes.
    """

    def __init__(
        self,
        responses: dict[str, list[TransportResponse]] | None = None,
        default_response: TransportResponse | None = None,
    ) -> None:
        import itertools

        self._cycles: dict[str, itertools.cycle[TransportResponse]] = {}
        if responses:
            self._cycles = {
                key: itertools.cycle(seq) for key, seq in responses.items()
            }
        self._default = default_response or TransportResponse(
            status_code=404,
            text="No mock response registered for this route",
        )
        self._call_log: list[tuple[str, str, dict | list | None]] = []

    @property
    def call_log(self) -> list[tuple[str, str, dict | list | None]]:
        """Return the ordered list of ``(method, url, body)`` calls made."""
        return list(self._call_log)

    def _lookup(self, method: str, url: str) -> TransportResponse:
        """Return the next response for ``{method} {url}``, or default."""
        key = f"{method.upper()} {url.split('?')[0]}"
        cycle = self._cycles.get(key)
        if cycle is None:
            # Try without query string
            cycle = self._cycles.get(key)
        if cycle is None:
            # Try the normalized base path
            from urllib.parse import urlparse

            parsed = urlparse(url)
            path_key = f"{method.upper()} {parsed.path}"
            cycle = self._cycles.get(path_key)
        if cycle is not None:
            return next(cycle)
        return self._default

    async def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse:
        """Mock GET request — returns the next response for this route."""
        self._call_log.append(("GET", url, params))
        return self._lookup("GET", url)

    async def post(
        self,
        url: str,
        json: dict | list | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse:
        """Mock POST request — returns the next response for this route."""
        self._call_log.append(("POST", url, json))
        return self._lookup("POST", url)

    async def close(self) -> None:
        """No-op for mock transport."""
        return None

    async def __aenter__(self) -> MockTransport:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: object | None = None,
    ) -> None:
        await self.close()


__all__ = [
    "HttpxTransport",
    "MockTransport",
    "Transport",
    "TransportResponse",
]
