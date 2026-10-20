import type { CSSProperties } from 'react'

/** A line number in Föli's own line colour (from GTFS), or neutral when unknown. */
export function LineBadge({
  name,
  color,
  textColor,
}: {
  name: string
  color?: string | null
  textColor?: string | null
}) {
  const style: CSSProperties | undefined = color
    ? { background: `#${color}`, color: `#${textColor ?? '000000'}` }
    : undefined
  return (
    <span className="line-badge" style={style}>
      {name}
    </span>
  )
}
