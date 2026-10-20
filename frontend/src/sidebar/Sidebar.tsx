import { useRef, type KeyboardEvent } from 'react'
import { ChevronIcon } from '../components/icons'
import { useUiDispatch, useUiState, type Tab } from '../state/uiState'
import { FavouritesPanel } from './FavouritesPanel'
import { LayersPanel } from './LayersPanel'
import { LinesPanel } from './LinesPanel'
import { NearbyPanel } from './NearbyPanel'
import { StopsPanel } from './StopsPanel'

const TABS: { id: Tab; label: string }[] = [
  { id: 'lines', label: 'Lines' },
  { id: 'stops', label: 'Stops' },
  { id: 'favourites', label: 'Favourites' },
  { id: 'nearby', label: 'Nearby' },
  { id: 'layers', label: 'Layers' },
]

export function Sidebar() {
  const { tab, sidebarOpen } = useUiState()
  const dispatch = useUiDispatch()
  const tabRefs = useRef<Partial<Record<Tab, HTMLButtonElement | null>>>({})

  // WAI-ARIA tabs: arrow keys move between tabs, Home/End jump to the ends.
  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const current = TABS.findIndex((t) => t.id === tab)
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
    let next: number | null = null
    if (step !== undefined) next = (current + step + TABS.length) % TABS.length
    if (event.key === 'Home') next = 0
    if (event.key === 'End') next = TABS.length - 1
    if (next === null) return
    event.preventDefault()
    const target = TABS[next]!.id
    dispatch({ type: 'setTab', tab: target })
    tabRefs.current[target]?.focus()
  }

  return (
    <aside className="sidebar" data-open={sidebarOpen} aria-label="Controls">
      <header className="sidebar__header">
        <div className="sidebar__brand">
          <span className="sidebar__logo" aria-hidden="true" />
          <div>
            <h1 className="sidebar__title">Föli live</h1>
            <p className="sidebar__subtitle">Turku region buses</p>
          </div>
        </div>
        <button
          type="button"
          className="icon-button sidebar__toggle"
          aria-expanded={sidebarOpen}
          aria-controls="sidebar-body"
          title={sidebarOpen ? 'Hide panel ( [ )' : 'Show panel ( [ )'}
          onClick={() => dispatch({ type: 'setSidebarOpen', open: !sidebarOpen })}
        >
          <ChevronIcon />
          <span className="visually-hidden">{sidebarOpen ? 'Hide panel' : 'Show panel'}</span>
        </button>
      </header>

      <div id="sidebar-body" className="sidebar__body" hidden={!sidebarOpen}>
        <div className="tabs" role="tablist" aria-label="Sections">
          {TABS.map((t) => (
            <button
              key={t.id}
              ref={(element) => {
                tabRefs.current[t.id] = element
              }}
              type="button"
              role="tab"
              id={`tab-${t.id}`}
              aria-selected={tab === t.id}
              aria-controls={`panel-${t.id}`}
              tabIndex={tab === t.id ? 0 : -1}
              className="tabs__tab"
              onClick={() => dispatch({ type: 'setTab', tab: t.id })}
              onKeyDown={onTabKeyDown}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="tab-panel" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
          {tab === 'lines' && <LinesPanel />}
          {tab === 'stops' && <StopsPanel />}
          {tab === 'favourites' && <FavouritesPanel />}
          {tab === 'nearby' && <NearbyPanel />}
          {tab === 'layers' && <LayersPanel />}
        </div>
      </div>
    </aside>
  )
}
