"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder used only for local development. Any non-development environment
# must provide a real JWT_SECRET_KEY, which `Settings` enforces below.
INSECURE_JWT_SECRET = "dev-insecure-secret-change-me-not-for-production"

# Environments where the placeholder secret is tolerated.
NON_PRODUCTION_ENVIRONMENTS = {"development", "local", "test"}


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

    # Authentication / JWT
    #
    # The secret is never hardcoded: it must be supplied through the
    # environment. The placeholder default keeps local development and the test
    # suite runnable, and is rejected outside development (see `_check_secret`).
    jwt_secret_key: str = INSECURE_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # The access token is delivered as an HttpOnly cookie so browser JavaScript
    # can never read it. Cookies are only sent cross-site when secure=True and
    # SameSite="none", so both are configurable per environment.
    auth_cookie_name: str = "access_token"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"

    # File imports
    #
    # Uploaded source files are written here verbatim so raw values can be
    # re-read for previews and re-processing. The directory is git-ignored.
    upload_storage_dir: str = "storage/uploads"
    max_upload_size_bytes: int = 10 * 1024 * 1024
    #: Rows returned by the preview endpoint.
    import_preview_rows: int = 20
    #: Rows written per database round trip while processing an import.
    import_batch_size: int = 500

    @model_validator(mode="after")
    def _check_secret(self) -> "Settings":
        """Refuse to start outside development with the placeholder secret."""
        if (
            self.jwt_secret_key == INSECURE_JWT_SECRET
            and self.environment.lower() not in NON_PRODUCTION_ENVIRONMENTS
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be set to a strong, unique value when "
                f"ENVIRONMENT is {self.environment!r}."
            )
        return self

    @property
    def database_url(self) -> str:
        """Return the SQLAlchemy connection URL for PostgreSQL."""
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def upload_storage_path(self) -> Path:
        """Directory where uploaded files are stored, resolved against the cwd."""
        return Path(self.upload_storage_dir).expanduser()


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
