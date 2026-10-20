import '@fontsource-variable/public-sans'
import './styles/tokens.css'
import './styles/app.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MapProvider } from '@vis.gl/react-maplibre'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ApiError } from './api/client'
import { App } from './App'
import { VehicleStreamProvider } from './hooks/useVehicleStream'
import { UiStateProvider } from './state/uiState'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Retry server-side and network failures, but not "not found"-type answers.
      retry: (failureCount, error) =>
        failureCount < 3 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <UiStateProvider>
        <VehicleStreamProvider>
          <MapProvider>
            <App />
          </MapProvider>
        </VehicleStreamProvider>
      </UiStateProvider>
    </QueryClientProvider>
  </StrictMode>,
)
