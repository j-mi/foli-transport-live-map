/**
 * Live buses.
 *
 * Clustering here is MapLibre's built-in GeoJSON clustering (`cluster: true`). It runs
 * Supercluster inside a web worker and draws with WebGL, so for points that move every few
 * seconds we only call `source.setData()` and never re-render React. Compare with stops, which
 * are clustered explicitly in React (hooks/useStopClusters.ts).
 *
 * Data flow: VehicleStreamClient -> useVehicleSnapshots(listener) -> source.setData(geojson).
 * React state is never involved, so a snapshot every 5 s costs no React renders at all.
 */
import { Layer, Source, useMap } from '@vis.gl/react-maplibre'
import type {
  CircleLayerSpecification,
  ExpressionSpecification,
  FilterSpecification,
  GeoJSONSource,
  MapSourceDataEvent,
  SymbolLayerSpecification,
} from 'maplibre-gl'
import { memo, useCallback, useEffect, useRef } from 'react'
import { useVehicleSnapshots, useVehicleStats, useVehicleStreamClient } from '../../hooks/useVehicleStream'
import { MAP_ID } from '../camera'
import { EMPTY_VEHICLES, partitionVehicles } from '../geojson'
import { FONT_BOLD, type MapColors } from '../mapStyle'

// Clustered and unclustered variants get different ids: <Source> cannot switch `cluster` on an
// existing source, and reusing one id across a remount would let the old instance's cleanup
// delete the new source.
export const VEHICLE_SOURCES = {
  clustered: 'vehicles-clustered',
  plain: 'vehicles-plain',
  selected: 'vehicles-selected',
} as const

export const VEHICLE_LAYER_IDS = {
  clusters: 'vehicles-clustered-clusters',
  clusterCount: 'vehicles-clustered-count',
  clusteredPoints: 'vehicles-clustered-points',
  clusteredLabels: 'vehicles-clustered-labels',
  plainPoints: 'vehicles-plain-points',
  plainLabels: 'vehicles-plain-labels',
  selectedPoints: 'vehicles-selected-points',
  selectedLabels: 'vehicles-selected-labels',
} as const

const ALL_SOURCES: string[] = Object.values(VEHICLE_SOURCES)

interface Props {
  clustered: boolean
  selectedRouteId: string | null
  colors: MapColors
}

