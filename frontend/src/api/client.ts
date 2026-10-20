import type {
  ApiErrorBody,
  DeparturesResponse,
  FavouriteLine,
  Favourites,
  FavouriteStop,
  LineShapeCollection,
  LinesResponse,
  NearbyStopsResponse,
  Snapshot,
  StopCollection,
} from './types'

export const API_BASE = '/api/v1'

/** Every failed call becomes an ApiError with the backend's stable error `code`. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as ApiErrorBody).error?.code === 'string'
  )
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', 'Could not reach the server.')
  }

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    if (isErrorBody(body)) {
      throw new ApiError(response.status, body.error.code, body.error.message)
    }
    throw new ApiError(response.status, `HTTP_${response.status}`, response.statusText)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

const seg = encodeURIComponent

export const api = {
  vehicles: () => request<Snapshot>('/vehicles'),
  lines: () => request<LinesResponse>('/lines'),
  lineShape: (routeId: string) => request<LineShapeCollection>(`/lines/${seg(routeId)}/shape`),
  stops: () => request<StopCollection>('/stops'),
  nearbyStops: (lat: number, lon: number, radiusM: number) =>
    request<NearbyStopsResponse>(
      `/stops/nearby?${new URLSearchParams({
        lat: lat.toFixed(6),
        lon: lon.toFixed(6),
        radius_m: String(radiusM),
      })}`,
    ),
  departures: (stopId: string) => request<DeparturesResponse>(`/stops/${seg(stopId)}/departures`),
  favourites: () => request<Favourites>('/favourites'),
  // PUT is idempotent: saving the same favourite twice never creates a duplicate, so retrying
  // after a timeout is always safe.
  addFavouriteStop: (stopId: string) =>
    request<FavouriteStop>(`/favourites/stops/${seg(stopId)}`, { method: 'PUT' }),
  removeFavouriteStop: (stopId: string) =>
    request<void>(`/favourites/stops/${seg(stopId)}`, { method: 'DELETE' }),
  addFavouriteLine: (routeId: string) =>
    request<FavouriteLine>(`/favourites/lines/${seg(routeId)}`, { method: 'PUT' }),
  removeFavouriteLine: (routeId: string) =>
    request<void>(`/favourites/lines/${seg(routeId)}`, { method: 'DELETE' }),
}
