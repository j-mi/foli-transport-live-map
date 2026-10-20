import { Layer, Source } from '@vis.gl/react-maplibre'
import { memo } from 'react'
import type { FeatureCollection, Point } from 'geojson'
import type { FilterSpecification } from 'maplibre-gl'
import { FONT_BOLD, FONT_REGULAR, type MapColors } from '../mapStyle'

export const STOP_LAYER_IDS = {
  clusters: 'stop-clusters',
  clusterCount: 'stop-cluster-count',
  points: 'stop-points',
  labels: 'stop-labels',
} as const

interface Props {
  /** Already clustered by Supercluster (or raw stops when clustering is off). */
  data: FeatureCollection<Point>
  favouriteStopIds: string[]
  colors: MapColors
}

const IS_CLUSTER: FilterSpecification = ['has', 'point_count']
const IS_STOP: FilterSpecification = ['!', ['has', 'point_count']]

/**
 * Renders stops. Note the source has NO `cluster` option: the clustering was already done in
 * React by Supercluster (hooks/useStopClusters.ts); MapLibre just draws the result.
 */
export const StopsLayer = memo(function StopsLayer({ data, favouriteStopIds, colors }: Props) {
  return (
    <Source id="stops" type="geojson" data={data}>
      <Layer
        id={STOP_LAYER_IDS.clusters}
        type="circle"
        filter={IS_CLUSTER}
        paint={{
          'circle-color': colors.stopCluster,
          // Muted on purpose: stops are context, buses are the subject.
          'circle-opacity': 0.7,
          'circle-radius': ['step', ['get', 'point_count'], 10, 25, 13, 100, 17, 400, 22],
          'circle-stroke-color': colors.surface,
          'circle-stroke-width': 1.5,
        }}
      />
      <Layer
        id={STOP_LAYER_IDS.clusterCount}
        type="symbol"
        filter={IS_CLUSTER}
        layout={{
          'text-field': ['to-string', ['get', 'point_count_abbreviated']],
          'text-font': FONT_BOLD,
          'text-size': 11,
          'text-allow-overlap': true,
        }}
        paint={{ 'text-color': colors.stopClusterText, 'text-opacity': 0.9 }}
      />
      <Layer
        id={STOP_LAYER_IDS.points}
        type="circle"
        filter={IS_STOP}
        paint={{
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 3, 16, 6.5],
          'circle-color': [
            'case',
            ['in', ['get', 'stop_id'], ['literal', favouriteStopIds]],
            colors.favourite,
            colors.surface,
          ],
          'circle-stroke-color': colors.stop,
          'circle-stroke-width': 1.75,
        }}
      />
      <Layer
        id={STOP_LAYER_IDS.labels}
        type="symbol"
        minzoom={16}
        filter={IS_STOP}
        layout={{
          'text-field': ['get', 'name'],
          'text-font': FONT_REGULAR,
          'text-size': 12,
          'text-anchor': 'top',
          'text-offset': [0, 0.9],
          'text-optional': true,
        }}
        paint={{ 'text-color': colors.text, 'text-halo-color': colors.surface, 'text-halo-width': 1.5 }}
      />
    </Source>
  )
})
