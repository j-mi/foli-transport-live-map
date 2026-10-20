/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Basemap style URL. Empty means the key-free OpenFreeMap default. */
  readonly VITE_MAP_STYLE_URL?: string
  /** Optional dark basemap style URL (falls back to VITE_MAP_STYLE_URL, then OpenFreeMap dark). */
  readonly VITE_MAP_STYLE_URL_DARK?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
