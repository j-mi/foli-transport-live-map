import asyncio
import json
from datetime import UTC, datetime

from app.api.vehicles import _heartbeat, snapshot_events
from app.realtime.broadcaster import Broadcaster, SnapshotMessage


def message(seq: int, status: str = "OK") -> SnapshotMessage:
    return SnapshotMessage(seq, status, datetime(2026, 10, 4, tzinfo=UTC), f'{{"seq":{seq}}}')


async def test_slow_subscriber_does_not_block_fast_one() -> None:
    broadcaster = Broadcaster(queue_size=2)
    received_fast: list[int] = []

    with broadcaster.subscribe() as fast, broadcaster.subscribe() as slow:
        for seq in range(1, 11):
            broadcaster.publish(message(seq))  # never awaits, so it can never block
            received_fast.append((await asyncio.wait_for(fast.get(), timeout=1)).seq)

        # The fast client saw everything.
        assert received_fast == list(range(1, 11))
        # The slow client never read: it holds only the newest two snapshots, oldest dropped.
        assert [slow.get_nowait().seq, slow.get_nowait().seq] == [9, 10]
        assert broadcaster.dropped_messages == 8

    assert broadcaster.subscriber_count == 0  # unsubscribed on exit


class FakePoller:
    def __init__(self, current: SnapshotMessage) -> None:
        self.message = current


async def test_stream_sends_current_snapshot_then_updates() -> None:
    broadcaster = Broadcaster()
    poller = FakePoller(message(5))
    events = snapshot_events(poller, broadcaster)  # type: ignore[arg-type]

    first = await anext(events)
    assert first.event == "status"
    assert json.loads(first.data)["upstream_status"] == "OK"

    second = await anext(events)
    assert (second.event, second.id, second.data) == ("vehicles", "5", '{"seq":5}')
    assert second.retry == 3000  # tells EventSource how long to wait before reconnecting

    assert broadcaster.subscriber_count == 1
    broadcaster.publish(message(5))  # duplicate of what was already sent: skipped
    broadcaster.publish(message(6))
    third = await asyncio.wait_for(anext(events), timeout=1)
    assert (third.event, third.id) == ("vehicles", "6")

    # A status change produces a `status` event before the snapshot.
    broadcaster.publish(message(7, status="DOWN"))
    status = await asyncio.wait_for(anext(events), timeout=1)
    assert status.event == "status" and json.loads(status.data)["upstream_status"] == "DOWN"
    assert (await asyncio.wait_for(anext(events), timeout=1)).id == "7"

    await events.aclose()
    assert broadcaster.subscriber_count == 0


def test_heartbeat_is_a_named_event_javascript_can_see() -> None:
    # SSE comment lines are invisible to EventSource listeners; a named event is not.
    event = _heartbeat()
    assert event.event == "heartbeat"
    assert event.data  # EventSource drops events with empty data
    assert b"event: heartbeat" in event.encode()
