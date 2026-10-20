import { ErrorBoundary } from './components/ErrorBoundary'
import { StatusBar } from './components/StatusBar'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import { MapView } from './map/MapView'
import { Sidebar } from './sidebar/Sidebar'
import { useResolvedTheme, useUiState } from './state/uiState'

export function App() {
  useKeyboardShortcuts()
  useResolvedTheme() // keeps <html data-theme> in sync with the chosen theme
  const { sidebarOpen } = useUiState()

  return (
    <div className="app" data-sidebar-open={sidebarOpen}>
      <Sidebar />
      <main className="map-area" aria-label="Map">
        <ErrorBoundary what="map">
          <MapView />
        </ErrorBoundary>
        <StatusBar />
      </main>
    </div>
  )
}
