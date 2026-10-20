"""All outbound HTTP to data.foli.fi goes through this module.

Föli is an external system we do not control. This client absorbs its failure modes so the
rest of the backend can assume "either I get parsed JSON, or I get a clear UpstreamError".

Resilience patterns, each explained where it is implemented:

1. Timeouts       - never wait forever on a slow or hung upstream.
2. Retries        - retry transient failures (network errors, timeouts, 5xx) with exponential
                    backoff and jitter. Never retry 4xx: the request itself is wrong.
3. Circuit breaker - after repeated failures, stop hammering a struggling upstream and only
                    probe it occasionally until it recovers.

Why retrying is safe here: every call is an HTTP GET, which is idempotent by definition.
Repeating it cannot change anything on Föli's side. (We would NOT blindly retry a POST that
creates something, because a retry after a timeout could create it twice.)
"""

import asyncio
import enum
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# -- Timeouts ---------------------------------------------------------------------------------
# Connecting should be quick; if TCP/TLS takes more than 3 s the host is likely unreachable.
# Reading gets more room because the SIRI VM document contains every vehicle (~1 MB unzipped).
DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=5.0)

# -- Retry policy ------------------------------------------------------------------------------
MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 0.5  # 0.5 s, 1 s, 2 s, ... before jitter


class UpstreamError(Exception):
    """Base class: Föli could not give us a usable answer."""


class UpstreamUnavailable(UpstreamError):
    """Network error, timeout, 5xx or malformed body, still failing after retries."""


class UpstreamClientError(UpstreamError):
    """Föli answered with a 4xx. Retrying would not help."""

    def __init__(self, status_code: int, url: str) -> None:
        super().__init__(f"Föli returned HTTP {status_code} for {url}")
        self.status_code = status_code


class CircuitOpenError(UpstreamError):
    """We are deliberately not calling Föli right now because it has been failing."""


class _RetryableError(Exception):
    """Internal marker for a single failed attempt that is worth retrying."""


class CircuitState(enum.StrEnum):
    CLOSED = "CLOSED"  # normal operation, requests flow
    OPEN = "OPEN"  # upstream considered down, requests fail fast without network I/O
    HALF_OPEN = "HALF_OPEN"  # cool-down elapsed, one probe request is allowed through


