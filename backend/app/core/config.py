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

    # ── AI (LLM) ────────────────────────────────────────────
    # Provider ativo: mock | ollama | openai. Mock é o default seguro
    # (dev/testes); produção define ollama (ou openai via API key).
    ai_provider: str = os.getenv("AI_PROVIDER", "mock")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    ai_timeout_seconds: int = int(os.getenv("AI_TIMEOUT_SECONDS", "60"))
    ai_max_tokens: int = int(os.getenv("AI_MAX_TOKENS", "2048"))
    ai_temperature: float = float(os.getenv("AI_TEMPERATURE", "0.3"))

    # ── Speech-to-Text / Text-to-Speech ─────────────────────
    # STT: mock | whisper (CLI). TTS: mock | piper (CLI).
    stt_provider: str = os.getenv("STT_PROVIDER", "mock")
    tts_provider: str = os.getenv("TTS_PROVIDER", "mock")
    whisper_model: str = os.getenv("WHISPER_MODEL", "base")
    piper_voice: str = os.getenv("PIPER_VOICE", "pt_BR-faber-medium")
    piper_executable: str = os.getenv("PIPER_EXECUTABLE", "/usr/local/bin/piper")
    piper_models_dir: str = os.getenv("PIPER_MODELS_DIR", "/models")

    # ── Scaling / Rate Limiting ─────────────────────────────
    # backend do rate limiter: memory (default, single worker) |
    # redis (compartilhado entre workers/instâncias — produção).
    rate_limit_mode: str = os.getenv("RATE_LIMIT_MODE", "memory")
    rate_limit_redis_url: str = os.getenv("RATE_LIMIT_REDIS_URL", "redis://localhost:6379/0")

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
        if not admin_pw:
            raise ValueError(
                "ADMIN_PASSWORD environment variable is required. "
                "Set it to a strong password before starting the server. "
                "Example: export ADMIN_PASSWORD=your_secure_password"
            )

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