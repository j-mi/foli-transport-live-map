import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // In development the backend runs on :8000. Proxying keeps the browser on one origin, the
    // same way nginx does in docker-compose, so the frontend code only ever uses /api/... URLs.
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  // MapLibre starts its worker as an ES module worker (see src/map/maplibreWorker.ts).
  worker: { format: 'es' },
  build: {
    // MapLibre alone is ~1 MB minified. Its own chunk means an app update does not make
    // returning visitors download the map library again.
    chunkSizeWarningLimit: 1100,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'maplibre', test: /node_modules[\\/]maplibre-gl/, priority: 20 },
            { name: 'vendor', test: /node_modules/, priority: 10 },
          ],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
