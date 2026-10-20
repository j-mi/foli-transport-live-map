/**
 * Live vehicle feed: Server-Sent Events with a REST polling fallback.
 *
 * This class is deliberately framework-free (no React) so the state machine can be unit tested
 * with a fake EventSource. `hooks/useVehicleStream.ts` wraps it for React.
 *
 * Transport states
 *
 *   connecting ──open──▶ live ──error──▶ reconnecting ──open──▶ live
 *                                            │
 *                         3 errors in a row  ▼
 *                         polling ◀──poll ok── (poll /vehicles every 5 s, retry SSE every 60 s)
 *                            │
 *                            └── poll fails ──▶ reconnecting (until a poll or SSE succeeds)
 *
 * Watchdog: a connection can die without the browser noticing (a proxy or NAT drops it, the
 * laptop sleeps, a dev proxy keeps the socket half-open). EventSource then waits forever. The
 * server sends a `heartbeat` event every 15 s, so 35 s of complete silence means the stream is
 * dead: we close it and treat it like any other error.
 *
 * "stale" is not a transport state but an overlay: whatever the transport, data older than 20 s
 * is stale. A connection can be "live" and still carry stale data (e.g. Föli is down and the
 * backend keeps re-sending the last known positions).
 *
 * Performance: snapshots are NOT put into React state. Listeners receive them directly (the map
 * layer writes them straight into MapLibre). Only small derived stats are published, and at most
 * once per second.
 */
import type { Snapshot, StatusEvent, UpstreamStatus } from '../api/types'

export type Transport = 'connecting' | 'live' | 'reconnecting' | 'polling'
export type ConnectionState = Transport | 'stale'

export interface StreamStats {
  connection: ConnectionState
  transport: Transport
  isStale: boolean
  vehicleCount: number
  fetchedAt: string | null
  /** Whole seconds since the backend fetched the data from Föli. */
  ageSeconds: number | null
  upstreamStatus: UpstreamStatus | null
}

export const STALE_AFTER_MS = 20_000
export const POLL_INTERVAL_MS = 5_000
export const SSE_RETRY_MS = 60_000
export const MAX_SSE_ERRORS = 3
/** Two missed 15 s heartbeats plus margin. */
export const SSE_SILENCE_MS = 35_000
const STATS_INTERVAL_MS = 1_000

/** The subset of the browser EventSource we use; lets tests pass a fake. */
export interface EventSourceLike {
  readonly readyState: number
  addEventListener(type: string, listener: (event: MessageEvent) => void): void
  close(): void
}

export interface VehicleStreamOptions {
  streamUrl?: string
  createEventSource?: (url: string) => EventSourceLike
  fetchSnapshot?: () => Promise<Snapshot>
  now?: () => number
}

const EVENT_SOURCE_CLOSED = 2

type SnapshotListener = (snapshot: Snapshot) => void

export class VehicleStreamClient {
  latest: Snapshot | null = null

  private readonly streamUrl: string
  private readonly createEventSource: (url: string) => EventSourceLike
  private readonly fetchSnapshot: () => Promise<Snapshot>
  private readonly now: () => number

  private running = false
  private transport: Transport = 'connecting'
  private upstreamStatus: UpstreamStatus | null = null
  private eventSource: EventSourceLike | null = null
  private sseErrors = 0
  private lastMessageAt = 0
  private polling = false
  private lastPollFailed = false

  private pollTimer: ReturnType<typeof setTimeout> | null = null
  private sseRetryTimer: ReturnType<typeof setTimeout> | null = null
  private statsTimer: ReturnType<typeof setInterval> | null = null

  private readonly snapshotListeners = new Set<SnapshotListener>()
  private readonly statsListeners = new Set<() => void>()
  private stats: StreamStats

  constructor(options: VehicleStreamOptions = {}) {
    this.streamUrl = options.streamUrl ?? '/api/v1/vehicles/stream'
    this.createEventSource = options.createEventSource ?? ((url) => new EventSource(url))
    this.fetchSnapshot = options.fetchSnapshot ?? defaultFetchSnapshot
    this.now = options.now ?? Date.now
    this.stats = this.computeStats()
  }

