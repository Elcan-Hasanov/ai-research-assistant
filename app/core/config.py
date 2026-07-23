from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Veritabanı bağlantı bilgileri — .env'deki isimlerle birebir eşleşir
    db_name: str
    db_user: str
    db_password: str
    db_host: str
    db_port: int = 5432  # varsayılan değer, .env'de yoksa bu kullanılır

    # Uygulama metadata'sı (Adım 2'deki hardcoded değerleri buraya taşıyacağız)
    app_name: str = "ArXiv Research Assistant"
    app_version: str = "2.0.0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # DB_NAME, db_name, Db_Name hepsi eşleşir
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """
    Process boyunca tek bir Settings nesnesi döner (singleton davranışı).
    lru_cache sayesinde .env her çağrıda değil, sadece ilk çağrıda okunur.
    """
    return Settings()