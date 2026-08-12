from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_name: str
    db_user: str
    db_password: SecretStr
    db_host: str
    db_port: int = 5432

    app_name: str = "AI Research Assistant API"
    app_version: str = "3.0.0-dev"

    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "cpu"
    embedding_dimension: int = 384
    embedding_batch_size: int = 32

    # ANN index runtime tuning. Kept >= SearchParams.limit ceiling (100) so that
    # the HNSW candidate pool is never narrower than the number of rows a caller
    # can legally request. Nothing enforces that coupling — see 🎯 below.
    hnsw_ef_search: int = 100

    @property
    def database_url(self) -> str:
        """Construct database connection DSN string."""
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password.get_secret_value())
        return f"postgresql://{user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    return Settings()