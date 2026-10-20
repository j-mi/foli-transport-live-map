import { describe, expect, it } from 'vitest'
import { formatAge, formatDelay, formatDeparture, formatDistance } from './format'

describe('formatDelay', () => {
  it.each([
    [null, 'No schedule information'],
    [0, 'On time'],
    [25, 'On time'],
    [-29, 'On time'],
    [180, '3 min late'],
    [-120, '2 min early'],
  ])('%s s -> %s', (seconds, text) => {
    expect(formatDelay(seconds)).toBe(text)
  })
})

describe('other formatting', () => {
  it('formats ages', () => {
    expect(formatAge(3)).toBe('3 s ago')
    expect(formatAge(125)).toBe('2 min ago')
    expect(formatAge(7300)).toBe('2 h ago')
  })

  it('formats distances', () => {
    expect(formatDistance(123)).toBe('120 m')
    expect(formatDistance(1530)).toBe('1.5 km')
  })

  it('formats departures relative to now', () => {
    const now = Date.parse('2026-10-04T12:00:00Z')
    expect(formatDeparture('2026-10-04T11:59:50Z', now)).toBe('now')
    expect(formatDeparture('2026-10-04T12:04:00Z', now)).toBe('in 4 min')
    expect(formatDeparture('2026-10-04T13:00:00Z', now)).toBe('16:00') // Helsinki is UTC+3 in October
  })
})
