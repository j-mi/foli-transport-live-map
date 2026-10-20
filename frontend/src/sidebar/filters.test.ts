import { describe, expect, it } from 'vitest'
import type { Line } from '../api/types'
import { filterLines, filterStops } from './filters'

const line = (short_name: string, long_name: string): Line => ({
  route_id: short_name,
  short_name,
  long_name,
  color: null,
  text_color: null,
})

describe('filterLines', () => {
  const lines = [line('1', 'Lentoasema-Satama'), line('14', 'Ilpoinen-Raunistula'), line('2', 'Kohmo')]

  it('matches line number prefixes', () => {
    expect(filterLines(lines, '1').map((l) => l.short_name)).toEqual(['1', '14'])
  })

  it('matches places case-insensitively', () => {
    expect(filterLines(lines, 'satama').map((l) => l.short_name)).toEqual(['1'])
  })

  it('returns everything for an empty query', () => {
    expect(filterLines(lines, '  ')).toHaveLength(3)
  })
})

describe('filterStops', () => {
  const stops = [
    { stop_id: '2', name: 'Kauppatori', lat: 0, lon: 0 },
    { stop_id: '10', name: 'Ylioppilaskylä', lat: 0, lon: 0 },
    { stop_id: '33', name: 'Itäinen Kauppatori', lat: 0, lon: 0 },
  ]

  it('puts names that start with the query first', () => {
    expect(filterStops(stops, 'kauppa').map((s) => s.stop_id)).toEqual(['2', '33'])
  })

  it('matches stop numbers', () => {
    expect(filterStops(stops, '10').map((s) => s.stop_id)).toEqual(['10'])
  })

  it('sorts alphabetically with Finnish rules', () => {
    expect(filterStops(stops, '').map((s) => s.name)).toEqual([
      'Itäinen Kauppatori',
      'Kauppatori',
      'Ylioppilaskylä',
    ])
  })
})
