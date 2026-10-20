// Basemap and colours for map layers. MapLibre paint properties need literal colours, so the
// values below mirror the CSS custom properties in styles/tokens.css. Change both together.

const OPENFREEMAP_LIGHT = 'https://tiles.openfreemap.org/styles/positron'
const OPENFREEMAP_DARK = 'https://tiles.openfreemap.org/styles/dark'

export function mapStyleUrl(theme: 'light' | 'dark'): string {
  const custom = import.meta.env.VITE_MAP_STYLE_URL?.trim()
  const customDark = import.meta.env.VITE_MAP_STYLE_URL_DARK?.trim()
  if (theme === 'dark') return customDark || custom || OPENFREEMAP_DARK
  return custom || OPENFREEMAP_LIGHT
}

// The basemap's own attribution (OpenFreeMap, OpenMapTiles, OpenStreetMap) comes from its
// TileJSON automatically. This adds the transit data credit.
export const FOLI_ATTRIBUTION =
  'Data: <a href="https://data.foli.fi/" target="_blank" rel="noopener">Föli / Turun seudun joukkoliikenne</a>'

export const TURKU_VIEW = { longitude: 22.2666, latitude: 60.4518, zoom: 12 }

// Fonts served by the OpenFreeMap glyph server. A custom style must provide the same fonts
// (or labels on clusters and buses will not render).
export const FONT_BOLD = ['Noto Sans Bold']
export const FONT_REGULAR = ['Noto Sans Regular']

export interface MapColors {
  surface: string
  text: string
  vehicle: string
  vehicleText: string
  vehicleStroke: string
  vehicleUnknown: string
  route: string
  routeCasing: string
  routeText: string
  stop: string
  stopCluster: string
  stopClusterText: string
  favourite: string
  stale: string
  nearby: string
}

export const mapColors: Record<'light' | 'dark', MapColors> = {
  light: {
    surface: '#ffffff',
    text: '#1d2430',
    vehicle: '#f0b323', // Föli yellow, as used on foli.fi
    vehicleText: '#1d2430',
    vehicleStroke: '#1d2430',
    vehicleUnknown: '#c3c9d2',
    route: '#1f5fd1',
    routeCasing: '#ffffff',
    routeText: '#ffffff',
    stop: '#6b7585',
    stopCluster: '#6b7585',
    stopClusterText: '#ffffff',
    favourite: '#f0b323',
    stale: '#a3abb7',
    nearby: '#1f5fd1',
  },
  dark: {
    surface: '#171c24',
    text: '#e7ebf0',
    vehicle: '#f0b323',
    vehicleText: '#11151b',
    vehicleStroke: '#11151b',
    vehicleUnknown: '#7d8796',
    route: '#6ea2ff',
    routeCasing: '#0b0e13',
    routeText: '#0b0e13',
    stop: '#9aa4b2',
    stopCluster: '#4b5563',
    stopClusterText: '#f2f4f7',
    favourite: '#f0b323',
    stale: '#5f6874',
    nearby: '#6ea2ff',
  },
}
