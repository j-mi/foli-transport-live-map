import { renderHook } from '@testing-library/react'
import type { BBox } from 'geojson'
import type { PointFeature } from 'supercluster'
import { describe, expect, it } from 'vitest'
import type { StopProps } from '../api/types'
import { useStopClusters } from './useStopClusters'

function stop(id: string, lat: number, lon: number): PointFeature<StopProps> {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [lon, lat] },
    properties: { stop_id: id, name: `Stop ${id}` },
  }
}

// Three stops ~50-100 m apart in central Turku, and one in Naantali ~15 km away.
const STOPS = [
  stop('a', 60.4518, 22.2666),
  stop('b', 60.4522, 22.2672),
  stop('c', 60.4513, 22.2660),
  stop('far', 60.4675, 22.0244),
]
const REGION: BBox = [21.5, 60.0, 23.0, 61.0]

const isCluster = (f: { properties: object }) => 'cluster' in f.properties

describe('useStopClusters', () => {
  it('groups nearby stops at low zoom', () => {
    const { result } = renderHook(() => useStopClusters(STOPS, REGION, 9))
    const clusters = result.current.clusters.filter(isCluster)
    expect(clusters).toHaveLength(1)
    expect(clusters[0]!.properties).toMatchObject({ point_count: 3 })
    // The Naantali stop is far enough away to stay on its own.
    expect(result.current.clusters).toHaveLength(2)
  })

  it('returns individual stops at high zoom', () => {
    const { result } = renderHook(() => useStopClusters(STOPS, REGION, 18))
    expect(result.current.clusters.filter(isCluster)).toHaveLength(0)
    expect(result.current.clusters).toHaveLength(4)
  })

  it('only returns what is inside the bounding box', () => {
    const naantali: BBox = [21.9, 60.4, 22.1, 60.5]
    const { result } = renderHook(() => useStopClusters(STOPS, naantali, 18))
    expect(result.current.clusters.map((f) => (f.properties as StopProps).stop_id)).toEqual(['far'])
  })

  it('tells how far to zoom for a cluster to split', () => {
    const { result } = renderHook(() => useStopClusters(STOPS, REGION, 9))
    const cluster = result.current.clusters.find(isCluster)!
    const zoom = result.current.index.getClusterExpansionZoom(
      (cluster.properties as { cluster_id: number }).cluster_id,
    )
    expect(zoom).toBeGreaterThan(9)
  })

  it('returns nothing before the map has reported its viewport', () => {
    const { result } = renderHook(() => useStopClusters(STOPS, null, 12))
    expect(result.current.clusters).toEqual([])
  })
})
