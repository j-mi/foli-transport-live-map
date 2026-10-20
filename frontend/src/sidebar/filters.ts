import type { Line } from '../api/types'
import type { StopInfo } from '../hooks/useLookups'

const normalise = (text: string) => text.trim().toLocaleLowerCase('fi')

/** Line number prefix ("1" finds 1, 1A, 1T, 10...) or any part of the route name. */
export function filterLines(lines: Line[], query: string): Line[] {
  const q = normalise(query)
  if (!q) return lines
  return lines.filter(
    (line) => normalise(line.short_name).startsWith(q) || normalise(line.long_name).includes(q),
  )
}

const collator = new Intl.Collator('fi')

/** Stop code prefix or any part of the name; name matches that start with the query come first. */
export function filterStops(stops: StopInfo[], query: string): StopInfo[] {
  const q = normalise(query)
  const sorted = (list: StopInfo[]) => [...list].sort((a, b) => collator.compare(a.name, b.name))
  if (!q) return sorted(stops)
  const starts: StopInfo[] = []
  const contains: StopInfo[] = []
  for (const stop of stops) {
    const name = normalise(stop.name)
    if (name.startsWith(q) || stop.stop_id.toLowerCase().startsWith(q)) starts.push(stop)
    else if (name.includes(q)) contains.push(stop)
  }
  return [...sorted(starts), ...sorted(contains)]
}