class CircuitBreaker:
    """A deliberately small circuit breaker.

    Why: when Föli is down, every poll would otherwise spend ~40 s on timeouts and retries,
    multiplied by every endpoint we call. That wastes our resources and adds load to a system
    that is already struggling. After `failure_threshold` consecutive failed calls we "open"
    the circuit: calls fail immediately. Every `reset_timeout_s` we let exactly one probe
    through (HALF_OPEN). If the probe succeeds the circuit closes; if not it opens again.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout_s = reset_timeout_s
        self._clock = clock
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self._opened_at = 0.0

    def allow_request(self) -> bool:
        if self.state is CircuitState.OPEN:
            if self._clock() - self._opened_at >= self.reset_timeout_s:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit %s half-open: sending one probe request", self.name)
                return True
            return False
        # CLOSED, or HALF_OPEN with a probe already in flight. Concurrent calls during a probe
        # are rare here (one poller), so we keep it simple and let them through.
        return True

    def record_success(self) -> None:
        if self.state is not CircuitState.CLOSED:
            logger.info("Circuit %s closed: upstream recovered", self.name)
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        should_open = (
            self.state is CircuitState.HALF_OPEN
            or self.consecutive_failures >= self.failure_threshold
        )
        if should_open and self.state is not CircuitState.OPEN:
            logger.warning(
                "Circuit %s open after %d consecutive failures; probing every %.0f s",
                self.name,
                self.consecutive_failures,
                self.reset_timeout_s,
            )
        if should_open:
            self.state = CircuitState.OPEN
            self._opened_at = self._clock()


def backoff_delay(attempt: int, rng: random.Random | None = None) -> float:
    """Delay before retry number `attempt` (1-based): 0.5 s, 1 s, 2 s, ... times a jitter factor.

    Jitter (a random factor between 0.5 and 1.5) matters when many clients fail at the same
    moment: without it they all retry in lockstep and hit the recovering server together
    (a "thundering herd"). With one backend it matters less, but it costs nothing.
    """
    rng = rng or random
    return BACKOFF_BASE_S * (2 ** (attempt - 1)) * rng.uniform(0.5, 1.5)


class FoliClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._rng = rng
        # Separate breakers so one failing endpoint group cannot stop the others: e.g. a burst
        # of stop-monitoring errors must not pause live vehicle polling.
        self.siri_breaker = CircuitBreaker("siri-vm", clock=clock)
        self.stop_monitoring_breaker = CircuitBreaker("siri-sm", clock=clock)
        self.gtfs_breaker = CircuitBreaker("gtfs", clock=clock)

    @staticmethod
    def build_http_client(user_agent: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            # Föli's short GTFS URLs (/gtfs/stops) are 302 redirects to a dataset-versioned URL.
            follow_redirects=True,
            # A courtesy to the API provider: they can see who is calling and contact us.
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )

    # -- Public API: one method per Föli endpoint we use ---------------------------------------

    async def fetch_vehicle_monitoring(self) -> dict[str, Any]:
        """SIRI VM: every active vehicle in one document. Poll no faster than every 3 s."""
        return await self._get_json("/siri/vm", self.siri_breaker)

    async def fetch_stop_monitoring(self, stop_id: str) -> dict[str, Any]:
        """SIRI SM: upcoming departures for one stop."""
        return await self._get_json(f"/siri/sm/{_seg(stop_id)}", self.stop_monitoring_breaker)

    async def fetch_gtfs_index(self) -> dict[str, Any]:
        """Dataset index with `latest` and `datasets`.

        Note the trailing slash: `/gtfs` returns 404, `/gtfs/` returns the index (verified).
        """
        return await self._get_json("/gtfs/", self.gtfs_breaker)

    async def fetch_gtfs_table(self, dataset_id: str, table: str) -> Any:
        """A whole GTFS table from one specific dataset, e.g. `stops` or `routes`.

        We request the versioned URL directly so every table comes from the same dataset,
        even if Föli publishes a new one between two requests.
        """
        return await self._get_json(f"/gtfs/v0/{_seg(dataset_id)}/{table}", self.gtfs_breaker)

    async def fetch_trips_for_route(self, dataset_id: str, route_id: str) -> Any:
        path = f"/gtfs/v0/{_seg(dataset_id)}/trips/route/{_seg(route_id)}"
        return await self._get_json(path, self.gtfs_breaker)

    async def fetch_shape(self, dataset_id: str, shape_id: str) -> Any:
        path = f"/gtfs/v0/{_seg(dataset_id)}/shapes/{_seg(shape_id)}"
        return await self._get_json(path, self.gtfs_breaker)

    # -- The retry loop -----------------------------------------------------------------------

    async def _get_json(self, path: str, breaker: CircuitBreaker) -> Any:
        url = f"{self._base_url}{path}"
        if not breaker.allow_request():
            raise CircuitOpenError(f"Not calling Föli ({breaker.name} circuit open)")

        # While probing a half-open circuit we make a single attempt: the point of the probe is
        # to ask "are you back?" cheaply, not to retry aggressively against a failing server.
        attempts = 1 if breaker.state is CircuitState.HALF_OPEN else self._max_attempts
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                result = await self._attempt(url)
            except UpstreamClientError:
                # A 4xx means Föli is up and answered; our request was wrong (e.g. unknown stop).
                # That says nothing bad about upstream health, so it counts as a success for
                # the breaker, and retrying it would be pointless.
                breaker.record_success()
                raise
            except _RetryableError as exc:
                last_error = exc
                if attempt < attempts:
                    delay = backoff_delay(attempt, self._rng)
                    logger.info(
                        "Föli %s failed (attempt %d/%d): %s; retrying in %.2f s",
                        path,
                        attempt,
                        attempts,
                        exc,
                        delay,
                    )
                    await self._sleep(delay)
                continue
            breaker.record_success()
            return result

        breaker.record_failure()
        raise UpstreamUnavailable(f"Föli {path} failed after {attempts} attempt(s): {last_error}")

    async def _attempt(self, url: str) -> Any:
        """One HTTP request. Classifies every outcome as success, retryable or client error."""
        try:
            response = await self._http.get(url)
        except httpx.TimeoutException as exc:
            raise _RetryableError(f"timeout ({type(exc).__name__})") from exc
        except httpx.TransportError as exc:
            # DNS failure, connection refused, connection reset, TLS errors...
            raise _RetryableError(f"network error ({type(exc).__name__})") from exc

        if response.status_code >= 500:
            raise _RetryableError(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            raise UpstreamClientError(response.status_code, url)
        try:
            # httpx transparently un-gzips: Föli always sends `Content-Encoding: gzip`.
            return response.json()
        except ValueError as exc:
            # A truncated or HTML body (e.g. a proxy error page with status 200) is most likely
            # transient, so we treat it like a 5xx.
            raise _RetryableError("response body is not valid JSON") from exc


def _seg(value: str) -> str:
    """Percent-encode one URL path segment so an ID can never change the path we request."""
    return quote(value, safe="")
