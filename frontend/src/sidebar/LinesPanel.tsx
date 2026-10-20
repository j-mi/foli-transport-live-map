import { useMemo, useState } from 'react'
import { useLines, useToggleFavouriteLine } from '../api/queries'
import { FavouriteButton } from '../components/FavouriteButton'
import { LineBadge } from '../components/LineBadge'
import { ErrorNotice } from '../components/Notice'
import { SearchField } from '../components/SearchField'
import { useFavouriteIds, useLineLookup } from '../hooks/useLookups'
import { useRevealMap } from '../hooks/useRevealMap'
import { useUiDispatch, useUiState } from '../state/uiState'
import { filterLines } from './filters'

export function LinesPanel() {
  const { data, isPending, isError, error, refetch } = useLines()
  const [query, setQuery] = useState('')
  const { selectedRouteId } = useUiState()
  const dispatch = useUiDispatch()
  const favourites = useFavouriteIds()
  const toggleFavourite = useToggleFavouriteLine()
  const revealMap = useRevealMap()
  const selected = useLineLookup().get(selectedRouteId ?? '')
  const lines = useMemo(() => filterLines(data?.lines ?? [], query), [data, query])

  return (
    <div className="panel">
      <SearchField label="Search lines" placeholder="Line number or place" value={query} onChange={setQuery} />

      {selected && (
        <div className="selection-banner">
          <span>
            Showing line <LineBadge name={selected.short_name} color={selected.color} textColor={selected.text_color} />
          </span>
          <button type="button" className="button button--small" onClick={() => dispatch({ type: 'selectLine', routeId: null })}>
            Show all
          </button>
        </div>
      )}

      {isPending && <p className="muted">Loading lines…</p>}
      {isError && <ErrorNotice error={error} what="lines" onRetry={() => void refetch()} />}
      {data && lines.length === 0 && <p className="muted">No lines match “{query}”.</p>}

      <ul className="item-list" aria-label="Lines">
        {lines.map((line) => {
          const isSelected = line.route_id === selectedRouteId
          return (
            <li key={line.route_id} className="item-row" data-selected={isSelected}>
              <button
                type="button"
                className="item-row__main"
                aria-pressed={isSelected}
                onClick={() => {
                  dispatch({ type: 'selectLine', routeId: isSelected ? null : line.route_id })
                  if (!isSelected) revealMap()
                }}
              >
                <LineBadge name={line.short_name} color={line.color} textColor={line.text_color} />
                <span className="item-row__text">{line.long_name}</span>
              </button>
              <FavouriteButton
                pressed={favourites.lines.has(line.route_id)}
                subject={`line ${line.short_name}`}
                onToggle={() =>
                  toggleFavourite.mutate({ line, favourite: !favourites.lines.has(line.route_id) })
                }
              />
            </li>
          )
        })}
      </ul>
    </div>
  )
}