export const VehiclesLayer = memo(function VehiclesLayer({ clustered, selectedRouteId, colors }: Props) {
  const map = useMap()[MAP_ID]
  const client = useVehicleStreamClient()
  // The only React state this layer reads: flips at most when data becomes stale or fresh.
  const isStale = useVehicleStats((stats) => stats.isStale)

  const selectedRef = useRef(selectedRouteId)
  const appliedSources = useRef(new Map<string, unknown>())
  const mainSourceId = clustered ? VEHICLE_SOURCES.clustered : VEHICLE_SOURCES.plain

  const pushToMap = useCallback(() => {
    const maplibre = map?.getMap()
    const snapshot = client.latest
    if (!maplibre || !snapshot) return
    const { others, selected } = partitionVehicles(snapshot.vehicles, selectedRef.current)
    const targets: [string, typeof others][] = [
      [mainSourceId, others],
      [VEHICLE_SOURCES.selected, selected],
    ]
    for (const [id, data] of targets) {
      const source = maplibre.getSource<GeoJSONSource>(id)
      if (source) {
        source.setData(data)
        appliedSources.current.set(id, source)
      }
    }
  }, [map, client, mainSourceId])

  // Every snapshot goes straight into MapLibre.
  useVehicleSnapshots(pushToMap)

  // Re-partition immediately when the selected line or the clustering mode changes.
  useEffect(() => {
    selectedRef.current = selectedRouteId
    pushToMap()
  }, [selectedRouteId, pushToMap])

  // When a source object is (re)created, e.g. after switching the basemap between light and
  // dark, <Source> re-adds it with its static empty `data`. Detect that and push again.
  useEffect(() => {
    const maplibre = map?.getMap()
    if (!maplibre) return
    const onSourceData = (event: MapSourceDataEvent) => {
      const id = event.sourceId
      if (id && ALL_SOURCES.includes(id) && maplibre.getSource(id) !== appliedSources.current.get(id)) {
        pushToMap()
      }
    }
    maplibre.on('sourcedata', onSourceData)
    return () => {
      maplibre.off('sourcedata', onSourceData)
    }
  }, [map, pushToMap])

  const dimmed = selectedRouteId !== null
  // Buses on lines missing from GTFS are drawn grey; everything is grey when data is stale.
  const fill: string | ExpressionSpecification = isStale
    ? colors.stale
    : ['case', ['get', 'known'], colors.vehicle, colors.vehicleUnknown]
  const opacity = dimmed ? 0.35 : 1
  const pointPaint: CircleLayerSpecification['paint'] = {
    'circle-color': fill,
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 5, 12, 9.5, 14, 11, 17, 13],
    'circle-stroke-color': colors.vehicleStroke,
    'circle-stroke-width': 1.5,
    'circle-opacity': opacity,
    'circle-stroke-opacity': opacity,
  }
  const labelLayout: SymbolLayerSpecification['layout'] = {
    'text-field': ['get', 'line'],
    'text-font': FONT_BOLD,
    'text-size': ['interpolate', ['linear'], ['zoom'], 12, 9.5, 16, 11.5],
    'text-allow-overlap': true,
    'text-ignore-placement': true,
  }
  const notCluster: FilterSpecification = ['!', ['has', 'point_count']]

  return (
    <>
      {clustered ? (
        // Distinct keys make React remount instead of reusing one <Source> with a new id.
        <Source
          key={VEHICLE_SOURCES.clustered}
          id={VEHICLE_SOURCES.clustered}
          type="geojson"
          data={EMPTY_VEHICLES}
          cluster
          clusterRadius={40}
          clusterMaxZoom={14}
        >
          <Layer
            id={VEHICLE_LAYER_IDS.clusters}
            type="circle"
            filter={['has', 'point_count']}
            paint={{
              'circle-color': isStale ? colors.stale : colors.vehicle,
              'circle-radius': ['step', ['get', 'point_count'], 14, 10, 18, 30, 23],
              'circle-stroke-color': colors.vehicleStroke,
              'circle-stroke-width': 2,
              'circle-opacity': opacity,
              'circle-stroke-opacity': opacity,
            }}
          />
          <Layer
            id={VEHICLE_LAYER_IDS.clusterCount}
            type="symbol"
            filter={['has', 'point_count']}
            layout={{
              'text-field': ['to-string', ['get', 'point_count_abbreviated']],
              'text-font': FONT_BOLD,
              'text-size': 12,
              'text-allow-overlap': true,
            }}
            paint={{ 'text-color': colors.vehicleText, 'text-opacity': opacity }}
          />
          <Layer id={VEHICLE_LAYER_IDS.clusteredPoints} type="circle" filter={notCluster} paint={pointPaint} />
          <Layer
            id={VEHICLE_LAYER_IDS.clusteredLabels}
            type="symbol"
            minzoom={12}
            filter={notCluster}
            layout={labelLayout}
            paint={{ 'text-color': colors.vehicleText, 'text-opacity': opacity }}
          />
        </Source>
      ) : (
        <Source key={VEHICLE_SOURCES.plain} id={VEHICLE_SOURCES.plain} type="geojson" data={EMPTY_VEHICLES}>
          <Layer id={VEHICLE_LAYER_IDS.plainPoints} type="circle" paint={pointPaint} />
          <Layer
            id={VEHICLE_LAYER_IDS.plainLabels}
            type="symbol"
            minzoom={12}
            layout={labelLayout}
            paint={{ 'text-color': colors.vehicleText, 'text-opacity': opacity }}
          />
        </Source>
      )}

      {/* The selected line's buses: never clustered, drawn on top, high contrast. */}
      <Source id={VEHICLE_SOURCES.selected} type="geojson" data={EMPTY_VEHICLES}>
        <Layer
          id={VEHICLE_LAYER_IDS.selectedPoints}
          type="circle"
          paint={{
            'circle-color': isStale ? colors.stale : colors.route,
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 8, 13, 11, 17, 14],
            'circle-stroke-color': colors.routeCasing,
            'circle-stroke-width': 2.5,
          }}
        />
        <Layer
          id={VEHICLE_LAYER_IDS.selectedLabels}
          type="symbol"
          layout={{ ...labelLayout, 'text-size': ['interpolate', ['linear'], ['zoom'], 10, 10, 16, 12] }}
          paint={{ 'text-color': colors.routeText }}
        />
      </Source>
    </>
  )
})
