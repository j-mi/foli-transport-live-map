import { useId, useState } from 'react'
import { useNearbyStops } from '../api/queries'
import { ErrorNotice } from '../components/Notice'
import { formatDistance } from '../format'
import { useUiDispatch, useUiState } from '../state/uiState'
import { useOpenStop } from './StopsPanel'

const RADII = [250, 500, 1000, 2000]

export function NearbyPanel() {
  const { nearbyPoint } = useUiState()
  const dispatch = useUiDispatch()
  const [radius, setRadius] = useState(500)
  const { data, isPending, isError, error, refetch } = useNearbyStops(nearbyPoint, radius)
  const openStop = useOpenStop()
  const radiusId = useId()

  if (!nearbyPoint) {
    return (
      <div className="panel">
        <p className="muted">
          Right-click the map (or press and hold on a touch screen) to list the stops near that point,
          nearest first.
        </p>
      </div>
    )
  }

  return (
    <div className="panel">
      <div className="nearby-controls">
        <label htmlFor={radiusId}>Within</label>
        <select id={radiusId} value={radius} onChange={(event) => setRadius(Number(event.target.value))}>
          {RADII.map((r) => (
            <option key={r} value={r}>
              {formatDistance(r)}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="button button--small"
          onClick={() => dispatch({ type: 'setNearbyPoint', point: null })}
        >
          Clear
        </button>
      </div>

      {isPending && <p className="muted">Searching…</p>}
      {isError && <ErrorNotice error={error} what="nearby stops" onRetry={() => void refetch()} />}
      {data && data.stops.length === 0 && (
        <p className="muted">No stops within {formatDistance(radius)}. Try a larger distance.</p>
      )}
      {data && data.stops.length > 0 && (
        <ol className="item-list" aria-label="Stops nearest first">
          {data.stops.map((stop) => (
            <li key={stop.stop_id} className="item-row">
              <button type="button" className="item-row__main" onClick={() => openStop(stop)}>
                <span className="item-row__text">{stop.name}</span>
                <span className="item-row__meta tabular">{formatDistance(stop.distance_m)}</span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
