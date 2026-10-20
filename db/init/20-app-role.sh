#!/bin/sh
# Runs once, when the database volume is first initialised (postgres image entrypoint).
#
# Least privilege: the API connects as APP_DB_USER, which can read and write rows but cannot
# create, alter or drop tables. Schema changes run as POSTGRES_USER (the table owner) through
# Alembic. If the API were ever compromised, it could not drop the schema.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_user="$APP_DB_USER" -v app_password="$APP_DB_PASSWORD" \
  -v db="$POSTGRES_DB" -v owner="$POSTGRES_USER" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE :"db" TO :"app_user";
GRANT USAGE ON SCHEMA public TO :"app_user";
-- Tables created later by the owner (i.e. by migrations) get these grants automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";
SQL
