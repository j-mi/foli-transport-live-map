import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Snapshot } from '../api/types'
import {
  POLL_INTERVAL_MS,
  SSE_RETRY_MS,
  SSE_SILENCE_MS,
  VehicleStreamClient,
  type EventSourceLike,
} from './vehicleStream'

/** A controllable stand-in for the browser's EventSource. */
class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = []
  readyState = 0 // CONNECTING
  closed = false
  private listeners = new Map<string, ((event: MessageEvent) => void)[]>()

  readonly url: string

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }

  close(): void {
    this.closed = true
    this.readyState = 2
  }

  emit(type: string, data?: unknown): void {
    const event = { data: data === undefined ? undefined : JSON.stringify(data) } as MessageEvent
    for (const listener of this.listeners.get(type) ?? []) listener(event)
  }

  open(): void {
    this.readyState = 1
    this.emit('open')
  }

  /** Network error: the browser keeps retrying (CONNECTING). HTTP error: it gives up (CLOSED). */
  fail({ fatal = false } = {}): void {
    this.readyState = fatal ? 2 : 0
    this.emit('error')
  }
}

const latestSource = () => FakeEventSource.instances.at(-1)!

function snapshot(seq: number, ageMs = 0, count = 2): Snapshot {
  return {
    seq,
    fetched_at: new Date(Date.now() - ageMs).toISOString(),
    upstream_status: 'OK',
    vehicles: Array.from({ length: count }, (_, i) => ({
      id: `v${i}`,
      line: '1',
      route_id: '1',
      direction: '1',
      destination: 'Satama',
      lat: 60.45,
      lon: 22.27,
      delay_s: 0,
      next_stop: null,
      recorded_at: new Date().toISOString(),
      monitored: true,
    })),
  }
}

