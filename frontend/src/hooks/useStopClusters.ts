/**
 * Stop clustering with Supercluster, done explicitly in React (vehicles use MapLibre's built-in
 * clustering instead; see map/layers/VehiclesLayer.tsx for the comparison).
 *
 * How Supercluster works, in plain words:
 *
 * 1. Load: all ~3 600 stops go into a KD-tree, a spatial index that answers "which points are
 *    near here?" quickly.
 * 2. Precompute, from the most detailed zoom (`maxZoom`) up to zoom 0: take a point that is not
 *    yet in a cluster, find every neighbour within `radius` pixels (converted to map units for
 *    that zoom), and merge them into one cluster placed at their weighted centre, remembering
 *    `point_count`. Then cluster those clusters again for the next zoom level up. Each level is
 *    built from the one below it, so the whole pyramid is computed once.
 * 3. Query: at runtime we only ask "which clusters lie inside this bounding box at this zoom?".
 *    The answer is a fast index lookup because everything was precomputed in step 2.
 *
 * The expensive step (load) runs once per GTFS dataset; the cheap step (query) runs after every
 * pan or zoom. We query on `moveend`, not `move`, so it runs once per gesture instead of 60
 * times per second.
 */
import { useMemo } from 'react'
import Supercluster from 'supercluster'
import type { ClusterFeature, PointFeature } from 'supercluster'
import type { BBox } from 'geojson'
import type { StopProps } from '../api/types'

export const STOP_CLUSTER_RADIUS_PX = 50
// From zoom 16, where stop names are drawn, every stop is shown on its own. (At 16, platform pairs
// a few metres apart would otherwise still merge into "2" clusters.)
export const STOP_CLUSTER_MAX_ZOOM = 15

export type StopClusterFeature = ClusterFeature<Record<string, never>> | PointFeature<StopProps>

export function buildStopIndex(stops: PointFeature<StopProps>[]): Supercluster<StopProps> {
  const index = new Supercluster<StopProps>({
    radius: STOP_CLUSTER_RADIUS_PX,
    maxZoom: STOP_CLUSTER_MAX_ZOOM,
  })
  index.load(stops)
  return index
}

export function useStopClusters(
  stops: PointFeature<StopProps>[],
  bbox: BBox | null, // [west, south, east, north]
  zoom: number,
) {
  // Rebuild the index only when the stop data changes (once per GTFS dataset).
  const index = useMemo(() => buildStopIndex(stops), [stops])

  // Cheap query on every pan or zoom. Supercluster's zoom levels are integers.
  const clusters = useMemo(
    () => (bbox ? (index.getClusters(bbox, Math.floor(zoom)) as StopClusterFeature[]) : []),
    [index, bbox, zoom],
  )

  return { clusters, index }
}
