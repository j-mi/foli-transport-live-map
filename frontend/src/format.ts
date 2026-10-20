// User-facing text formatting. Plain words, no jargon: "3 min late", "updated 5 s ago".

export function formatDelay(delaySeconds: number | null): string {
  if (delaySeconds === null) return 'No schedule information'
  const minutes = Math.round(delaySeconds / 60)
  if (minutes === 0) return 'On time'
  return minutes > 0 ? `${minutes} min late` : `${-minutes} min early`
}

export function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds} s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  return `${Math.floor(seconds / 3600)} h ago`
}

/** "positions from 40 s" / "positions from 2 min" — for "showing positions from … ago". */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`
  return `${Math.floor(seconds / 3600)} h`
}

export function formatDistance(metres: number): string {
  if (metres < 1000) return `${Math.round(metres / 10) * 10} m`
  return `${(metres / 1000).toFixed(1)} km`
}

// Buses run in Turku, so times are always shown in Finnish time, whatever the viewer's zone.
const clock = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'Europe/Helsinki',
})

export function formatClock(iso: string): string {
  return clock.format(new Date(iso))
}

/** "now", "in 4 min", or the clock time for departures further away. */
export function formatDeparture(iso: string, nowMs: number = Date.now()): string {
  const minutes = Math.round((Date.parse(iso) - nowMs) / 60_000)
  if (minutes <= 0) return 'now'
  if (minutes < 30) return `in ${minutes} min`
  return formatClock(iso)
}
