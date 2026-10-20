"""SIRI Vehicle/Stop Monitoring JSON -> our domain model. Pure functions, no I/O.

Verified against live responses on 2026-10-04 (see tests/fixtures/):

- Envelope: {"sys": "VM", "status": "OK", "servertime": <unix>, "result": {"vehicles": {...}}}
- `result.vehicles` is an object keyed by vehicleref, not an array.
- `delay` is an ISO 8601 duration ("PT90S", "-PT8S"). POSITIVE MEANS LATE: it matches
  next_expectedarrivaltime - next_aimedarrivaltime. `delaysecs` (an int) is present less often.
- A few vehicles have no latitude/longitude at all. They are skipped, not crashed on.
- `__routeref` (undocumented, double underscore) equals the GTFS route_id. `publishedlinename`
  equals GTFS route_short_name. We prefer the former and fall back to the latter.
- All timestamps are Unix seconds (UTC).
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.schemas import Departure, UpstreamStatus, Vehicle

logger = logging.getLogger(__name__)

# (routeref, line name) -> GTFS route_id or None. Provided by the GTFS cache.
RouteResolver = Callable[[str | None, str | None], str | None]


class SiriParseError(ValueError):
    """The document does not look like a SIRI response at all."""


@dataclass(frozen=True)
class ParsedVehicleMonitoring:
    status: UpstreamStatus
    server_time: datetime | None
    vehicles: list[Vehicle]
    skipped: int  # vehicles dropped because they had no usable position


_STATUS_MAP: dict[str, UpstreamStatus] = {
    "OK": "OK",
    "PENDING": "PENDING",  # service starting, data in 5-30 s
    "NO_SIRI_DATA": "NO_DATA",  # Föli's own backend has problems
}

# Only the subset of ISO 8601 durations Föli actually uses: optional sign, days, h, m, s.
_DURATION_RE = re.compile(
    r"^(?P<sign>[-+])?P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


def parse_iso8601_duration(value: str) -> int | None:
    """'PT90S' -> 90, '-PT1M30S' -> -90, 'PT0S' -> 0. Returns None if unparseable."""
    match = _DURATION_RE.match(value.strip())
    if not match:
        return None
    parts = match.groupdict()
    if not any(parts[k] for k in ("days", "hours", "minutes", "seconds")):
        return None  # "P" or "PT" alone is not a duration
    total = (
        int(parts["days"] or 0) * 86400
        + int(parts["hours"] or 0) * 3600
        + int(parts["minutes"] or 0) * 60
        + float(parts["seconds"] or 0)
    )
    return -round(total) if parts["sign"] == "-" else round(total)


def _unix_to_datetime(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return None
    return datetime.fromtimestamp(value, tz=UTC)


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coordinate(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _parse_delay(raw: dict[str, Any]) -> int | None:
    delay = raw.get("delay")
    if isinstance(delay, str):
        parsed = parse_iso8601_duration(delay)
        if parsed is not None:
            return parsed
    secs = raw.get("delaysecs")
    if isinstance(secs, int) and not isinstance(secs, bool):
        return secs
    return None


def parse_status(payload: Any) -> UpstreamStatus:
    if not isinstance(payload, dict) or "status" not in payload:
        raise SiriParseError("missing 'status' in SIRI envelope")
    raw_status = str(payload["status"])
    status = _STATUS_MAP.get(raw_status)
    if status is None:
        # Unknown status strings are treated as "no data" rather than crashing the poller.
        logger.warning("Unknown SIRI status %r; treating as NO_DATA", raw_status)
        return "NO_DATA"
    return status


def parse_vehicle(
    key: str, raw: dict[str, Any], resolve_route: RouteResolver | None
) -> Vehicle | None:
    """Convert one SIRI vehicle. Returns None when it has no usable position."""
    lat = _coordinate(raw.get("latitude"))
    lon = _coordinate(raw.get("longitude"))
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    recorded_at = _unix_to_datetime(raw.get("recordedattime"))
    if recorded_at is None:
        return None

    line = _str_or_none(raw.get("publishedlinename")) or _str_or_none(raw.get("lineref"))
    routeref = _str_or_none(raw.get("__routeref"))
    route_id = resolve_route(routeref, line) if resolve_route else None

    return Vehicle(
        id=_str_or_none(raw.get("vehicleref")) or key,
        line=line,
        route_id=route_id,
        direction=_str_or_none(raw.get("directionref")),
        destination=_str_or_none(raw.get("destinationname")),
        lat=lat,
        lon=lon,
        delay_s=_parse_delay(raw),
        next_stop=_str_or_none(raw.get("next_stoppointname")),
        recorded_at=recorded_at,
        monitored=bool(raw.get("monitored", False)),
    )


def parse_vehicle_monitoring(
    payload: Any, resolve_route: RouteResolver | None = None
) -> ParsedVehicleMonitoring:
    status = parse_status(payload)
    server_time = _unix_to_datetime(payload.get("servertime"))
    if status != "OK":
        # PENDING / NO_SIRI_DATA come with an empty result. They are states, not errors.
        return ParsedVehicleMonitoring(status, server_time, [], 0)

    result = payload.get("result")
    raw_vehicles = result.get("vehicles") if isinstance(result, dict) else None
    if not isinstance(raw_vehicles, dict):
        raise SiriParseError("status OK but 'result.vehicles' is missing or not an object")

    vehicles: list[Vehicle] = []
    skipped = 0
    for key, raw in raw_vehicles.items():
        vehicle = parse_vehicle(key, raw, resolve_route) if isinstance(raw, dict) else None
        if vehicle is None:
            skipped += 1
        else:
            vehicles.append(vehicle)
    return ParsedVehicleMonitoring(status, server_time, vehicles, skipped)


def parse_stop_monitoring(
    payload: Any, resolve_route: RouteResolver | None = None
) -> tuple[UpstreamStatus, list[Departure]]:
    """SIRI SM: `result` is an array of upcoming visits to one stop."""
    status = parse_status(payload)
    if status != "OK":
        return status, []
    result = payload.get("result")
    if not isinstance(result, list):
        raise SiriParseError("status OK but 'result' is not an array")

    departures: list[Departure] = []
    for raw in result:
        if not isinstance(raw, dict):
            continue
        line = _str_or_none(raw.get("lineref"))
        routeref = _str_or_none(raw.get("__routeref"))
        departures.append(
            Departure(
                line=line,
                route_id=resolve_route(routeref, line) if resolve_route else None,
                destination=_str_or_none(raw.get("destinationdisplay")),
                aimed_departure=_unix_to_datetime(raw.get("aimeddeparturetime")),
                expected_departure=_unix_to_datetime(raw.get("expecteddeparturetime")),
                monitored=bool(raw.get("monitored", False)),
                vehicle_id=_str_or_none(raw.get("vehicleref")),
            )
        )
    departures.sort(
        key=lambda d: d.expected_departure or d.aimed_departure or datetime.max.replace(tzinfo=UTC)
    )
    return status, departures