  // -- Lifecycle ----------------------------------------------------------------------------

  start(): void {
    if (this.running) return
    this.running = true
    this.setTransport('connecting')
    // 1. Immediate first paint from the REST snapshot while SSE connects.
    void this.loadInitialSnapshot()
    // 2. Then live updates.
    this.openEventSource()
    this.statsTimer = setInterval(() => {
      this.checkSilence()
      this.refreshStats()
    }, STATS_INTERVAL_MS)
  }

  stop(): void {
    this.running = false
    this.closeEventSource()
    this.stopPolling()
    if (this.sseRetryTimer) clearTimeout(this.sseRetryTimer)
    if (this.statsTimer) clearInterval(this.statsTimer)
    this.sseRetryTimer = null
    this.statsTimer = null
  }

  // -- Subscriptions ------------------------------------------------------------------------

  /** Called with every new snapshot. Returns an unsubscribe function. */
  subscribe(listener: SnapshotListener): () => void {
    this.snapshotListeners.add(listener)
    return () => this.snapshotListeners.delete(listener)
  }

  /** For React's useSyncExternalStore: notified when `getStats()` changes (≤ once per second). */
  subscribeStats = (listener: () => void): (() => void) => {
    this.statsListeners.add(listener)
    return () => this.statsListeners.delete(listener)
  }

  getStats = (): StreamStats => this.stats

  // -- SSE ----------------------------------------------------------------------------------

  private openEventSource(): void {
    const source = this.createEventSource(this.streamUrl)
    this.eventSource = source
    this.lastMessageAt = this.now()
    const alive = () => {
      if (source === this.eventSource) this.lastMessageAt = this.now()
    }

    source.addEventListener('open', () => {
      if (source !== this.eventSource) return
      alive()
      this.sseErrors = 0
      this.stopPolling() // SSE works again; polling is no longer needed
      this.setTransport('live')
    })
    source.addEventListener('vehicles', (event) => {
      if (source !== this.eventSource) return
      alive()
      const snapshot = parseJson<Snapshot>(event.data)
      if (snapshot) this.applySnapshot(snapshot)
    })
    source.addEventListener('status', (event) => {
      if (source !== this.eventSource) return
      alive()
      const status = parseJson<StatusEvent>(event.data)
      if (status) {
        this.upstreamStatus = status.upstream_status
        this.refreshStats()
      }
    })
    source.addEventListener('heartbeat', alive)
    source.addEventListener('error', () =>
      this.handleEventSourceError(source, source.readyState === EVENT_SOURCE_CLOSED),
    )
  }

  /** Watchdog: silence longer than two heartbeats means the stream is dead (see header). */
  private checkSilence(): void {
    const source = this.eventSource
    if (source && this.now() - this.lastMessageAt > SSE_SILENCE_MS) {
      this.handleEventSourceError(source, true)
    }
  }

  private handleEventSourceError(source: EventSourceLike, closed: boolean): void {
    if (source !== this.eventSource || !this.running) return
    this.sseErrors += 1

    if (this.sseErrors >= MAX_SSE_ERRORS) {
      // SSE keeps failing (server down, or a proxy that breaks long-lived connections).
      // Fall back to plain polling and try SSE again later.
      this.closeEventSource()
      this.startPolling()
      this.scheduleSseRetry(SSE_RETRY_MS)
      return
    }

    if (!this.polling) this.setTransport('reconnecting')
    if (closed) {
      // The browser only auto-reconnects after network errors. After an HTTP error (e.g. 502
      // from nginx while the backend restarts) it gives up, and a silent dead connection is
      // never noticed at all, so in both cases we reopen it ourselves.
      this.closeEventSource()
      this.scheduleSseRetry(1000 * 2 ** (this.sseErrors - 1))
    }
    // Otherwise readyState is CONNECTING: the browser is already retrying on its own.
  }

