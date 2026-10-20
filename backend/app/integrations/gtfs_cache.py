"""In-memory cache of Föli's static GTFS data: routes (lines), stops and route shapes.

Verified shapes (2026-10-04):
- `GET /gtfs/` -> {"latest": "20261002-153501", "datasets": [...], ...}
- `routes`     -> array of {route_id, route_short_name, route_long_name, route_color, ...}
- `stops`      -> OBJECT keyed by stop_id (== stop_code): {stop_name, stop_lat, stop_lon, ...}
- `trips/route/<route_id>` -> array of {trip_id, direction_id, shape_id, trip_headsign, ...}
- `shapes/<shape_id>`      -> array of {lat, lon, traveled}

Consistency: we read `latest` once and then fetch every table from `/gtfs/v0/<latest>/...`, so
routes and stops always come from the same dataset. The loaded data lives in one immutable
`GtfsDataset` object that is swapped in a single assignment, so a request never sees routes
from one dataset and stops from another.
"""

import asyncio
import json
import logging
import re
from collections import Counter, OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.geo import feature_collection, line_feature, point_feature
from app.integrations.foli_client import FoliClient, UpstreamError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Route:
    route_id: str
    short_name: str
    long_name: str
    color: str | None
    text_color: str | None


@dataclass(frozen=True)
class Stop:
    stop_id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class GtfsDataset:
    dataset_id: str
    loaded_at: datetime
    routes: dict[str, Route]
    route_id_by_short_name: dict[str, str]
    lines_sorted: list[Route]
    stops: dict[str, Stop]
    # Serialised once per dataset; /stops just returns these bytes.
    stops_geojson: bytes = field(repr=False)


@dataclass(frozen=True)
class ShapeChoice:
    direction_id: str
    shape_id: str
    trip_count: int
    headsign: str | None


class GtfsNotReady(Exception):
    pass


class UnknownRoute(KeyError):
    pass


_HEX_COLOR = re.compile(r"^[0-9a-fA-F]{6}$")
_LINE_NAME = re.compile(r"^(\D*)(\d*)(.*)$")


def natural_line_key(short_name: str) -> tuple[int, str, float, str]:
    """Sort '1', '1A', '2', '10', 'K1', 'L10', 'Lautta' the way people expect."""
    prefix, number, suffix = _LINE_NAME.match(short_name).groups()  # type: ignore[union-attr]
    return (1 if prefix else 0, prefix, float(number) if number else float("inf"), suffix)


def _color(value: Any) -> str | None:
    text = str(value or "").strip().lstrip("#")
    return text.lower() if _HEX_COLOR.match(text) else None


def parse_routes(raw: Any) -> dict[str, Route]:
    rows = raw.values() if isinstance(raw, dict) else raw
    routes: dict[str, Route] = {}
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("route_id"):
            continue
        route_id = str(row["route_id"])
        routes[route_id] = Route(
            route_id=route_id,
            short_name=str(row.get("route_short_name") or route_id),
            long_name=str(row.get("route_long_name") or ""),
            color=_color(row.get("route_color")),
            text_color=_color(row.get("route_text_color")),
        )
    return routes


def parse_stops(raw: Any) -> dict[str, Stop]:
    # Föli returns an object keyed by stop id. Accept an array too in case that ever changes.
    items = raw.items() if isinstance(raw, dict) else ((None, row) for row in raw or [])
    stops: dict[str, Stop] = {}
    for key, row in items:
        if not isinstance(row, dict):
            continue
        stop_id = str(row.get("stop_code") or row.get("stop_id") or key or "")
        lat, lon = row.get("stop_lat"), row.get("stop_lon")
        if not stop_id or not isinstance(lat, int | float) or not isinstance(lon, int | float):
            continue
        stops[stop_id] = Stop(stop_id, str(row.get("stop_name") or stop_id), float(lat), float(lon))
    return stops


def build_dataset(dataset_id: str, raw_routes: Any, raw_stops: Any) -> GtfsDataset:
    routes = parse_routes(raw_routes)
    stops = parse_stops(raw_stops)
    stops_fc = feature_collection(
        [
            point_feature(s.lat, s.lon, {"stop_id": s.stop_id, "name": s.name})
            for s in stops.values()
        ]
    )
    return GtfsDataset(
        dataset_id=dataset_id,
        loaded_at=datetime.now(UTC),
        routes=routes,
        route_id_by_short_name={r.short_name: r.route_id for r in routes.values()},
        lines_sorted=sorted(routes.values(), key=lambda r: natural_line_key(r.short_name)),
        stops=stops,
        stops_geojson=json.dumps(stops_fc, ensure_ascii=False, separators=(",", ":")).encode(),
    )


def pick_shapes_per_direction(trips: Any) -> list[ShapeChoice]:
    """A route has no single shape in GTFS; each trip references one.

    Föli's documented approach: take the route's trips, and for each direction pick the shape
    used by the most trips. Rare variants (a depot run, one late-night detour) are ignored.
    Ties are broken by shape_id so the result is deterministic.
    """
    rows = trips.values() if isinstance(trips, dict) else trips
    by_direction: dict[str, Counter[str]] = {}
    headsigns: dict[tuple[str, str], Counter[str]] = {}
    for trip in rows or []:
        if not isinstance(trip, dict) or not trip.get("shape_id"):
            continue
        direction = str(trip.get("direction_id", "0"))
        shape_id = str(trip["shape_id"])
        by_direction.setdefault(direction, Counter())[shape_id] += 1
        if trip.get("trip_headsign"):
            headsigns.setdefault((direction, shape_id), Counter())[str(trip["trip_headsign"])] += 1

    choices = []
    for direction in sorted(by_direction):
        counts = by_direction[direction]
        shape_id, count = min(counts.items(), key=lambda item: (-item[1], item[0]))
        headsign_counts = headsigns.get((direction, shape_id))
        headsign = headsign_counts.most_common(1)[0][0] if headsign_counts else None
        choices.append(ShapeChoice(direction, shape_id, count, headsign))
    return choices


