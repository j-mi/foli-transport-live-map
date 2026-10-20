import random

import httpx
import pytest
import respx

from app.integrations.foli_client import (
    CircuitOpenError,
    CircuitState,
    FoliClient,
    UpstreamClientError,
    UpstreamUnavailable,
    backoff_delay,
)

BASE = "https://data.foli.fi"
OK_BODY = {"sys": "VM", "status": "OK", "servertime": 1, "result": {"vehicles": {}}}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def client(sleeps: list[float], clock: FakeClock):
    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    http = FoliClient.build_http_client("test-agent/1.0")
    yield FoliClient(http, BASE, sleep=fake_sleep, rng=random.Random(42), clock=clock)
    await http.aclose()


@respx.mock(base_url=BASE)
async def test_timeout_is_retried_then_succeeds(
    respx_mock: respx.MockRouter, client: FoliClient, sleeps: list[float]
) -> None:
    route = respx_mock.get("/siri/vm").mock(
        side_effect=[httpx.ConnectTimeout("slow"), httpx.Response(200, json=OK_BODY)]
    )
    assert await client.fetch_vehicle_monitoring() == OK_BODY
    assert route.call_count == 2
    assert len(sleeps) == 1 and 0.25 <= sleeps[0] <= 0.75  # 0.5 s x jitter
    assert client.siri_breaker.state is CircuitState.CLOSED


@respx.mock(base_url=BASE)
async def test_5xx_is_retried_with_growing_backoff(
    respx_mock: respx.MockRouter, client: FoliClient, sleeps: list[float]
) -> None:
    route = respx_mock.get("/siri/vm").mock(
        side_effect=[httpx.Response(502), httpx.Response(503), httpx.Response(200, json=OK_BODY)]
    )
    assert await client.fetch_vehicle_monitoring() == OK_BODY
    assert route.call_count == 3
    assert 0.25 <= sleeps[0] <= 0.75
    assert 0.5 <= sleeps[1] <= 1.5


@respx.mock(base_url=BASE)
async def test_4xx_is_not_retried(
    respx_mock: respx.MockRouter, client: FoliClient, sleeps: list[float]
) -> None:
    route = respx_mock.get("/siri/sm/999").respond(404, text="<html>404 Not found</html>")
    with pytest.raises(UpstreamClientError) as error:
        await client.fetch_stop_monitoring("999")
    assert error.value.status_code == 404
    assert route.call_count == 1
    assert sleeps == []
    # Föli answered, so it is up: a 4xx does not count against the circuit breaker.
    assert client.siri_breaker.consecutive_failures == 0


@respx.mock(base_url=BASE)
async def test_invalid_json_is_retried(respx_mock: respx.MockRouter, client: FoliClient) -> None:
    respx_mock.get("/siri/vm").mock(
        side_effect=[httpx.Response(200, text="<html>proxy</html>"), httpx.Response(200, json={})]
    )
    assert await client.fetch_vehicle_monitoring() == {}


@respx.mock(base_url=BASE)
async def test_repeated_failures_open_the_circuit(
    respx_mock: respx.MockRouter, client: FoliClient, clock: FakeClock
) -> None:
    route = respx_mock.get("/siri/vm").respond(500)

    for _ in range(5):
        with pytest.raises(UpstreamUnavailable):
            await client.fetch_vehicle_monitoring()
    assert route.call_count == 15  # 5 calls x 3 attempts
    assert client.siri_breaker.state is CircuitState.OPEN

    # While open, calls fail fast without touching the network.
    with pytest.raises(CircuitOpenError):
        await client.fetch_vehicle_monitoring()
    assert route.call_count == 15

    # GTFS has its own breaker and is unaffected.
    assert client.gtfs_breaker.state is CircuitState.CLOSED

    # After the cool-down exactly one probe goes out; it fails, so the circuit re-opens.
    clock.now += 30
    with pytest.raises(UpstreamUnavailable):
        await client.fetch_vehicle_monitoring()
    assert route.call_count == 16
    assert client.siri_breaker.state is CircuitState.OPEN

    # Next probe succeeds: the circuit closes again.
    clock.now += 30
    route.respond(200, json=OK_BODY)
    assert await client.fetch_vehicle_monitoring() == OK_BODY
    assert client.siri_breaker.state is CircuitState.CLOSED


@respx.mock(base_url=BASE)
async def test_sends_user_agent_and_encodes_ids(
    respx_mock: respx.MockRouter, client: FoliClient
) -> None:
    route = respx_mock.get("/gtfs/v0/ds/shapes/a%2Fb").respond(json=[])
    await client.fetch_shape("ds", "a/b")
    request = route.calls.last.request
    assert request.headers["user-agent"] == "test-agent/1.0"


def test_backoff_grows_exponentially_with_bounded_jitter() -> None:
    rng = random.Random(1)
    for attempt, (low, high) in enumerate([(0.25, 0.75), (0.5, 1.5), (1.0, 3.0)], start=1):
        for _ in range(50):
            assert low <= backoff_delay(attempt, rng) <= high
