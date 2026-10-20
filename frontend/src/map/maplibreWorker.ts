/**
 * MapLibre GL 6 runs parsing and clustering in a web worker and finds the worker script relative
 * to its own file (`import.meta.url`). Bundlers move and rename that file (Vite pre-bundles it in
 * development and hashes it in production builds), so the worker would 404 and the map would
 * stay blank. Instead we let Vite build the worker, including the chunk it shares with the main
 * library, and tell MapLibre where it is. Import this module once, before creating a map.
 */
import { setWorkerUrl } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

setWorkerUrl(workerUrl)
