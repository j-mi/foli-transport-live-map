import { describe, expect, it } from 'vitest'
import type { Vehicle } from '../api/types'
import { lineBounds, padBounds, partitionVehicles, toPosition, vehicleToFeature } from './geojson'

const vehicle = (overrides: Partial<Vehicle> = {}): Vehicle => ({
  id: 'v1',
  line: '1',
  route_id: '1',
  direction: '1',
  destination: 'Satama',
  lat: 60.4518,
  lon: 22.2666,
  delay_s: 30,
  next_stop: 'Kauppatori',
  recorded_at: '2026-10-04T12:00:00Z',
  monitored: true,
  ...overrides,
})

describe('GeoJSON conversion', () => {
  it('puts longitude first', () => {
    expect(toPosition(60.4518, 22.2666)).toEqual([22.2666, 60.4518])
  })

  it('converts a vehicle to a [lon, lat] point', () => {
    const feature = vehicleToFeature(vehicle())
    expect(feature.geometry.coordinates).toEqual([22.2666, 60.4518])
    expect(feature.properties).toMatchObject({ id: 'v1', line: '1', route_id: '1', known: true })
  })

  it('marks vehicles on lines missing from GTFS as unknown', () => {
    const feature = vehicleToFeature(vehicle({ route_id: null, line: null }))
    expect(feature.properties).toMatchObject({ route_id: '', known: false, line: '?' })
  })

  it('splits out the selected line', () => {
    const vehicles = [vehicle({ id: 'a', route_id: '1' }), vehicle({ id: 'b', route_id: '2' })]
    const { selected, others } = partitionVehicles(vehicles, '1')
    expect(selected.features.map((f) => f.properties.id)).toEqual(['a'])
    expect(others.features.map((f) => f.properties.id)).toEqual(['b'])
    expect(partitionVehicles(vehicles, null).selected.features).toHaveLength(0)
  })

  it('computes line bounds as [west, south, east, north]', () => {
    const bounds = lineBounds({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: { type: 'LineString', coordinates: [[22.1, 60.4], [22.3, 60.5]] },
        },
      ],
    })
    expect(bounds).toEqual([22.1, 60.4, 22.3, 60.5])
    expect(lineBounds({ type: 'FeatureCollection', features: [] })).toBeNull()
  })

  it('pads bounds on every side', () => {
    expect(padBounds([0, 0, 10, 10], 0.1)).toEqual([-1, -1, 11, 11])
  })
})
