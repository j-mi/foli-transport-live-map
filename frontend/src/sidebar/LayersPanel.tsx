import { useUiDispatch, useUiState, type LayerToggles, type ThemePreference } from '../state/uiState'

const TOGGLES: { key: keyof LayerToggles; label: string; hint: string }[] = [
  { key: 'stops', label: 'Stops', hint: '' },
  {
    key: 'clusterStops',
    label: 'Group nearby stops',
    hint: 'Supercluster, computed in the browser for the visible area',
  },
  { key: 'vehicles', label: 'Buses', hint: '' },
  {
    key: 'clusterVehicles',
    label: 'Group nearby buses',
    hint: 'MapLibre’s built-in clustering, computed in a web worker',
  },
]

const THEMES: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

export function LayersPanel() {
  const { layers, theme } = useUiState()
  const dispatch = useUiDispatch()

  return (
    <div className="panel">
      <fieldset className="fieldset">
        <legend className="panel__heading">Map layers</legend>
        {TOGGLES.map((toggle) => {
          const disabled =
            (toggle.key === 'clusterStops' && !layers.stops) ||
            (toggle.key === 'clusterVehicles' && !layers.vehicles)
          return (
            <label key={toggle.key} className="checkbox" data-indent={toggle.key.startsWith('cluster')}>
              <input
                type="checkbox"
                checked={layers[toggle.key]}
                disabled={disabled}
                onChange={() => dispatch({ type: 'toggleLayer', layer: toggle.key })}
              />
              <span>
                {toggle.label}
                {toggle.hint && <span className="checkbox__hint">{toggle.hint}</span>}
              </span>
            </label>
          )
        })}
      </fieldset>

      <fieldset className="fieldset">
        <legend className="panel__heading">Theme</legend>
        <div className="segmented">
          {THEMES.map((option) => (
            <label key={option.value} className="segmented__option">
              <input
                type="radio"
                name="theme"
                value={option.value}
                checked={theme === option.value}
                onChange={() => dispatch({ type: 'setTheme', theme: option.value })}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <section>
        <h2 className="panel__heading">Keyboard</h2>
        <dl className="shortcuts">
          <dt><kbd>/</kbd></dt>
          <dd>Search</dd>
          <dt><kbd>Esc</kbd></dt>
          <dd>Clear selection and close popups</dd>
          <dt><kbd>[</kbd></dt>
          <dd>Show or hide this panel</dd>
        </dl>
      </section>

      <section>
        <h2 className="panel__heading">About the data</h2>
        <p className="small muted">
          Live positions come from Föli’s open data, refreshed every 5 seconds through our server.
          They are Föli’s estimates from odometer, GPS and timing, not raw GPS: a bus can appear a few
          seconds off, may be snapped to its planned route during a detour, and can drop out where the
          mobile network is weak. Buses drawn in grey belong to lines missing from the timetable data.
        </p>
      </section>
    </div>
  )
}
