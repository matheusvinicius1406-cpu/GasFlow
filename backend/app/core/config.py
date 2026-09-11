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
    # Chave compartilhada service-to-service (whatsapp → backend). Aceita
    # MARCOS_GAS_API_KEY (legado) ou WHATSAPP_SERVICE_KEY. Vazio = chamadas
    # de serviço desabilitadas (apenas usuários autenticados via Bearer).
    whatsapp_service_key: str = os.getenv("WHATSAPP_SERVICE_KEY", os.getenv("MARCOS_GAS_API_KEY", ""))

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

    # ── PIX PSP ──────────────────────────────────────────────
    # Provedor de pagamentos PIX: mock (default) | gerencianet | pagseguro |
    # mercadopago. Providers reais exigem PSP_API_URL + PSP_API_KEY.
    psp_provider: str = os.getenv("PSP_PROVIDER", "mock")
    psp_api_url: str = os.getenv("PSP_API_URL", "")
    psp_api_key: str = os.getenv("PSP_API_KEY", "")
    psp_client_id: str = os.getenv("PSP_CLIENT_ID", "")
    psp_client_secret: str = os.getenv("PSP_CLIENT_SECRET", "")
    # Secret compartilhado p/ assinar/verificar webhooks do PSP. Vazio =
    # webhook PIX desabilitado (503) — nunca aceitar confirmação sem assinatura.
    psp_webhook_secret: str = os.getenv("PSP_WEBHOOK_SECRET", "")

    # ── Scaling / Rate Limiting ─────────────────────────────
    # backend do rate limiter: memory (default, single worker) |
    # redis (compartilhado entre workers/instâncias — produção).
    rate_limit_mode: str = os.getenv("RATE_LIMIT_MODE", "memory")
    rate_limit_redis_url: str = os.getenv("RATE_LIMIT_REDIS_URL", "redis://localhost:6379/0")

    # ── Approval queue (automações de alto risco) ───────────
    # backend da fila de aprovações: memory (default, single worker) |
    # redis (compartilhado entre workers/instâncias — produção).
    # Aprovações pendentes não podem desaparecer num restart nem ficar
    # presas no worker que as criou (ver policy.py / automation.py).
    approval_queue_mode: str = os.getenv("APPROVAL_QUEUE_MODE", "memory")
    approval_queue_redis_url: str = os.getenv(
        "APPROVAL_QUEUE_REDIS_URL",
        os.getenv("RATE_LIMIT_REDIS_URL", "redis://localhost:6379/0"),
    )

    # ── Realtime (WebSocket cross-worker) ──────────────────
    # propagação entre workers: memory (default, 1 worker/processo) |
    # redis (compartilha eventos entre workers via pub/sub — multi-worker).
    realtime_backend: str = os.getenv("REALTIME_BACKEND", "memory")
    # Herda a URL do rate limiter quando REALTIME_REDIS_URL não é definida —
    # evita o default localhost silencioso em produção (lição do GOLDEN).
    realtime_redis_url: str = os.getenv(
        "REALTIME_REDIS_URL",
        os.getenv("RATE_LIMIT_REDIS_URL", "redis://localhost:6379/0"),
    )

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
