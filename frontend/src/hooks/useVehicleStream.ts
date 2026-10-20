/**
 * React access to the live vehicle feed (see realtime/vehicleStream.ts for the state machine).
 *
 * - `useVehicleStats(selector)` re-renders only when the selected value changes, and the stats
 *   themselves change at most once per second. A component that only needs `isStale` does not
 *   re-render when the vehicle count or data age ticks.
 * - `useVehicleSnapshots(listener)` delivers every snapshot WITHOUT a re-render. The vehicle
 *   map layer uses it to push positions straight into MapLibre.
 */
import { createContext, createElement, useContext, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import type { Snapshot } from '../api/types'
import { VehicleStreamClient, type StreamStats } from '../realtime/vehicleStream'

const VehicleStreamContext = createContext<VehicleStreamClient | null>(null)

export function VehicleStreamProvider({
  children,
  client: providedClient,
}: {
  children: ReactNode
  client?: VehicleStreamClient
}) {
  const [client] = useState(() => providedClient ?? new VehicleStreamClient())
  useEffect(() => {
    client.start()
    return () => client.stop()
  }, [client])
  return createElement(VehicleStreamContext.Provider, { value: client }, children)
}

export function useVehicleStreamClient(): VehicleStreamClient {
  const client = useContext(VehicleStreamContext)
  if (!client) throw new Error('useVehicleStreamClient must be used inside VehicleStreamProvider')
  return client
}

export function useVehicleStats<T>(selector: (stats: StreamStats) => T): T {
  const client = useVehicleStreamClient()
  return useSyncExternalStore(client.subscribeStats, () => selector(client.getStats()))
}

export function useVehicleSnapshots(listener: (snapshot: Snapshot) => void): void {
  const client = useVehicleStreamClient()
  // Keep the latest listener in a ref so callers can pass inline functions without
  // resubscribing on every render.
  const listenerRef = useRef(listener)
  useEffect(() => {
    listenerRef.current = listener
  })
  useEffect(() => client.subscribe((snapshot) => listenerRef.current(snapshot)), [client])
}
