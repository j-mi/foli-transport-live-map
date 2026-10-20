"""A tiny time-based cache with a size bound."""

import time
from collections import OrderedDict
from collections.abc import Callable


class TtlCache[V]:
    def __init__(
        self, ttl_s: float, max_entries: int = 500, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl_s = ttl_s
        self._max = max_entries
        self._clock = clock
        self._data: OrderedDict[str, tuple[float, V]] = OrderedDict()

    def get(self, key: str) -> V | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._data[key]
            return None
        return value

    def put(self, key: str, value: V) -> None:
        self._data[key] = (self._clock() + self._ttl_s, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)
