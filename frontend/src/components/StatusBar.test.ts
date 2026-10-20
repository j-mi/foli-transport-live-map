import { describe, expect, it } from 'vitest'
import type { StreamStats } from '../realtime/vehicleStream'
import { summarise } from './StatusBar'

const base: StreamStats = {
  connection: 'live',
  transport: 'live',
  isStale: false,
  vehicleCount: 120,
  fetchedAt: '2026-10-04T12:00:00Z',
  ageSeconds: 3,
  upstreamStatus: 'OK',
}

describe('status bar wording', () => {
  it('is quiet when everything is fine', () => {
    expect(summarise(base)).toEqual({ tone: 'ok', label: 'Live', message: null })
  })

  it('says how old the positions are when live data is unavailable', () => {
    const summary = summarise({
      ...base,
      connection: 'stale',
      isStale: true,
      ageSeconds: 75,
      upstreamStatus: 'DOWN',
    })
    expect(summary.tone).toBe('warning')
    expect(summary.label).toBe('Live data unavailable')
    expect(summary.message).toBe('Föli is not responding. Showing positions from 1 min ago.')
  })

  it('names a lost server connection and still gives the data age', () => {
    const summary = summarise({
      ...base,
      connection: 'reconnecting',
      transport: 'reconnecting',
      isStale: true,
      ageSeconds: 45,
    })
    expect(summary.label).toBe('Reconnecting…')
    expect(summary.message).toBe('Showing positions from 45 s ago.')
  })

  it('explains the polling fallback', () => {
    const summary = summarise({ ...base, connection: 'polling', transport: 'polling' })
    expect(summary.label).toBe('Live (polling)')
    expect(summary.message).toMatch(/every 5 s/)
  })

  it('reports Föli starting up even on a live connection', () => {
    const summary = summarise({ ...base, upstreamStatus: 'PENDING', ageSeconds: null, fetchedAt: null })
    expect(summary.tone).toBe('warning')
    expect(summary.message).toMatch(/starting up/)
  })
})
