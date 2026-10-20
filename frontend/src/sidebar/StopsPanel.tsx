import { useVirtualizer } from '@tanstack/react-virtual'
import { useMemo, useRef, useState } from 'react'
import { useStops, useToggleFavouriteStop } from '../api/queries'
import { FavouriteButton } from '../components/FavouriteButton'
import { ErrorNotice } from '../components/Notice'
import { SearchField } from '../components/SearchField'
import { useFavouriteIds, useStopLookup, type StopInfo } from '../hooks/useLookups'
import { useRevealMap } from '../hooks/useRevealMap'
import { useCamera } from '../map/camera'
import { useUiDispatch } from '../state/uiState'
import { filterStops } from './filters'

const ROW_HEIGHT = 48

export function StopsPanel() {
  const { isPending, isError, error, refetch } = useStops()
  const lookup = useStopLookup()
  const [query, setQuery] = useState('')
  const stops = useMemo(() => filterStops([...lookup.values()], query), [lookup, query])
  const openStop = useOpenStop()
  const favourites = useFavouriteIds()
  const toggleFavourite = useToggleFavouriteStop()

  // ~3 600 stops: only the rows in view are rendered (virtualised list).
  const scrollRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: stops.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  })

  return (
    <div className="panel panel--fill">
      <SearchField label="Search stops" placeholder="Stop name or number" value={query} onChange={setQuery} />
      {isPending && <p className="muted">Loading stops…</p>}
      {isError && <ErrorNotice error={error} what="stops" onRetry={() => void refetch()} />}
      {!isPending && !isError && (
        <p className="muted small tabular" aria-live="polite">
          {stops.length === 0 ? `No stops match “${query}”.` : `${stops.length} stops`}
        </p>
      )}
      <div ref={scrollRef} className="virtual-list">
        <ul className="virtual-list__inner" style={{ height: virtualizer.getTotalSize() }} aria-label="Stops">
          {virtualizer.getVirtualItems().map((item) => {
            const stop = stops[item.index]!
            const isFavourite = favourites.stops.has(stop.stop_id)
            return (
              <li
                key={stop.stop_id}
                className="item-row virtual-list__row"
                aria-setsize={stops.length}
                aria-posinset={item.index + 1}
                style={{ height: item.size, transform: `translateY(${item.start}px)` }}
              >
                <button type="button" className="item-row__main" onClick={() => openStop(stop)}>
                  <span className="item-row__text">{stop.name}</span>
                  <span className="item-row__meta tabular">{stop.stop_id}</span>
                </button>
                <FavouriteButton
                  pressed={isFavourite}
                  subject={stop.name}
                  onToggle={() => toggleFavourite.mutate({ stop, favourite: !isFavourite })}
                />
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}

/** Fly to a stop and open its popup. Shared by the stops, favourites and nearby panels. */
export function useOpenStop() {
  const camera = useCamera()
  const dispatch = useUiDispatch()
  const revealMap = useRevealMap()
  return (stop: Pick<StopInfo, 'stop_id' | 'lat' | 'lon'>) => {
    camera.flyTo(stop.lon, stop.lat, 16)
    dispatch({ type: 'openStop', stopId: stop.stop_id })
    revealMap()
  }
}
