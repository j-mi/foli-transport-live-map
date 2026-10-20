// Mirrors backend/app/schemas.py. Keep the two in sync when the API changes.
import type { FeatureCollection, LineString, Point } from 'geojson'

export type UpstreamStatus = 'OK' | 'PENDING' | 'NO_DATA' | 'DOWN'

export interface Vehicle {
  id: string
  line: string | null
  route_id: string | null
  direction: string | null
  destination: string | null
  lat: number
  lon: number
  /** Seconds behind schedule; negative means early. */
  delay_s: number | null
  next_stop: string | null
  recorded_at: string
  monitored: boolean
}

export interface Snapshot {
  seq: number
  /** When the backend fetched this data from Föli. Null before the first success. */
  fetched_at: string | null
  upstream_status: UpstreamStatus
  vehicles: Vehicle[]
}

/** Payload of the SSE `status` event. */
export interface StatusEvent {
  upstream_status: UpstreamStatus
  fetched_at: string | null
}

export interface Line {
  route_id: string
  short_name: string
  long_name: string
  /** Hex colour without '#'. */
  color: string | null
  text_color: string | null
}

export interface LinesResponse {
  dataset_id: string
  lines: Line[]
}

export interface StopProps {
  stop_id: string
  name: string
}

export type StopCollection = FeatureCollection<Point, StopProps>

export interface LineShapeProps {
  route_id: string
  short_name: string
  direction_id: string
  shape_id: string
  headsign: string | null
  trip_count: number
  color: string | null
}

export type LineShapeCollection = FeatureCollection<LineString, LineShapeProps>

export interface FavouriteStop {
  stop_id: string
  name: string
  lat: number
  lon: number
  created_at: string
}

export interface FavouriteLine {
  route_id: string
  short_name: string
  created_at: string
}

export interface Favourites {
  stops: FavouriteStop[]
  lines: FavouriteLine[]
}

export interface NearbyStop {
  stop_id: string
  name: string
  lat: number
  lon: number
  distance_m: number
}

export interface NearbyStopsResponse {
  lat: number
  lon: number
  radius_m: number
  stops: NearbyStop[]
}

export interface Departure {
  line: string | null
  route_id: string | null
  destination: string | null
  aimed_departure: string | null
  expected_departure: string | null
  monitored: boolean
  vehicle_id: string | null
}

export interface DeparturesResponse {
  stop_id: string
  fetched_at: string
  departures: Departure[]
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown }
}
