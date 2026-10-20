import { Layer, Source } from '@vis.gl/react-maplibre'
import { useEffect, useRef, useState } from 'react'
import { useLineShape } from '../../api/queries'
import { usePrefersReducedMotion } from '../../state/uiState'
import { useCamera } from '../camera'
import { lineBounds } from '../geojson'
import type { MapColors } from '../mapStyle'

export const ROUTE_LAYER_IDS = { casing: 'route-casing', line: 'route-line' } as const

/**
 * The selected line, drawn thick and high-contrast with a thin casing underneath so it stays
 * legible on any basemap. Fits the map to the line once per selection and fades in.
 */
export function RouteHighlightLayer({ routeId, colors }: { routeId: string | null; colors: MapColors }) {
  const { data } = useLineShape(routeId)
  const camera = useCamera()
  const reducedMotion = usePrefersReducedMotion()
  const fittedFor = useRef<string | null>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!routeId || !data) {
      if (!routeId) fittedFor.current = null
      setVisible(false) // nothing drawn yet; the next line fades in from transparent
      return
    }
    if (fittedFor.current === routeId) return
    fittedFor.current = routeId
    const bounds = lineBounds(data)
    if (bounds) camera.fitBounds(bounds)
    // Start transparent, then switch to opaque on the next frame so MapLibre animates it.
    setVisible(false)
    const frame = requestAnimationFrame(() => setVisible(true))
    return () => cancelAnimationFrame(frame)
  }, [routeId, data, camera])

  if (!routeId || !data) return null
  const transition = { duration: reducedMotion ? 0 : 400, delay: 0 }
  const opacity = visible ? 1 : 0

  return (
    <Source id="route-highlight" type="geojson" data={data}>
      <Layer
        id={ROUTE_LAYER_IDS.casing}
        type="line"
        layout={{ 'line-join': 'round', 'line-cap': 'round' }}
        paint={{
          'line-color': colors.routeCasing,
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 7, 16, 13],
          'line-opacity': opacity,
          'line-opacity-transition': transition,
        }}
      />
      <Layer
        id={ROUTE_LAYER_IDS.line}
        type="line"
        layout={{ 'line-join': 'round', 'line-cap': 'round' }}
        paint={{
          'line-color': colors.route,
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 3.5, 16, 7.5],
          'line-opacity': opacity,
          'line-opacity-transition': transition,
        }}
      />
    </Source>
  )
}
