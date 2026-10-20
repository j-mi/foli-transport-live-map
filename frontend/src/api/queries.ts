import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Favourites } from './types'

const HOUR = 60 * 60 * 1000

export const queryKeys = {
  lines: ['lines'] as const,
  stops: ['stops'] as const,
  lineShape: (routeId: string) => ['lineShape', routeId] as const,
  favourites: ['favourites'] as const,
  nearby: (lat: number, lon: number, radiusM: number) => ['nearby', lat, lon, radiusM] as const,
  departures: (stopId: string) => ['departures', stopId] as const,
}

// Static GTFS data changes at most a few times a week, so it is cached generously.
export function useLines() {
  return useQuery({ queryKey: queryKeys.lines, queryFn: api.lines, staleTime: HOUR })
}

export function useStops() {
  return useQuery({ queryKey: queryKeys.stops, queryFn: api.stops, staleTime: HOUR })
}

export function useLineShape(routeId: string | null) {
  return useQuery({
    queryKey: queryKeys.lineShape(routeId ?? ''),
    queryFn: () => api.lineShape(routeId!),
    enabled: routeId !== null,
    staleTime: Infinity, // shapes never change within a dataset
  })
}

export function useFavourites() {
  return useQuery({ queryKey: queryKeys.favourites, queryFn: api.favourites })
}

export function useNearbyStops(point: { lat: number; lon: number } | null, radiusM: number) {
  return useQuery({
    queryKey: queryKeys.nearby(point?.lat ?? 0, point?.lon ?? 0, radiusM),
    queryFn: () => api.nearbyStops(point!.lat, point!.lon, radiusM),
    enabled: point !== null,
  })
}

export function useDepartures(stopId: string | null) {
  return useQuery({
    queryKey: queryKeys.departures(stopId ?? ''),
    queryFn: () => api.departures(stopId!),
    enabled: stopId !== null,
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: 1,
  })
}

/**
 * Optimistic favourite toggles.
 *
 * The star flips immediately (we write the expected result into the query cache), the request
 * runs in the background, and on failure we restore the previous cache value. Finally we refetch
 * so the cache matches the server either way.
 */
function useOptimisticFavourites<V>(
  mutationFn: (variables: V) => Promise<unknown>,
  applyOptimistic: (current: Favourites, variables: V) => Favourites,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onMutate: async (variables: V) => {
      // Stop in-flight refetches from overwriting our optimistic value.
      await queryClient.cancelQueries({ queryKey: queryKeys.favourites })
      const previous = queryClient.getQueryData<Favourites>(queryKeys.favourites)
      if (previous) {
        queryClient.setQueryData(queryKeys.favourites, applyOptimistic(previous, variables))
      }
      return { previous }
    },
    onError: (_error, _variables, onMutateResult) => {
      if (onMutateResult?.previous) {
        queryClient.setQueryData(queryKeys.favourites, onMutateResult.previous)
      }
    },
    onSettled: () => invalidateFavourites(queryClient),
  })
}

function invalidateFavourites(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.favourites })
}

export interface ToggleStopVars {
  stop: { stop_id: string; name: string; lat: number; lon: number }
  favourite: boolean
}

export function useToggleFavouriteStop() {
  return useOptimisticFavourites<ToggleStopVars>(
    ({ stop, favourite }) =>
      favourite ? api.addFavouriteStop(stop.stop_id) : api.removeFavouriteStop(stop.stop_id),
    (current, { stop, favourite }) => ({
      ...current,
      stops: favourite
        ? current.stops.some((s) => s.stop_id === stop.stop_id)
          ? current.stops
          : [...current.stops, { ...stop, created_at: new Date().toISOString() }]
        : current.stops.filter((s) => s.stop_id !== stop.stop_id),
    }),
  )
}

export interface ToggleLineVars {
  line: { route_id: string; short_name: string }
  favourite: boolean
}

export function useToggleFavouriteLine() {
  return useOptimisticFavourites<ToggleLineVars>(
    ({ line, favourite }) =>
      favourite ? api.addFavouriteLine(line.route_id) : api.removeFavouriteLine(line.route_id),
    (current, { line, favourite }) => ({
      ...current,
      lines: favourite
        ? current.lines.some((l) => l.route_id === line.route_id)
          ? current.lines
          : [...current.lines, { ...line, created_at: new Date().toISOString() }]
        : current.lines.filter((l) => l.route_id !== line.route_id),
    }),
  )
}
