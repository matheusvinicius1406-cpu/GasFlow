"""
GasFlow — Application Configuration

Environment-specific settings loaded from environment variables.
Defaults are safe for development. Production must override via env vars.
"""

import os
from pydantic import BaseModel
from typing import List


class Settings(BaseModel):
    app_name: str = "GasFlow"
    app_version: str = "0.1.0"

    # Environment
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # Database
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./gasflow.db")

    # Auth / Security
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    session_ttl_minutes: int = int(os.getenv("SESSION_TTL_MINUTES", "60"))
    max_failed_attempts: int = int(os.getenv("MAX_FAILED_ATTEMPTS", "5"))
    lockout_minutes: int = int(os.getenv("LOCKOUT_MINUTES", "15"))

    # CORS
    cors_origins: List[str] = []
    cors_methods: List[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    cors_headers: List[str] = ["Authorization", "Content-Type", "Accept"]

    # External Services
    whatsapp_service_url: str = os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3000")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def from_env(cls):
        """Load settings from environment variables."""
        origins_str = os.getenv("CORS_ORIGINS", "")
        if origins_str:
            origins = [o.strip() for o in origins_str.split(",") if o.strip()]
        else:
            origins = [
                "http://localhost",
                "http://localhost:3000",
                "http://localhost:3001",
                "http://localhost:5173",
                "http://localhost:8080",
                "http://127.0.0.1",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3001",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:8080",
            ]

        env = os.getenv("ENVIRONMENT", "development")

        env = os.getenv("ENVIRONMENT", "development")
        admin_pw = os.getenv("ADMIN_PASSWORD", "")
        if env == "production" and not admin_pw:
            raise ValueError(
                "ADMIN_PASSWORD environment variable is required in production. "
                "Set it to a strong password before starting the server."
            )
        if not admin_pw:
            admin_pw = "admin123"  # Dev-only fallback

        return cls(
            environment=env,
            debug=os.getenv("DEBUG", "false").lower() in ("true", "1", "yes"),
            database_url=os.getenv("DATABASE_URL", "sqlite:///./gasflow.db"),
            admin_password=admin_pw,
            cors_origins=origins,
            whatsapp_service_url=os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3000"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            session_ttl_minutes=int(os.getenv("SESSION_TTL_MINUTES", "60")),
        )


settings = Settings.from_env()