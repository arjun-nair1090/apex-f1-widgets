from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ponytail: SQLite default so the repo runs with zero infra; set DATABASE_URL to PostgreSQL in prod.
    database_url: str = "sqlite:///./apex.db"
    redis_url: str | None = None
    jolpica_base: str = "https://api.jolpi.ca/ergast/f1"
    openf1_base: str = "https://api.openf1.org/v1"
    openf1_token: str | None = None  # required by OpenF1 for real-time data during sessions
    api_key: str | None = None  # when set, every /api call needs X-API-Key
    rate_limit_per_minute: int = 120
    force_https: bool = False
    sync_minutes: int = 30
    live_poll_seconds: float = 4.0
    ingest_on_startup: bool = True
    background_jobs: bool = True  # ingest + live loops; set 0 on every replica but one
    extra_seasons: str = ""  # e.g. "2024,2025": past seasons for the Driver widget's season option


settings = Settings()
