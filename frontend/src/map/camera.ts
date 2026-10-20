import { useMap } from '@vis.gl/react-maplibre'
import { useMemo } from 'react'
import type { BBox } from 'geojson'
import { usePrefersReducedMotion } from '../state/uiState'

export const MAP_ID = 'main'

/**
 * Camera moves triggered by the user (fly to a stop, fit a line). With `prefers-reduced-motion`
 * they jump instead of animating.
 */
export function useCamera() {
  const maps = useMap()
  const map = maps[MAP_ID]
  const reducedMotion = usePrefersReducedMotion()

  return useMemo(() => {
    const duration = (ms: number) => (reducedMotion ? 0 : ms)
    return {
      flyTo(lon: number, lat: number, zoom = 16) {
        map?.flyTo({
          center: [lon, lat],
          zoom: Math.max(zoom, map.getZoom()),
          duration: duration(1200),
          essential: false,
        })
      },
      easeTo(lon: number, lat: number, zoom: number) {
        map?.easeTo({ center: [lon, lat], zoom, duration: duration(500) })
      },
      fitBounds(bbox: BBox) {
        const [west, south, east, north] = bbox as [number, number, number, number]
        map?.fitBounds(
          [
            [west, south],
            [east, north],
          ],
          { padding: 60, maxZoom: 15, duration: duration(900) },
        )
      },
    }
  }, [map, reducedMotion])
}
