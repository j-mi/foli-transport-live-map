import {
  Map,
  Marker,
  NavigationControl,
  ScaleControl,
  type MapLayerMouseEvent,
  type MapLayerTouchEvent,
} from '@vis.gl/react-maplibre'
import type { BBox, FeatureCollection, Point } from 'geojson'
import type { GeoJSONSource, MapLibreEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import './maplibreWorker'
import { useCallback, useMemo, useRef, useState } from 'react'
import type { PointFeature } from 'supercluster'
import { useStops } from '../api/queries'
import type { StopProps } from '../api/types'
import { useFavouriteIds } from '../hooks/useLookups'
import { useStopClusters } from '../hooks/useStopClusters'
import { useResolvedTheme, useUiDispatch, useUiState } from '../state/uiState'
import { MAP_ID, useCamera } from './camera'
import { padBounds } from './geojson'
import { RouteHighlightLayer } from './layers/RouteHighlightLayer'
import { STOP_LAYER_IDS, StopsLayer } from './layers/StopsLayer'
import { VEHICLE_LAYER_IDS, VEHICLE_SOURCES, VehiclesLayer } from './layers/VehiclesLayer'
import { FOLI_ATTRIBUTION, TURKU_VIEW, mapColors, mapStyleUrl } from './mapStyle'
import { StopPopup } from './popups/StopPopup'
import { VehiclePopup } from './popups/VehiclePopup'

const NO_STOPS: PointFeature<StopProps>[] = []
const EMPTY_COLLECTION: FeatureCollection<Point> = { type: 'FeatureCollection', features: [] }
const LONG_PRESS_MS = 600

// Topmost first is decided by MapLibre's draw order; this list only says what is clickable.
const INTERACTIVE_LAYERS = [
  VEHICLE_LAYER_IDS.selectedPoints,
  VEHICLE_LAYER_IDS.clusters,
  VEHICLE_LAYER_IDS.clusteredPoints,
  VEHICLE_LAYER_IDS.plainPoints,
  STOP_LAYER_IDS.clusters,
  STOP_LAYER_IDS.points,
]
const VEHICLE_POINT_LAYERS = new Set<string>([
  VEHICLE_LAYER_IDS.selectedPoints,
  VEHICLE_LAYER_IDS.clusteredPoints,
  VEHICLE_LAYER_IDS.plainPoints,
])

interface Viewport {
  bbox: BBox
  zoom: number
}

export function MapView() {
  const ui = useUiState()
  const dispatch = useUiDispatch()
  const theme = useResolvedTheme()
  const colors = mapColors[theme]
  const camera = useCamera()

  const stops = useStops()
  const stopFeatures = (stops.data?.features as PointFeature<StopProps>[] | undefined) ?? NO_STOPS
  const favouriteIds = useFavouriteIds()
  const favouriteStopIds = useMemo(() => [...favouriteIds.stops], [favouriteIds])

  // Bounding box and zoom, updated once per gesture (moveend), drive the Supercluster query.
  const [viewport, setViewport] = useState<Viewport | null>(null)
  const { clusters, index } = useStopClusters(stopFeatures, viewport?.bbox ?? null, viewport?.zoom ?? 0)
  const stopData = useMemo<FeatureCollection<Point>>(
    () =>
      ui.layers.clusterStops
        ? { type: 'FeatureCollection', features: clusters }
        : (stops.data ?? EMPTY_COLLECTION),
    [ui.layers.clusterStops, clusters, stops.data],
  )

  const updateViewport = useCallback((event: MapLibreEvent) => {
    const map = event.target
    const bounds = map.getBounds()
    setViewport({
      // Pad so stops just outside the screen are ready before they scroll into view.
      bbox: padBounds([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()], 0.15),
      zoom: map.getZoom(),
    })
  }, [])

  const [cursor, setCursor] = useState<string>('')

  const onClick = useCallback(
    async (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0]
      if (!feature) return
      const layerId = feature.layer.id
      const [lon, lat] = (feature.geometry as Point).coordinates as [number, number]
      const props = feature.properties

      if (layerId === STOP_LAYER_IDS.clusters) {
        // Zoom to where this Supercluster cluster splits into smaller ones.
        const zoom = index.getClusterExpansionZoom(Number(props.cluster_id))
        camera.easeTo(lon, lat, Math.min(zoom, 20))
      } else if (layerId === STOP_LAYER_IDS.points) {
        dispatch({ type: 'openStop', stopId: String(props.stop_id) })
      } else if (layerId === VEHICLE_LAYER_IDS.clusters) {
        // Same idea, but MapLibre owns this index (in a web worker), so the answer is async. It
        // can fail if a new snapshot replaced the clusters meanwhile; then the click does nothing.
        const source = event.target.getSource<GeoJSONSource>(VEHICLE_SOURCES.clustered)
        const zoom = await source?.getClusterExpansionZoom(Number(props.cluster_id)).catch(() => undefined)
        if (zoom !== undefined) camera.easeTo(lon, lat, zoom)
      } else if (VEHICLE_POINT_LAYERS.has(layerId)) {
        dispatch({ type: 'openVehicle', vehicleId: String(props.id) })
      }
    },
    [index, camera, dispatch],
  )

  // Right-click (desktop) or long-press (touch): "stops near here".
  const findNearby = useCallback(
    (lat: number, lon: number) => dispatch({ type: 'setNearbyPoint', point: { lat, lon } }),
    [dispatch],
  )
  const longPress = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cancelLongPress = useCallback(() => {
    if (longPress.current) clearTimeout(longPress.current)
    longPress.current = null
  }, [])
  const onTouchStart = useCallback(
    (event: MapLayerTouchEvent) => {
      cancelLongPress()
      if (event.points.length !== 1) return // pinch, not a press
      const { lat, lng } = event.lngLat
      longPress.current = setTimeout(() => findNearby(lat, lng), LONG_PRESS_MS)
    },
    [cancelLongPress, findNearby],
  )

  return (
    <Map
      id={MAP_ID}
      initialViewState={TURKU_VIEW}
      mapStyle={mapStyleUrl(theme)}
      style={{ width: '100%', height: '100%' }}
      attributionControl={{ compact: false, customAttribution: FOLI_ATTRIBUTION }}
      dragRotate={false}
      pitchWithRotate={false}
      touchPitch={false}
      minZoom={7}
      interactiveLayerIds={INTERACTIVE_LAYERS}
      cursor={cursor}
      onMouseEnter={() => setCursor('pointer')}
      onMouseLeave={() => setCursor('')}
      onClick={onClick}
      onContextMenu={(event) => {
        event.preventDefault()
        findNearby(event.lngLat.lat, event.lngLat.lng)
      }}
      onTouchStart={onTouchStart}
      onTouchEnd={cancelLongPress}
      onTouchMove={cancelLongPress}
      onLoad={(event) => {
        // Development only (removed from production builds): reach the map from devtools.
        if (import.meta.env.DEV) Object.assign(window, { __foliMap: event.target })
        updateViewport(event)
      }}
      onMoveEnd={updateViewport}
    >
      <NavigationControl position="top-right" showCompass={false} />
      <ScaleControl position="bottom-right" />

      <RouteHighlightLayer routeId={ui.selectedRouteId} colors={colors} />
      {ui.layers.stops && (
        <StopsLayer data={stopData} favouriteStopIds={favouriteStopIds} colors={colors} />
      )}
      {ui.layers.vehicles && (
        <VehiclesLayer
          clustered={ui.layers.clusterVehicles}
          selectedRouteId={ui.selectedRouteId}
          colors={colors}
        />
      )}

      {ui.nearbyPoint && (
        <Marker longitude={ui.nearbyPoint.lon} latitude={ui.nearbyPoint.lat} anchor="center">
          <span className="nearby-marker" aria-label="Selected point" role="img" />
        </Marker>
      )}
      {ui.openStopId && <StopPopup key={ui.openStopId} stopId={ui.openStopId} />}
      {ui.openVehicleId && <VehiclePopup key={ui.openVehicleId} vehicleId={ui.openVehicleId} />}
    </Map>
  )
}
