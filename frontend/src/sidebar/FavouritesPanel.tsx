import { useFavourites, useToggleFavouriteLine, useToggleFavouriteStop } from '../api/queries'
import { FavouriteButton } from '../components/FavouriteButton'
import { LineBadge } from '../components/LineBadge'
import { ErrorNotice } from '../components/Notice'
import { useLineLookup } from '../hooks/useLookups'
import { useRevealMap } from '../hooks/useRevealMap'
import { useUiDispatch, useUiState } from '../state/uiState'
import { useOpenStop } from './StopsPanel'

export function FavouritesPanel() {
  const { data, isPending, isError, error, refetch } = useFavourites()
  const lines = useLineLookup()
  const { selectedRouteId } = useUiState()
  const dispatch = useUiDispatch()
  const openStop = useOpenStop()
  const revealMap = useRevealMap()
  const toggleStop = useToggleFavouriteStop()
  const toggleLine = useToggleFavouriteLine()

  if (isPending) return <p className="panel muted">Loading favourites…</p>
  if (isError) return <ErrorNotice error={error} what="favourites" onRetry={() => void refetch()} />

  const empty = data.stops.length === 0 && data.lines.length === 0
  return (
    <div className="panel">
      {empty && (
        <p className="muted">No favourites yet. Use the star next to a line or stop to save it here.</p>
      )}

      {data.lines.length > 0 && (
        <section>
          <h2 className="panel__heading">Lines</h2>
          <ul className="item-list">
            {data.lines.map((favourite) => {
              const line = lines.get(favourite.route_id)
              const isSelected = favourite.route_id === selectedRouteId
              return (
                <li key={favourite.route_id} className="item-row" data-selected={isSelected}>
                  <button
                    type="button"
                    className="item-row__main"
                    aria-pressed={isSelected}
                    onClick={() => {
                      dispatch({ type: 'selectLine', routeId: isSelected ? null : favourite.route_id })
                      if (!isSelected) revealMap()
                    }}
                  >
                    <LineBadge name={favourite.short_name} color={line?.color} textColor={line?.text_color} />
                    <span className="item-row__text">{line?.long_name ?? 'No longer in the timetable'}</span>
                  </button>
                  <FavouriteButton
                    pressed
                    subject={`line ${favourite.short_name}`}
                    onToggle={() => toggleLine.mutate({ line: favourite, favourite: false })}
                  />
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {data.stops.length > 0 && (
        <section>
          <h2 className="panel__heading">Stops</h2>
          <ul className="item-list">
            {data.stops.map((stop) => (
              <li key={stop.stop_id} className="item-row">
                <button type="button" className="item-row__main" onClick={() => openStop(stop)}>
                  <span className="item-row__text">{stop.name}</span>
                  <span className="item-row__meta tabular">{stop.stop_id}</span>
                </button>
                <FavouriteButton
                  pressed
                  subject={stop.name}
                  onToggle={() => toggleStop.mutate({ stop, favourite: false })}
                />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
