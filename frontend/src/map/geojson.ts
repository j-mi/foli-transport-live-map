/**
 * Conversions from API objects to GeoJSON for MapLibre.
 *
 * GeoJSON positions are [longitude, latitude]. The API (like Föli) gives separate `lat` and
 * `lon` fields. `toPosition` is the one place where they are combined, and it is unit tested,
 * because swapping them silently moves Turku into the Indian Ocean.
 */
import type { BBox, Feature, FeatureCollection, LineString, Point, Position } from 'geojson'
import type { Vehicle } from '../api/types'

export function toPosition(lat: number, lon: number): [number, number] {
  return [lon, lat]
}

export interface VehicleFeatureProps {
  id: string
  line: string
  /** Empty string when the line is not in GTFS; MapLibre expressions handle '' more simply. */
  route_id: string
  known: boolean
  delay_s: number | null
}

export type VehicleCollection = FeatureCollection<Point, VehicleFeatureProps>

export const EMPTY_VEHICLES: VehicleCollection = { type: 'FeatureCollection', features: [] }

export function vehicleToFeature(vehicle: Vehicle): Feature<Point, VehicleFeatureProps> {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: toPosition(vehicle.lat, vehicle.lon) },
    properties: {
      id: vehicle.id,
      line: vehicle.line ?? '?',
      route_id: vehicle.route_id ?? '',
      known: vehicle.route_id !== null,
      delay_s: vehicle.delay_s,
    },
  }
}

/**
 * Split vehicles into the selected line's buses and everyone else.
 *
 * The selected line goes into its own unclustered source drawn on top, so its buses are always
 * individually visible and emphasised even when the others are clustered and dimmed.
 */
export function partitionVehicles(
  vehicles: Vehicle[],
  selectedRouteId: string | null,
): { others: VehicleCollection; selected: VehicleCollection } {
  const others: Feature<Point, VehicleFeatureProps>[] = []
  const selected: Feature<Point, VehicleFeatureProps>[] = []
  for (const vehicle of vehicles) {
    const feature = vehicleToFeature(vehicle)
    if (selectedRouteId !== null && vehicle.route_id === selectedRouteId) selected.push(feature)
    else others.push(feature)
  }
  return {
    others: { type: 'FeatureCollection', features: others },
    selected: { type: 'FeatureCollection', features: selected },
  }
}

/** [west, south, east, north] covering every coordinate of the given lines, or null if empty. */
export function lineBounds(collection: FeatureCollection<LineString>): BBox | null {
  let west = Infinity
  let south = Infinity
  let east = -Infinity
  let north = -Infinity
  for (const feature of collection.features) {
    for (const [lon, lat] of feature.geometry.coordinates as Position[]) {
      if (lon === undefined || lat === undefined) continue
      west = Math.min(west, lon)
      east = Math.max(east, lon)
      south = Math.min(south, lat)
      north = Math.max(north, lat)
    }
  }
  return Number.isFinite(west) ? [west, south, east, north] : null
}

/** Grow a bbox by a fraction of its size on each side (so points near the edge don't pop in). */
export function padBounds(bbox: BBox, fraction: number): BBox {
  const [west, south, east, north] = bbox as [number, number, number, number]
  const dx = (east - west) * fraction
  const dy = (north - south) * fraction
  return [west - dx, Math.max(-90, south - dy), east + dx, Math.min(90, north + dy)]
}
