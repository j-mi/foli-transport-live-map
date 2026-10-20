#!/bin/sh
set -eu

# Migrations run with the owner role (MIGRATIONS_DATABASE_URL); the API itself connects with the
# least-privilege app role (DATABASE_URL). See db/init/20-app-role.sh.
echo "Running database migrations..."
alembic upgrade head

# --timeout-graceful-shutdown: open SSE streams would otherwise hold shutdown for a long time.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers \
  --forwarded-allow-ips='*' --timeout-graceful-shutdown 5
