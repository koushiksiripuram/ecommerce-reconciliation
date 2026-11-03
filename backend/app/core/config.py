"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the backend service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "E-commerce Reconciliation API"
    environment: str = "development"
    debug: bool = True

    # API
    api_prefix: str = "/api"

    # CORS: comma separated list of allowed origins for the frontend
    cors_origins: list[str] = ["http://localhost:5173"]

    # Database
    #
    # Hosted providers usually expose a single connection string. When
    # DATABASE_URL is set it takes precedence over the discrete POSTGRES_*
    # variables below, which remain useful for local/managed setups.
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "reconciliation"

    @property
    def database_url(self) -> str:
        """Return the SQLAlchemy connection URL for PostgreSQL."""
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
