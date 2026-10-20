/**
 * UI state shared by the sidebar and the map: what is selected, which layers are on, which
 * sidebar tab is open. Server data (lines, stops, favourites) lives in TanStack Query instead,
 * and live vehicle positions live outside React entirely (see hooks/useVehicleStream.ts).
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useState,
  type Dispatch,
  type ReactNode,
} from 'react'

export type Tab = 'lines' | 'stops' | 'favourites' | 'nearby' | 'layers'
export type ThemePreference = 'system' | 'light' | 'dark'

export interface LayerToggles {
  stops: boolean
  vehicles: boolean
  clusterStops: boolean
  clusterVehicles: boolean
}

export interface UiState {
  selectedRouteId: string | null
  openStopId: string | null
  openVehicleId: string | null
  nearbyPoint: { lat: number; lon: number } | null
  layers: LayerToggles
  tab: Tab
  sidebarOpen: boolean
  theme: ThemePreference
}

export type UiAction =
  | { type: 'selectLine'; routeId: string | null }
  | { type: 'openStop'; stopId: string | null }
  | { type: 'openVehicle'; vehicleId: string | null }
  // Closing carries the id: a popup closing because the user clicked another feature must not
  // close the popup that click just opened.
  | { type: 'closeStop'; stopId: string }
  | { type: 'closeVehicle'; vehicleId: string }
  | { type: 'setNearbyPoint'; point: { lat: number; lon: number } | null }
  | { type: 'toggleLayer'; layer: keyof LayerToggles }
  | { type: 'setTab'; tab: Tab }
  | { type: 'setSidebarOpen'; open: boolean }
  | { type: 'setTheme'; theme: ThemePreference }
  | { type: 'clearSelection' }

const THEME_STORAGE_KEY = 'foli-live:theme'

function readStoredTheme(): ThemePreference {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system' // storage can be unavailable (private mode, blocked site data)
  }
}

export function initialUiState(): UiState {
  return {
    selectedRouteId: null,
    openStopId: null,
    openVehicleId: null,
    nearbyPoint: null,
    layers: { stops: true, vehicles: true, clusterStops: true, clusterVehicles: true },
    tab: 'lines',
    sidebarOpen: true,
    theme: readStoredTheme(),
  }
}

export function uiReducer(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case 'selectLine':
      return { ...state, selectedRouteId: action.routeId }
    case 'openStop':
      // One popup at a time keeps the map readable.
      return { ...state, openStopId: action.stopId, openVehicleId: null }
    case 'openVehicle':
      return { ...state, openVehicleId: action.vehicleId, openStopId: null }
    case 'closeStop':
      return state.openStopId === action.stopId ? { ...state, openStopId: null } : state
    case 'closeVehicle':
      return state.openVehicleId === action.vehicleId ? { ...state, openVehicleId: null } : state
    case 'setNearbyPoint':
      return {
        ...state,
        nearbyPoint: action.point,
        tab: action.point ? 'nearby' : state.tab,
        sidebarOpen: action.point ? true : state.sidebarOpen,
      }
    case 'toggleLayer':
      return { ...state, layers: { ...state.layers, [action.layer]: !state.layers[action.layer] } }
    case 'setTab':
      return { ...state, tab: action.tab, sidebarOpen: true }
    case 'setSidebarOpen':
      return { ...state, sidebarOpen: action.open }
    case 'setTheme':
      return { ...state, theme: action.theme }
    case 'clearSelection':
      return { ...state, selectedRouteId: null, openStopId: null, openVehicleId: null }
  }
}

const UiStateContext = createContext<UiState | null>(null)
const UiDispatchContext = createContext<Dispatch<UiAction> | null>(null)

export function UiStateProvider({ children, initial }: { children: ReactNode; initial?: UiState }) {
  const [state, dispatch] = useReducer(uiReducer, initial ?? null, (i) => i ?? initialUiState())

  useEffect(() => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, state.theme)
    } catch {
      // A remembered theme is a convenience; ignore storage failures.
    }
  }, [state.theme])

  return (
    <UiStateContext.Provider value={state}>
      <UiDispatchContext.Provider value={dispatch}>{children}</UiDispatchContext.Provider>
    </UiStateContext.Provider>
  )
}

export function useUiState(): UiState {
  const state = useContext(UiStateContext)
  if (!state) throw new Error('useUiState must be used inside UiStateProvider')
  return state
}

export function useUiDispatch(): Dispatch<UiAction> {
  const dispatch = useContext(UiDispatchContext)
  if (!dispatch) throw new Error('useUiDispatch must be used inside UiStateProvider')
  return dispatch
}

/** Resolves 'system' using the OS setting and keeps <html data-theme> in sync. */
export function useResolvedTheme(): 'light' | 'dark' {
  const { theme } = useUiState()
  const systemDark = useMediaQuery('(prefers-color-scheme: dark)')
  const resolved = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme
  useEffect(() => {
    if (theme === 'system') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
  }, [theme])
  return resolved
}

export function useMediaQuery(query: string): boolean {
  const media = useMemo(
    () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query) : null),
    [query],
  )
  const [matches, setMatches] = useState(media?.matches ?? false)
  useEffect(() => {
    if (!media) return
    const onChange = () => setMatches(media.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [media])
  return matches
}

export function usePrefersReducedMotion(): boolean {
  return useMediaQuery('(prefers-reduced-motion: reduce)')
}
