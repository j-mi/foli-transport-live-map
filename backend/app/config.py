"""Application settings, read from environment variables (and `.env` when present)."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Föli asks clients not to poll the SIRI VM endpoint faster than every 3 seconds.
# Its front server caches for 2 s anyway, so polling faster would only add load.
MIN_POLL_INTERVAL_S = 3.0


class Settings(BaseSettings):
    # One .env at the repository root serves both docker compose and a backend run from
    # backend/ on the host. Real environment variables always win over the file.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # Runtime connection, used by the API. In docker-compose this is a least-privilege role
    # that can read and write rows but cannot create or drop tables.
    database_url: str = "postgresql+asyncpg://transport_app:change_me_app@localhost:5432/transport"
    # Connection used by Alembic. Falls back to `database_url` when unset.
    migrations_database_url: str | None = None

    foli_base_url: str = "https://data.foli.fi"
    poll_interval_s: float = 5.0
    gtfs_refresh_hours: float = 6.0
    cors_origins: str = "http://localhost:5173"
    user_agent: str = "foli-live-map/0.1 (open source learning project; polls once per 5 s)"

    # Turn off in tests that construct the app without talking to Föli or the database.
    start_background_tasks: bool = True
    log_level: str = "INFO"

    @field_validator("poll_interval_s")
    @classmethod
    def _respect_provider_minimum(cls, value: float) -> float:
        if value < MIN_POLL_INTERVAL_S:
            raise ValueError(
                f"POLL_INTERVAL_S must be at least {MIN_POLL_INTERVAL_S} s (Föli's published limit)"
            )
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
