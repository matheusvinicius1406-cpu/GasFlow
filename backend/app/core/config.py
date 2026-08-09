from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração da aplicação, carregada de variáveis de ambiente / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "GasFlow"
    app_version: str = "0.1.0"
    debug: bool = False

    database_url: str = "sqlite:///./gasflow.db"

    # Origens permitidas no CORS, separadas por vírgula.
    cors_origins: str = (
        "http://localhost,http://localhost:3000,"
        "http://localhost:5173,http://localhost:8080"
    )

    # Auth (usado a partir da Fase 2).
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # Infra opcional.
    redis_url: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
