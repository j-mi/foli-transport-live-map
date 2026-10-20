import { Popup } from '@vis.gl/react-maplibre'
import { useDepartures, useToggleFavouriteStop } from '../../api/queries'
import { FavouriteButton } from '../../components/FavouriteButton'
import { LineBadge } from '../../components/LineBadge'
import { formatClock, formatDeparture } from '../../format'
import { useFavouriteIds, useLineLookup, useStopLookup } from '../../hooks/useLookups'
import { useNow } from '../../hooks/useNow'
import { useUiDispatch } from '../../state/uiState'

export function StopPopup({ stopId }: { stopId: string }) {
  const stop = useStopLookup().get(stopId)
  const dispatch = useUiDispatch()
  const favourites = useFavouriteIds()
  const toggle = useToggleFavouriteStop()
  if (!stop) return null

  const isFavourite = favourites.stops.has(stopId)
  return (
    <Popup
      longitude={stop.lon}
      latitude={stop.lat}
      anchor="bottom"
      offset={10}
      maxWidth="320px"
      className="map-popup"
      onClose={() => dispatch({ type: 'closeStop', stopId })}
    >
      <div className="popup">
        <h2 className="popup__title">{stop.name}</h2>
        <p className="popup__meta">Stop {stop.stop_id}</p>
        <FavouriteButton
          pressed={isFavourite}
          subject={stop.name}
          showText
          onToggle={() => toggle.mutate({ stop, favourite: !isFavourite })}
        />
        {toggle.isError && <p className="popup__warning">Could not update favourites. Try again.</p>}
        <Departures stopId={stopId} />
      </div>
    </Popup>
  )
}

function Departures({ stopId }: { stopId: string }) {
  const { data, isPending, isError } = useDepartures(stopId)
  const lines = useLineLookup()
  const now = useNow(15_000)

  return (
    <section className="departures" aria-label="Next departures">
      <h3 className="departures__title">Next departures</h3>
      {isPending && <p className="muted">Loading…</p>}
      {isError && <p className="muted">Departures are unavailable right now.</p>}
      {data && data.departures.length === 0 && <p className="muted">No departures in the next hour.</p>}
      {data && data.departures.length > 0 && (
        <ul className="departures__list">
          {data.departures.slice(0, 6).map((departure, index) => {
            const time = departure.expected_departure ?? departure.aimed_departure
            const line = departure.route_id ? lines.get(departure.route_id) : undefined
            const late =
              departure.expected_departure &&
              departure.aimed_departure &&
              Date.parse(departure.expected_departure) - Date.parse(departure.aimed_departure) >= 60_000
            return (
              <li key={`${departure.vehicle_id ?? 'x'}-${time ?? index}`} className="departures__row">
                <LineBadge name={departure.line ?? '?'} color={line?.color} textColor={line?.text_color} />
                <span className="departures__dest">{departure.destination ?? '—'}</span>
                <span className="departures__time tabular">
                  {time ? formatDeparture(time, now) : '—'}
                  {late && departure.aimed_departure && (
                    <span className="departures__aimed"> (sched. {formatClock(departure.aimed_departure)})</span>
                  )}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
