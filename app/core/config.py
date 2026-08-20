from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    db_name: str
    db_user: str
    db_password: SecretStr
    db_host: str
    db_port: int = 5432

    app_name: str = "AI Research Assistant API"
    app_version: str = "4.0.0-dev"

    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "cpu"
    embedding_dimension: int = 384
    embedding_batch_size: int = 32

    # ANN index runtime tuning. Kept >= SearchParams.limit ceiling (100) so that
    # the HNSW candidate pool is never narrower than the number of rows a caller
    # can legally request. Nothing enforces that coupling — see 🎯 below.
    hnsw_ef_search: int = 100

    # --- LLM provider ---------------------------------------------------
    # Only values that change with the deployment environment live here.
    # max_tokens and temperature are call-site arguments, not config: they
    # vary by task, not by environment.
    llm_api_key: SecretStr
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_timeout_seconds: float = 30.0
    llm_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    return Settings()