  private scheduleSseRetry(delayMs: number): void {
    if (this.sseRetryTimer) clearTimeout(this.sseRetryTimer)
    this.sseRetryTimer = setTimeout(() => {
      this.sseRetryTimer = null
      if (!this.running || this.eventSource) return
      if (this.polling) {
        // One more failure while retrying from polling mode sends us straight back to polling.
        this.sseErrors = MAX_SSE_ERRORS - 1
      }
      this.openEventSource()
    }, delayMs)
  }

  private closeEventSource(): void {
    this.eventSource?.close()
    this.eventSource = null
  }

  // -- Polling fallback ---------------------------------------------------------------------

  private startPolling(): void {
    if (this.polling) return
    this.polling = true
    this.setTransport('reconnecting') // until the first poll succeeds
    void this.pollOnce()
  }

  private stopPolling(): void {
    this.polling = false
    this.lastPollFailed = false
    if (this.pollTimer) clearTimeout(this.pollTimer)
    this.pollTimer = null
  }

  private async pollOnce(): Promise<void> {
    if (!this.polling) return
    try {
      const snapshot = await this.fetchSnapshot()
      if (!this.polling) return
      this.applySnapshot(snapshot)
      this.setTransport('polling')
      if (this.lastPollFailed) {
        // The server was unreachable and is back (e.g. a restart), so SSE probably works again
        // too. Try it now rather than waiting for the 60 s retry.
        this.lastPollFailed = false
        if (!this.eventSource) this.scheduleSseRetry(0)
      }
    } catch {
      if (!this.polling) return
      this.lastPollFailed = true
      this.setTransport('reconnecting')
    }
    if (this.polling) {
      this.pollTimer = setTimeout(() => void this.pollOnce(), POLL_INTERVAL_MS)
    }
  }

  private async loadInitialSnapshot(): Promise<void> {
    try {
      const snapshot = await this.fetchSnapshot()
      if (this.running) this.applySnapshot(snapshot)
    } catch {
      // Not fatal: SSE or the polling fallback will deliver data.
    }
  }

  // -- State --------------------------------------------------------------------------------

  private applySnapshot(snapshot: Snapshot): void {
    // Never go back in time: a slow poll response must not overwrite a newer SSE snapshot.
    const current = this.latest?.fetched_at
    if (current && snapshot.fetched_at && Date.parse(snapshot.fetched_at) < Date.parse(current)) {
      return
    }

    this.latest = snapshot
    this.upstreamStatus = snapshot.upstream_status
    for (const listener of this.snapshotListeners) listener(snapshot)
    this.refreshStats()
  }

  private setTransport(transport: Transport): void {
    if (this.transport === transport) return
    this.transport = transport
    this.refreshStats()
  }

  private computeStats(): StreamStats {
    const fetchedAt = this.latest?.fetched_at ?? null
    const ageMs = fetchedAt ? Math.max(0, this.now() - Date.parse(fetchedAt)) : null
    const isStale = ageMs !== null && ageMs > STALE_AFTER_MS
    return {
      // A broken link to our own server says more than "the data is old", so "reconnecting"
      // takes precedence over "stale" (the age is still shown alongside it).
      connection: this.transport === 'reconnecting' ? 'reconnecting' : isStale ? 'stale' : this.transport,
      transport: this.transport,
      isStale,
      vehicleCount: this.latest?.vehicles.length ?? 0,
      fetchedAt,
      ageSeconds: ageMs === null ? null : Math.floor(ageMs / 1000),
      upstreamStatus: this.upstreamStatus,
    }
  }

  private refreshStats(): void {
    const next = this.computeStats()
    if (shallowEqual(next, this.stats)) return
    this.stats = next // a new object only when something changed, as useSyncExternalStore needs
    for (const listener of this.statsListeners) listener()
  }
}

async function defaultFetchSnapshot(): Promise<Snapshot> {
  const response = await fetch('/api/v1/vehicles', { headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return (await response.json()) as Snapshot
}

function parseJson<T>(data: unknown): T | null {
  if (typeof data !== 'string') return null
  try {
    return JSON.parse(data) as T
  } catch {
    return null
  }
}

function shallowEqual(a: StreamStats, b: StreamStats): boolean {
  return (Object.keys(a) as (keyof StreamStats)[]).every((key) => a[key] === b[key])
}