def parse_shape_points(raw: Any) -> list[tuple[float, float]]:
    rows = raw.values() if isinstance(raw, dict) else raw
    points = []
    for row in rows or []:
        if isinstance(row, dict):
            lat, lon = row.get("lat"), row.get("lon")
            if isinstance(lat, int | float) and isinstance(lon, int | float):
                points.append((row.get("traveled", 0) or 0, float(lat), float(lon)))
    points.sort(key=lambda p: p[0])  # order along the route by distance travelled
    return [(lat, lon) for _, lat, lon in points]


class _LruCache:
    """Tiny LRU so memory stays bounded however many lines users click."""

    def __init__(self, max_entries: int) -> None:
        self._max = max_entries
        self._data: OrderedDict[Any, Any] = OrderedDict()

    def get(self, key: Any) -> Any | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: Any, value: Any) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


class GtfsCache:
    def __init__(
        self,
        client: FoliClient,
        *,
        shape_cache_size: int = 256,
        on_dataset_loaded: Callable[[GtfsDataset], Awaitable[None]] | None = None,
    ) -> None:
        self._client = client
        self.on_dataset_loaded = on_dataset_loaded
        self._line_shapes = _LruCache(shape_cache_size)
        self.dataset: GtfsDataset | None = None

    @property
    def dataset_id(self) -> str | None:
        return self.dataset.dataset_id if self.dataset else None

    def require_dataset(self) -> GtfsDataset:
        if self.dataset is None:
            raise GtfsNotReady()
        return self.dataset

    async def refresh(self) -> bool:
        """Load the latest dataset if it differs from the one we have. Returns True if loaded."""
        index = await self._client.fetch_gtfs_index()
        latest = index.get("latest") if isinstance(index, dict) else None
        if not latest:
            raise UpstreamError("GTFS index has no 'latest' dataset id")
        if self.dataset and self.dataset.dataset_id == latest:
            return False

        raw_routes, raw_stops = await asyncio.gather(
            self._client.fetch_gtfs_table(latest, "routes"),
            self._client.fetch_gtfs_table(latest, "stops"),
        )
        dataset = build_dataset(latest, raw_routes, raw_stops)
        if not dataset.routes or not dataset.stops:
            raise UpstreamError(f"GTFS dataset {latest} has no routes or stops")
        self.dataset = dataset  # single atomic swap
        logger.info(
            "Loaded GTFS dataset %s: %d routes, %d stops",
            latest,
            len(dataset.routes),
            len(dataset.stops),
        )
        if self.on_dataset_loaded:
            await self.on_dataset_loaded(dataset)
        return True

    async def run_refresh_loop(self, interval_s: float, retry_s: float = 60.0) -> None:
        """Background task: load on start, then check for a new dataset every `interval_s`."""
        while True:
            try:
                await self.refresh()
                delay = interval_s
            except UpstreamError as exc:
                delay = retry_s if self.dataset is None else interval_s
                logger.warning("GTFS refresh failed: %s; next attempt in %.0f s", exc, delay)
            except Exception:
                delay = retry_s
                logger.exception("Unexpected error while refreshing GTFS")
            await asyncio.sleep(delay)

    def resolve_route(self, routeref: str | None, line: str | None) -> str | None:
        """Map a SIRI vehicle to a GTFS route_id.

        GTFS and SIRI come from different providers and are not guaranteed to agree. Unknown
        lines return None (the UI then draws them in a neutral style) instead of raising.
        """
        dataset = self.dataset
        if dataset is None:
            return None
        if routeref and routeref in dataset.routes:
            return routeref
        if line:
            return dataset.route_id_by_short_name.get(line)
        return None

    async def get_line_shapes(self, route_id: str) -> dict[str, Any]:
        """GeoJSON FeatureCollection with one LineString per direction of the route."""
        dataset = self.require_dataset()
        route = dataset.routes.get(route_id)
        if route is None:
            raise UnknownRoute(route_id)

        key = (dataset.dataset_id, route_id)
        cached = self._line_shapes.get(key)
        if cached is not None:
            return cached

        trips = await self._client.fetch_trips_for_route(dataset.dataset_id, route_id)
        choices = pick_shapes_per_direction(trips)
        raw_shapes = await asyncio.gather(
            *(self._client.fetch_shape(dataset.dataset_id, c.shape_id) for c in choices)
        )
        features = []
        for choice, raw_shape in zip(choices, raw_shapes, strict=True):
            points = parse_shape_points(raw_shape)
            if len(points) < 2:
                continue
            features.append(
                line_feature(
                    points,
                    {
                        "route_id": route.route_id,
                        "short_name": route.short_name,
                        "direction_id": choice.direction_id,
                        "shape_id": choice.shape_id,
                        "headsign": choice.headsign,
                        "trip_count": choice.trip_count,
                        "color": route.color,
                    },
                )
            )
        result = feature_collection(features)
        # Shapes are immutable within a dataset, so caching by (dataset, route) is always valid.
        self._line_shapes.put(key, result)
        return result
