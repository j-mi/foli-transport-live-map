import { Popup } from '@vis.gl/react-maplibre'
import { useState } from 'react'
import type { Vehicle } from '../../api/types'
import { LineBadge } from '../../components/LineBadge'
import { formatAge, formatDelay } from '../../format'
import { useLineLookup } from '../../hooks/useLookups'
import { useNow } from '../../hooks/useNow'
import { useVehicleSnapshots, useVehicleStreamClient } from '../../hooks/useVehicleStream'
import { useUiDispatch, useUiState } from '../../state/uiState'

/**
 * Follows one bus: on each snapshot it looks the vehicle up again and moves with it. Only this
 * popup re-renders on updates, not the rest of the app.
 */
export function VehiclePopup({ vehicleId }: { vehicleId: string }) {
  const client = useVehicleStreamClient()
  const dispatch = useUiDispatch()
  const { selectedRouteId } = useUiState()
  const lines = useLineLookup()
  const now = useNow(1000)
  const [vehicle, setVehicle] = useState<Vehicle | null>(
    () => client.latest?.vehicles.find((v) => v.id === vehicleId) ?? null,
  )
  const [gone, setGone] = useState(false)

  useVehicleSnapshots((snapshot) => {
    const next = snapshot.vehicles.find((v) => v.id === vehicleId)
    if (next) setVehicle(next)
    setGone(!next)
  })

  if (!vehicle) return null
  const line = vehicle.route_id ? lines.get(vehicle.route_id) : undefined
  const positionAge = Math.max(0, Math.floor((now - Date.parse(vehicle.recorded_at)) / 1000))

  return (
    <Popup
      longitude={vehicle.lon}
      latitude={vehicle.lat}
      anchor="bottom"
      offset={14}
      maxWidth="300px"
      className="map-popup"
      onClose={() => dispatch({ type: 'closeVehicle', vehicleId })}
    >
      <div className="popup">
        <h2 className="popup__title popup__title--line">
          <LineBadge name={vehicle.line ?? '?'} color={line?.color} textColor={line?.text_color} />
          <span>{vehicle.destination ?? 'Destination unknown'}</span>
        </h2>
        <dl className="popup__facts">
          <dt>Schedule</dt>
          <dd>{formatDelay(vehicle.delay_s)}</dd>
          <dt>Next stop</dt>
          <dd>{vehicle.next_stop ?? '—'}</dd>
          <dt>Position</dt>
          <dd className="tabular">updated {formatAge(positionAge)}</dd>
        </dl>
        {!line && <p className="popup__note">This line is not in the timetable data.</p>}
        {!vehicle.monitored && <p className="popup__note">Not monitored: position is an estimate.</p>}
        {gone && <p className="popup__warning">Föli no longer reports this bus. Last known position shown.</p>}
        {vehicle.route_id && vehicle.route_id !== selectedRouteId && (
          <button
            type="button"
            className="button button--small"
            onClick={() => dispatch({ type: 'selectLine', routeId: vehicle.route_id })}
          >
            Show line {vehicle.line} route
          </button>
        )}
      </div>
    </Popup>
  )
}
