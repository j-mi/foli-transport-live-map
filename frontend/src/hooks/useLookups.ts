import { useMemo } from 'react'
import { useFavourites, useLines, useStops } from '../api/queries'
import type { Line } from '../api/types'

export interface StopInfo {
  stop_id: string
  name: string
  lat: number
  lon: number
}

/** Stops by id, derived once from the GeoJSON returned by /stops. */
export function useStopLookup(): Map<string, StopInfo> {
  const { data } = useStops()
  return useMemo(() => {
    const lookup = new Map<string, StopInfo>()
    for (const feature of data?.features ?? []) {
      const [lon, lat] = feature.geometry.coordinates as [number, number]
      lookup.set(feature.properties.stop_id, { ...feature.properties, lat, lon })
    }
    return lookup
  }, [data])
}

export function useLineLookup(): Map<string, Line> {
  const { data } = useLines()
  return useMemo(() => new Map((data?.lines ?? []).map((line) => [line.route_id, line])), [data])
}

export function useFavouriteIds(): { stops: Set<string>; lines: Set<string> } {
  const { data } = useFavourites()
  return useMemo(
    () => ({
      stops: new Set((data?.stops ?? []).map((s) => s.stop_id)),
      lines: new Set((data?.lines ?? []).map((l) => l.route_id)),
    }),
    [data],
  )
}
