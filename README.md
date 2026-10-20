# Föli live map

Turku region (Föli) buses live on a map: clustering, a control sidebar, line highlighting,
saved favourites, "stops near here" and next departures.

- **Backend**: FastAPI integration layer. It polls Föli once every 5 s and fans the snapshot out
  to every browser over Server-Sent Events. Timeouts, retries with backoff and jitter, a circuit
  breaker, last-known-good data.
- **Database**: PostgreSQL + PostGIS for favourites and spatially indexed stop queries.
- **Frontend**: React + MapLibre GL. Stops are clustered with Supercluster in React; buses use
  MapLibre's built-in clustering. Live positions never pass through React state.

Diagrams of how data moves between Föli, the backend, the database and the map, including every
timeout and freshness limit, are in [docs/data-flow.html](docs/data-flow.html) (open it in a browser).

No API keys are needed: Föli open data and the OpenFreeMap basemap are both key-free.

## Run the full stack

```sh
cp .env.example .env        # optional; defaults work as-is
docker compose up --build
```

Open <http://localhost:8080>.

| Service    | What it does                                                | Port               |
|------------|-------------------------------------------------------------|--------------------|
| `db`       | PostGIS 16, named volume `pgdata`                           | 127.0.0.1:5432     |
| `backend`  | Runs `alembic upgrade head`, then Uvicorn                   | internal 8000      |
| `frontend` | nginx: static React build, proxies `/api` (SSE unbuffered)  | 8080               |

Favourites survive `docker compose down` / `up` because they live in the named volume.
`docker compose down -v` deletes the volume (and every favourite).

**Apple Silicon:** the official `postgis/postgis` image is amd64-only. Compose pins
`platform: linux/amd64`, so Docker Desktop runs it under emulation. It works, just a little slower.

## Local development

Prerequisites: Docker, Python 3.12+, Node.js 20.19+ (Vite 8 requirement).

```sh
cp .env.example .env
docker compose up -d db                      # database only

# Backend (http://localhost:8000, API docs at /api/v1/docs)
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head               # uses MIGRATIONS_DATABASE_URL from ../.env
.venv/bin/uvicorn app.main:app --reload

# Frontend (http://localhost:5173), in another terminal
cd frontend
npm install
npm run dev                                  # proxies /api to localhost:8000
```

The backend reads the repository-root `.env` when started from `backend/`. Inside compose it gets
its database URLs from `docker-compose.yml` instead.

## Tests and checks

```sh
cd backend
.venv/bin/pytest                 # 70 tests; the 8 marked `db` need `docker compose up -d db`
.venv/bin/ruff check . && .venv/bin/ruff format --check .

cd frontend
npm test                         # vitest
npm run typecheck                # tsc, strict
npm run lint                     # oxlint
```

Tests never call the live Föli API. They run against recorded samples in
`backend/tests/fixtures/`. To refresh the samples (for example when you suspect Föli changed a
response shape):

```sh
cd backend && .venv/bin/python scripts/fetch_fixtures.py && .venv/bin/pytest
```

Database tests create and migrate a separate `transport_test` database, so development data is
never touched. Override the connection with `TEST_DATABASE_ADMIN_URL`.

## API

All endpoints are under `/api/v1`. Errors share one shape:
`{"error": {"code": "STOP_NOT_FOUND", "message": "..."}}`.

| Method | Path                               | Purpose                                                  |
|--------|------------------------------------|----------------------------------------------------------|
| GET    | `/health`                          | DB, upstream status, GTFS dataset, poll metrics, SSE clients |
| GET    | `/lines`                           | All lines with Föli's colours                            |
| GET    | `/lines/{route_id}/shape`          | GeoJSON, one LineString per direction (most common shape) |
| GET    | `/stops`                           | All stops as GeoJSON                                     |
| GET    | `/stops/nearby?lat=&lon=&radius_m=` | PostGIS, nearest first                                  |
| GET    | `/stops/{stop_id}/departures`      | Next departures (SIRI SM), cached 15 s per stop          |
| GET    | `/vehicles`                        | Current snapshot (first paint, polling fallback)         |
| GET    | `/vehicles/stream`                 | SSE: `status` and `vehicles` events                      |
| GET    | `/favourites`                      | Saved stops and lines                                    |
| PUT    | `/favourites/stops/{stop_id}`      | Idempotent: 201 created, 200 already there               |
| DELETE | `/favourites/stops/{stop_id}`      | Idempotent: always 204                                   |
| PUT    | `/favourites/lines/{route_id}`     | Idempotent: 201 / 200                                    |
| DELETE | `/favourites/lines/{route_id}`     | Idempotent: always 204                                   |

Interactive docs: <http://localhost:8000/api/v1/docs> (local dev).

## Configuration

See [.env.example](.env.example).

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `transport` / `change_me` / `transport` | Database owner; used by migrations |
| `APP_DB_USER` / `APP_DB_PASSWORD` | `transport_app` / `change_me_app` | Least-privilege role the API uses (rows only, no DDL) |
| `DATABASE_URL`, `MIGRATIONS_DATABASE_URL` | localhost URLs | For running the backend on the host |
| `FOLI_BASE_URL` | `https://data.foli.fi` | |
| `POLL_INTERVAL_S` | `5` | Values below 3 are rejected (Föli's limit) |
| `GTFS_REFRESH_HOURS` | `6` | How often to check for a new GTFS dataset |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated |
| `VITE_MAP_STYLE_URL`, `VITE_MAP_STYLE_URL_DARK` | empty | Empty = OpenFreeMap positron / dark. Baked in at build time |

The app role is created by `db/init/20-app-role.sh`, which Postgres runs only when the volume
is first created. If you change `APP_DB_*` later, recreate the volume (`docker compose down -v`).

## Things worth knowing

- **MapLibre 6 web worker.** MapLibre finds its worker relative to its own file. Vite moves that
  file in both dev and production, so `src/map/maplibreWorker.ts` builds the worker with Vite
  and calls `setWorkerUrl()`. Without this the map stays blank.
- **Basemap labels.** Cluster counts and line numbers use the `Noto Sans` fonts served by
  OpenFreeMap. A custom `VITE_MAP_STYLE_URL` needs a glyph server with the same font names.
- **Data age uses the browser clock.** "Updated 3 s ago" compares the server's `fetched_at` with
  the viewer's clock. A badly wrong client clock skews it.
- **Single backend instance.** The poller and SSE fan-out live in one process. Several replicas
  would each poll Föli; the fix is one poller publishing through Redis pub/sub (not built).

## Spatial index check (Phase 5)

`EXPLAIN` for the nearby query is recorded here once it has been run against the full dataset:

```sh
docker compose exec db psql -U transport -d transport -c "EXPLAIN ANALYZE
SELECT stop_id FROM stops
WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(22.2666, 60.4518), 4326)::geography, 500);"
```

_Result: pending. It could not be run while this was written because Docker Desktop could not
pull images (see section 16.4 of the plan). The automated test
`test_the_spatial_index_can_serve_the_query` asserts that the index can serve this query shape._