describe('VehicleStreamClient', () => {
  let fetchSnapshot: ReturnType<typeof vi.fn<() => Promise<Snapshot>>>
  let client: VehicleStreamClient

  beforeEach(() => {
    vi.useFakeTimers({ now: new Date('2026-10-04T12:00:00Z') })
    FakeEventSource.instances = []
    fetchSnapshot = vi.fn(() => Promise.resolve(snapshot(1)))
    client = new VehicleStreamClient({
      createEventSource: (url) => new FakeEventSource(url),
      fetchSnapshot,
      now: () => Date.now(),
    })
  })

  afterEach(() => {
    client.stop()
    vi.useRealTimers()
  })

  it('paints from REST first, then goes live over SSE', async () => {
    client.start()
    expect(client.getStats().connection).toBe('connecting')
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchSnapshot).toHaveBeenCalledTimes(1)
    expect(client.getStats().vehicleCount).toBe(2)

    latestSource().open()
    expect(client.getStats().connection).toBe('live')

    const received: number[] = []
    client.subscribe((s) => received.push(s.seq))
    latestSource().emit('vehicles', snapshot(2, 0, 5))
    expect(received).toEqual([2])
    expect(client.getStats().vehicleCount).toBe(5)
  })

  it('shows reconnecting while the browser retries, and recovers', async () => {
    client.start()
    latestSource().open()
    latestSource().fail()
    expect(client.getStats().connection).toBe('reconnecting')
    latestSource().open()
    expect(client.getStats().connection).toBe('live')
  })

  it('reopens the stream itself after an HTTP error', async () => {
    client.start()
    latestSource().fail({ fatal: true }) // e.g. 502 from nginx while the backend restarts
    expect(FakeEventSource.instances).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(FakeEventSource.instances).toHaveLength(2)
    expect(FakeEventSource.instances[0]!.closed).toBe(true)
  })

  it('falls back to polling after repeated errors and retries SSE later', async () => {
    client.start()
    await vi.advanceTimersByTimeAsync(0)
    fetchSnapshot.mockClear()
    const first = latestSource()
    first.fail()
    first.fail()
    first.fail()
    expect(first.closed).toBe(true)

    await vi.advanceTimersByTimeAsync(0)
    expect(fetchSnapshot).toHaveBeenCalledTimes(1)
    expect(client.getStats().connection).toBe('polling')

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(fetchSnapshot).toHaveBeenCalledTimes(2)

    // SSE is retried after a minute; when it opens, polling stops.
    await vi.advanceTimersByTimeAsync(SSE_RETRY_MS)
    const retry = latestSource()
    expect(retry).not.toBe(first)
    retry.open()
    expect(client.getStats().connection).toBe('live')
    const polls = fetchSnapshot.mock.calls.length
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)
    expect(fetchSnapshot).toHaveBeenCalledTimes(polls)
  })

  it('a single failed retry goes straight back to polling', async () => {
    client.start()
    for (let i = 0; i < 3; i++) latestSource().fail()
    await vi.advanceTimersByTimeAsync(SSE_RETRY_MS)
    const retry = latestSource()
    retry.fail()
    expect(retry.closed).toBe(true)
    expect(client.getStats().transport).toBe('polling')
  })

  it('reports reconnecting while polls fail, and retries SSE as soon as the server is back', async () => {
    client.start()
    await vi.advanceTimersByTimeAsync(0)
    fetchSnapshot.mockRejectedValue(new Error('down'))
    for (let i = 0; i < 3; i++) latestSource().fail()
    await vi.advanceTimersByTimeAsync(0)
    expect(client.getStats().connection).toBe('reconnecting')

    const sourcesBefore = FakeEventSource.instances.length
    fetchSnapshot.mockResolvedValue(snapshot(9))
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(client.getStats().connection).toBe('polling')
    // The retry is queued (0 ms) right after the successful poll. Fake timers run a 0 ms timer
    // created during a tick 1 ms later, hence 1 here.
    await vi.advanceTimersByTimeAsync(1)
    expect(FakeEventSource.instances.length).toBe(sourcesBefore + 1) // no 60 s wait
  })

  it('reopens a stream that has gone silent, but not one that sends heartbeats', async () => {
    client.start()
    const first = latestSource()
    first.open()
    // Heartbeats every 15 s keep a quiet connection alive (e.g. Föli down, no new snapshots).
    for (let i = 0; i < 4; i++) {
      await vi.advanceTimersByTimeAsync(15_000)
      first.emit('heartbeat', '2026-10-04T12:00:00Z')
    }
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(client.getStats().transport).toBe('live')

    // Then total silence, e.g. a proxy dropped the connection without telling the browser.
    await vi.advanceTimersByTimeAsync(SSE_SILENCE_MS + 1000)
    expect(first.closed).toBe(true)
    expect(client.getStats().transport).toBe('reconnecting')
    await vi.advanceTimersByTimeAsync(1000)
    const second = latestSource()
    expect(second).not.toBe(first)
    second.open()
    expect(client.getStats().transport).toBe('live')
  })

  it('marks data older than 20 s as stale whatever the transport', async () => {
    client.start()
    latestSource().open()
    latestSource().emit('vehicles', snapshot(3, 25_000))
    const stats = client.getStats()
    expect(stats.transport).toBe('live')
    expect(stats.isStale).toBe(true)
    expect(stats.connection).toBe('stale')
    expect(stats.ageSeconds).toBe(25)
  })

  it('says "reconnecting" rather than "stale" when the server connection is down', async () => {
    client.start()
    latestSource().open()
    latestSource().emit('vehicles', snapshot(3, 25_000))
    latestSource().fail()
    const stats = client.getStats()
    expect(stats.isStale).toBe(true) // the age is still reported...
    expect(stats.connection).toBe('reconnecting') // ...but the label names the actual problem
  })

  it('becomes stale over time when updates stop arriving', async () => {
    client.start()
    latestSource().open()
    latestSource().emit('vehicles', snapshot(3))
    expect(client.getStats().isStale).toBe(false)
    await vi.advanceTimersByTimeAsync(21_000)
    expect(client.getStats().isStale).toBe(true)
  })

  it('never replaces newer data with an older snapshot', async () => {
    client.start()
    latestSource().open()
    latestSource().emit('vehicles', snapshot(5, 0, 7))
    latestSource().emit('vehicles', snapshot(4, 10_000, 1))
    expect(client.latest?.seq).toBe(5)
  })

  it('tracks upstream status events', async () => {
    client.start()
    latestSource().open()
    latestSource().emit('status', { upstream_status: 'DOWN', fetched_at: null })
    expect(client.getStats().upstreamStatus).toBe('DOWN')
  })

  it('only notifies stats listeners when something changed', async () => {
    fetchSnapshot.mockRejectedValue(new Error('no initial data'))
    client.start()
    latestSource().open()
    const listener = vi.fn()
    client.subscribeStats(listener)
    await vi.advanceTimersByTimeAsync(5_000) // no data yet: nothing ticks
    expect(listener).not.toHaveBeenCalled()
  })
})
