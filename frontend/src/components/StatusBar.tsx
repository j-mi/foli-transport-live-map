import type { UpstreamStatus } from '../api/types'
import { formatAge, formatDuration } from '../format'
import { useVehicleStats } from '../hooks/useVehicleStream'
import type { StreamStats } from '../realtime/vehicleStream'

type Tone = 'ok' | 'info' | 'warning'

interface Summary {
  tone: Tone
  label: string
  message: string | null
}

const UPSTREAM_MESSAGES: Partial<Record<UpstreamStatus, string>> = {
  PENDING: 'Föli is starting up; live positions will appear shortly.',
  NO_DATA: 'Föli is not publishing live data right now.',
  DOWN: 'Föli is not responding.',
}

/** Turns transport state + data age + upstream status into one honest, plain-language line. */
export function summarise(stats: StreamStats): Summary {
  const upstream = stats.upstreamStatus ? UPSTREAM_MESSAGES[stats.upstreamStatus] ?? null : null
  const showingOld =
    stats.isStale && stats.ageSeconds !== null
      ? `Showing positions from ${formatDuration(stats.ageSeconds)} ago.`
      : null

  switch (stats.connection) {
    case 'connecting':
      return { tone: 'info', label: 'Connecting…', message: upstream }
    case 'reconnecting':
      return {
        tone: 'warning',
        label: 'Reconnecting…',
        message: showingOld ?? 'Lost connection to the server.',
      }
    case 'stale':
      return {
        tone: 'warning',
        label: 'Live data unavailable',
        message: [upstream, showingOld].filter(Boolean).join(' ') || null,
      }
    case 'polling':
      return {
        tone: upstream ? 'warning' : 'ok',
        label: 'Live (polling)',
        message: upstream ?? 'Streaming is blocked on this network; checking every 5 s instead.',
      }
    case 'live':
      return { tone: upstream ? 'warning' : 'ok', label: 'Live', message: upstream }
  }
}

export function StatusBar() {
  // Re-renders at most once per second (the stats tick), and only this component.
  const stats = useVehicleStats((s) => s)
  const summary = summarise(stats)

  return (
    <footer className="status-bar" data-tone={summary.tone}>
      <span className="status-bar__dot" aria-hidden="true" />
      {/* Only the state is announced to screen readers, not the ticking counters. */}
      <span className="status-bar__label" role="status" aria-live="polite">
        {summary.label}
      </span>
      <span className="status-bar__sep" aria-hidden="true">
        ·
      </span>
      <span className="tabular">
        {stats.vehicleCount} {stats.vehicleCount === 1 ? 'bus' : 'buses'}
      </span>
      {stats.ageSeconds !== null && (
        <>
          <span className="status-bar__sep" aria-hidden="true">
            ·
          </span>
          <span className="tabular">updated {formatAge(stats.ageSeconds)}</span>
        </>
      )}
      {summary.message && <span className="status-bar__message">{summary.message}</span>}
    </footer>
  )
}
