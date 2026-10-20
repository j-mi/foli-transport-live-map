from datetime import UTC, datetime, timedelta
from typing import Any

from app.integrations.foli_client import CircuitBreaker, CircuitState, UpstreamUnavailable
from app.realtime.broadcaster import Broadcaster
from app.realtime.poller import VehiclePoller
from tests.conftest import load_fixture


class FakeFoli:
    def __init__(self) -> None:
        self.siri_breaker = CircuitBreaker("siri")
        self.responses: list[Any] = []

    async def fetch_vehicle_monitoring(self) -> Any:
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeGtfs:
    def resolve_route(self, routeref: str | None, line: str | None) -> str | None:
        return routeref


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=5)
        return self.now


def make_poller() -> tuple[VehiclePoller, FakeFoli, list[int]]:
    foli = FakeFoli()
    broadcaster = Broadcaster()
    published: list[int] = []
    broadcaster.publish = lambda message: published.append(message.seq)  # type: ignore[method-assign]
    poller = VehiclePoller(foli, FakeGtfs(), broadcaster, 5, now=Clock())  # type: ignore[arg-type]
    return poller, foli, published


async def test_starts_pending_then_publishes_parsed_snapshot() -> None:
    poller, foli, published = make_poller()
    assert poller.snapshot.upstream_status == "PENDING"
    assert poller.snapshot.fetched_at is None

    foli.responses.append(load_fixture("siri_vm.json"))
    await poller.poll_once()

    assert poller.snapshot.upstream_status == "OK"
    assert len(poller.snapshot.vehicles) == 9
    assert poller.snapshot.vehicles[0].route_id is not None
    assert published == [1]
    assert '"seq":1' in poller.message.data  # serialised once, shared by every client


async def test_keeps_last_good_positions_when_upstream_fails() -> None:
    poller, foli, published = make_poller()
    foli.responses.append(load_fixture("siri_vm.json"))
    await poller.poll_once()
    good = poller.snapshot

    # One failure: status unchanged (debounced), nothing re-sent, positions kept.
    foli.responses.append(UpstreamUnavailable("boom"))
    await poller.poll_once()
    assert poller.snapshot is good
    assert poller.consecutive_failures == 1
    assert published == [1]

    # Once the circuit breaker has opened we report DOWN, still with the last positions and
    # the ORIGINAL fetch time, so the UI can say how old they are.
    foli.siri_breaker.state = CircuitState.OPEN
    foli.responses.append(UpstreamUnavailable("boom"))
    await poller.poll_once()
    assert poller.snapshot.upstream_status == "DOWN"
    assert poller.snapshot.vehicles == good.vehicles
    assert poller.snapshot.fetched_at == good.fetched_at
    assert published == [1, 2]

    # Recovery publishes fresh data.
    foli.siri_breaker.state = CircuitState.CLOSED
    foli.responses.append(load_fixture("siri_vm.json"))
    await poller.poll_once()
    assert poller.snapshot.upstream_status == "OK"
    assert poller.snapshot.fetched_at > good.fetched_at
    assert poller.consecutive_failures == 0


async def test_pending_and_no_data_keep_positions() -> None:
    poller, foli, published = make_poller()
    foli.responses.append(load_fixture("siri_vm.json"))
    await poller.poll_once()

    foli.responses.append(load_fixture("siri_vm_no_siri_data.json"))
    await poller.poll_once()
    assert poller.snapshot.upstream_status == "NO_DATA"
    assert len(poller.snapshot.vehicles) == 9

    # Same status again: nothing new to tell clients.
    foli.responses.append(load_fixture("siri_vm_no_siri_data.json"))
    await poller.poll_once()
    assert published == [1, 2]


async def test_unparseable_response_reports_no_data() -> None:
    poller, foli, _ = make_poller()
    foli.responses.append({"status": "OK", "result": {}})
    await poller.poll_once()
    assert poller.snapshot.upstream_status == "NO_DATA"
