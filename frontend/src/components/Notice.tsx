import { ApiError } from '../api/client'

/** Plain-language error with an optional retry. */
export function ErrorNotice({ error, what, onRetry }: { error: unknown; what: string; onRetry?: () => void }) {
  let detail = 'Please try again in a moment.'
  if (error instanceof ApiError) {
    if (error.code === 'GTFS_NOT_READY') detail = 'Timetable data is still loading from Föli.'
    else if (error.code === 'NETWORK_ERROR') detail = 'The server cannot be reached.'
    else if (error.status === 503) detail = 'Föli is not responding right now.'
  }
  return (
    <div className="notice notice--warning" role="alert">
      <p>
        Could not load {what}. {detail}
      </p>
      {onRetry && (
        <button type="button" className="button button--small" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}
