"""Download small, real samples from every Föli endpoint we use into tests/fixtures/.

Tests never call the live API; they run against these recorded responses. Re-run this script
when you suspect Föli changed a response shape, then run the test suite.

    cd backend && .venv/bin/python scripts/fetch_fixtures.py

Samples are trimmed so the fixtures stay readable, but field names and structure are left
exactly as Föli sends them. Two fixtures (PENDING and NO_SIRI_DATA) cannot be recorded on
demand, so they are written from Föli's documentation and marked with a "_note" key.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

BASE = "https://data.foli.fi"
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
SAMPLE_ROUTE_ID = "1"  # line 1: airport - centre - harbour, two clear directions
SAMPLE_STOP_ID = "1"  # Turun satama (Silja), a busy terminus


def get(client: httpx.Client, path: str) -> Any:
    response = client.get(f"{BASE}{path}")
    response.raise_for_status()
    return response.json()


def write(name: str, data: Any) -> None:
    path = OUT / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(OUT.parent.parent)} ({path.stat().st_size} bytes)")


def pick_vehicles(vehicles: dict[str, Any], limit: int = 10) -> dict[str, Any]:
    """Keep a handful of vehicles that cover the interesting cases."""
    wanted: list[str] = []

    def add(predicate: Any) -> None:
        for key, v in vehicles.items():
            if key not in wanted and predicate(v):
                wanted.append(key)
                return

    add(lambda v: "latitude" not in v)  # no position at all
    add(lambda v: not v.get("monitored", True))  # not monitored
    add(lambda v: "delay" not in v)  # no delay information
    add(lambda v: str(v.get("delay", "")).startswith("-"))  # early
    add(lambda v: str(v.get("delay", "")).startswith("PT") and v.get("delay") != "PT0S")  # late
    add(lambda v: "delaysecs" not in v and "delay" in v)  # ISO delay only
    for key in vehicles:
        if len(wanted) >= limit:
            break
        if key not in wanted:
            wanted.append(key)

    trimmed = {}
    for key in wanted:
        v = dict(vehicles[key])
        if isinstance(v.get("onwardcalls"), list):
            v["onwardcalls"] = v["onwardcalls"][:2]
        trimmed[key] = v
    return trimmed


def trim_trips(trips: list[dict[str, Any]], per_shape: int = 6) -> list[dict[str, Any]]:
    """Keep a few trips of every (direction, shape) pair, preserving which shape is dominant."""
    counts = Counter((t["direction_id"], t["shape_id"]) for t in trips)
    kept: list[dict[str, Any]] = []
    seen: Counter[tuple[Any, Any]] = Counter()
    for trip in trips:
        key = (trip["direction_id"], trip["shape_id"])
        # Dominant shapes keep `per_shape` trips, rare variants keep one, so the most common
        # shape per direction is still the most common one in the fixture.
        limit = per_shape if counts[key] > 1 else 1
        if seen[key] < limit:
            kept.append(trip)
            seen[key] += 1
    return kept


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "foli-live-map fixture recorder (runs rarely, by hand)"}
    with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
        index = get(client, "/gtfs/")
        dataset = index["latest"]
        write("gtfs_index.json", index)

        # The short URL answers 302 with a small JSON body; record that too.
        redirect = client.get(f"{BASE}/gtfs/stops", follow_redirects=False)
        write(
            "gtfs_redirect_stops.json",
            {
                "status_code": redirect.status_code,
                "location": redirect.headers.get("location"),
                "body": redirect.json(),
            },
        )

        vm = get(client, "/siri/vm")
        vm["result"]["vehicles"] = pick_vehicles(vm["result"]["vehicles"])
        write("siri_vm.json", vm)

        routes = get(client, f"/gtfs/v0/{dataset}/routes")
        referenced = {v.get("__routeref") for v in vm["result"]["vehicles"].values()}
        referenced.add(SAMPLE_ROUTE_ID)
        routes = [r for i, r in enumerate(routes) if i < 20 or r["route_id"] in referenced]
        write("gtfs_routes.json", routes)

        sm = get(client, f"/siri/sm/{SAMPLE_STOP_ID}")
        sm["result"] = sm["result"][:4]
        write("siri_sm_stop.json", sm)

        stops = get(client, f"/gtfs/v0/{dataset}/stops")
        keep = set(list(stops)[:40]) | {SAMPLE_STOP_ID}
        write("gtfs_stops.json", {k: v for k, v in stops.items() if k in keep})

        trips = get(client, f"/gtfs/v0/{dataset}/trips/route/{SAMPLE_ROUTE_ID}")
        trips = trim_trips(trips)
        write(f"gtfs_trips_route_{SAMPLE_ROUTE_ID}.json", trips)

        shape_ids = sorted({t["shape_id"] for t in trips})
        for shape_id in shape_ids:
            points = get(client, f"/gtfs/v0/{dataset}/shapes/{shape_id}")
            # Every 10th point keeps the geometry recognisable at a fraction of the size.
            write(f"gtfs_shape_{shape_id}.json", points[::10] + points[-1:])

    # Documented special states. Their envelope matches the real OK response.
    write(
        "siri_vm_pending.json",
        {
            "_note": "Synthetic, from Föli docs: service starting, data expected in 5-30 s",
            "sys": "VM",
            "status": "PENDING",
            "servertime": vm["servertime"],
            "result": {},
        },
    )
    write(
        "siri_vm_no_siri_data.json",
        {
            "_note": "Synthetic, from Föli docs: Föli's backend has problems",
            "sys": "VM",
            "status": "NO_SIRI_DATA",
            "servertime": vm["servertime"],
            "result": {},
        },
    )


if __name__ == "__main__":
    main()
