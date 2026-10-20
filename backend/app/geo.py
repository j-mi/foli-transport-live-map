"""The single place where Föli's separate lat/lon values become GeoJSON coordinates.

GeoJSON (RFC 7946) orders positions as [longitude, latitude]. Föli, like most humans, says
"lat, lon". Swapping them is the classic GIS bug: Turku (60.45 N, 22.27 E) silently becomes
a point in the Indian Ocean. Every conversion goes through `lonlat()` so it is tested once.

All coordinates are WGS 84 (EPSG:4326), which is what both Föli GTFS and SIRI use.
"""

from typing import Any


def lonlat(lat: float, lon: float) -> list[float]:
    """Return a GeoJSON position. Note the argument order (lat, lon) vs result order [lon, lat]."""
    return [lon, lat]


def point_feature(lat: float, lon: float, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": lonlat(lat, lon)},
        "properties": properties,
    }


def line_feature(points: list[tuple[float, float]], properties: dict[str, Any]) -> dict[str, Any]:
    """`points` is a list of (lat, lon) tuples."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [lonlat(lat, lon) for lat, lon in points],
        },
        "properties": properties,
    }


def feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}
