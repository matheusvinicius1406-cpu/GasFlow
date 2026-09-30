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
    app_version: str = "1.1.7"

    # Environment
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # Database
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./gasflow.db")

    # Auth / Security
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    # Secret HS256 do access token do app do entregador (mini-JWT 15 min).
    # OBRIGATÓRIO em produção (ver app/presentation/api/driver_mobile_auth.py):
    # env MOBILE_JWT_SECRET (≥32 bytes) ou MOBILE_JWT_SECRET_FILE. Sem nada,
    # dev gera/persiste um secret aleatório fora do repo; produção falha alto.
    mobile_jwt_secret: str = os.getenv("MOBILE_JWT_SECRET", "")
    # Secret HS256 do access token do OPERADOR (B5). Dedicado e distinto do
    # mobile: um token do app do entregador nunca é assinado com a chave do
    # console. Mesma regra de resolução e de produção do mobile
    # (env OPERATOR_JWT_SECRET ou OPERATOR_JWT_SECRET_FILE, ≥32 bytes).
    operator_jwt_secret: str = os.getenv("OPERATOR_JWT_SECRET", "")
    session_ttl_minutes: int = int(os.getenv("SESSION_TTL_MINUTES", "60"))
    max_failed_attempts: int = int(os.getenv("MAX_FAILED_ATTEMPTS", "5"))
    lockout_minutes: int = int(os.getenv("LOCKOUT_MINUTES", "15"))

    # CORS
    cors_origins: List[str] = []
    cors_methods: List[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    cors_headers: List[str] = ["Authorization", "Content-Type", "Accept"]
    # F10.2: origem extra da página pública de cadastro (Vercel). Separada de
    # CORS_ORIGINS (apis admin) para poder liberar só o domínio público.
    public_signup_origins: List[str] = [
        o.strip() for o in os.getenv("PUBLIC_SIGNUP_ORIGINS", "").split(",") if o.strip()
    ]

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
    # Kill switch de emergência via env (o toggle do admin vive no quadro de
    # configurações — system_settings chave ai.enabled, default True). O env
    # só é consultado quando o quadro não está disponível.
    ai_enabled: bool = os.getenv("AI_ENABLED", "true").strip().lower() in ("1", "true", "yes")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    # Modo thinking (qwen3): false desliga (recomendado — sem isso o budget de
    # tokens é queimado no campo `thinking` e o `content` volta vazio);
    # true liga; "auto" omite o campo (server default, p/ modelos sem thinking).
    _ollama_think_raw: str = os.getenv("OLLAMA_THINK", "false").strip().lower()
    ollama_think: bool | None = None if _ollama_think_raw == "auto" else _ollama_think_raw in ("1", "true", "yes")
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

    # ── Entrega inteligente (Fases 8–10) ───────────────────
    # Fase 8 — sequenciamento de rota (OR-Tools). Desligada (default), o
    # endpoint POST /delivery/route/optimize responde 409 em vez de silenciar:
    # quem pediu algo desligado precisa saber que está desligado.
    delivery_smart_routing_enabled: bool = os.getenv("DELIVERY_SMART_ROUTING_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    # Fase 9 — score de despacho extraído (DispatchScorer). Desligada (default),
    # /delivery/dispatch/suggest mantém exatamente o cálculo inline de hoje.
    delivery_smart_dispatch_enabled: bool = os.getenv("DELIVERY_SMART_DISPATCH_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    # Fase 10 — provedor de roteamento: haversine (default, zero infra, em
    # memória) | osrm (opt-in, self-hosted, ver docs/routing/osrm.md).
    routing_provider: str = os.getenv("ROUTING_PROVIDER", "haversine").strip().lower()
    osrm_base_url: str = os.getenv("OSRM_BASE_URL", "").strip()
    # Timeout curto: o provider é otimização, não caminho crítico.
    osrm_timeout_seconds: float = float(os.getenv("OSRM_TIMEOUT_SECONDS", "2"))
    # Circuit breaker: após N falhas seguidas o OSRM fica de fora por M segundos
    # (evita pagar o timeout em toda request quando o serviço está caído).
    osrm_breaker_failures: int = int(os.getenv("OSRM_BREAKER_FAILURES", "3"))
    osrm_breaker_cooldown_s: int = int(os.getenv("OSRM_BREAKER_COOLDOWN_S", "60"))
    # Velocidade média assumida quando não há provedor de malha viária (km/h).
    # Mesmo valor do fallback do ETA (Fase 7.1) para as duas estimativas
    # contarem a mesma história.
    routing_default_speed_kmh: float = float(os.getenv("ROUTING_DEFAULT_SPEED_KMH", "28"))
    # Pesos do DispatchScorer (Fase 9). Rebalanceados na hora do score, então
    # mudar um peso não exige mexer nos outros.
    dispatch_weight_proximity: float = float(os.getenv("DISPATCH_WEIGHT_PROXIMITY", "0.45"))
    dispatch_weight_load: float = float(os.getenv("DISPATCH_WEIGHT_LOAD", "0.25"))
    dispatch_weight_deadline: float = float(os.getenv("DISPATCH_WEIGHT_DEADLINE", "0.20"))
    dispatch_weight_fairness: float = float(os.getenv("DISPATCH_WEIGHT_FAIRNESS", "0.10"))
    # Fase 9: entregas concorrentes que "enchem" o entregador (denominador do
    # load). Configurável para calibrar à realidade da frota sem misturar unidades
    # (não usa capacidade de estoque aqui — isso já é gate de elegibilidade).
    dispatch_load_full_deliveries: float = float(os.getenv("DISPATCH_LOAD_FULL_DELIVERIES", "4"))

    # ── Geocoding de contatos (.vcf) — Fase 2 §7 / ADR-0004 ───────
    # Liga/desliga o renomeador inteiro (D13). Desligado, os endpoints
    # respondem 409 em vez de silenciar: quem pediu algo desligado precisa
    # saber que está desligado (mesma regra do smart routing, Fase 8).
    contact_renamer_enabled: bool = os.getenv("CONTACT_RENAMER_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    geocoding_enabled: bool = os.getenv("GEOCODING_ENABLED", "true").strip().lower() in ("1", "true", "yes")
    # nominatim (default, público e sem chave) | photon (self-host) | mock.
    geocoding_provider: str = os.getenv("GEOCODING_PROVIDER", "nominatim").strip().lower()
    geocoding_base_url: str = os.getenv("GEOCODING_BASE_URL", "https://nominatim.openstreetmap.org").strip()
    geocoding_timeout_s: float = float(os.getenv("GEOCODING_TIMEOUT_S", "10"))
    # O Nominatim público EXIGE User-Agent identificando a aplicação (política
    # de uso); sem ele a própria instância bloqueia as requisições.
    geocoding_user_agent: str = os.getenv("GEOCODING_USER_AGENT", "GasFlow/1.1.7 (contatos .vcf)")
    # Teto da política do Nominatim público: 1 requisição por segundo.
    geocoding_rate_limit_s: float = float(os.getenv("GEOCODING_RATE_LIMIT_S", "1.0"))
    geocoding_max_attempts: int = int(os.getenv("GEOCODING_MAX_ATTEMPTS", "3"))
    # Circuit breaker: MESMA classe do OSRM (infrastructure/routing/circuit_breaker.py)
    # — provedor público fora do ar não pode fazer cada rua pagar o timeout
    # inteiro de novo. Defaults espelham os do OSRM de propósito.
    geocoding_breaker_failures: int = int(os.getenv("GEOCODING_BREAKER_FAILURES", "3"))
    geocoding_breaker_cooldown_s: int = int(os.getenv("GEOCODING_BREAKER_COOLDOWN_S", "60"))
    # ViaCEP só como fallback de CEP, e só quando houver cidade/uf (é indexado
    # por CEP, não por endereço).
    # (busca por endereço → CEP; abre a cadeia do fallback de CEP abaixo)
    viacep_enabled: bool = os.getenv("VIACEP_ENABLED", "true").strip().lower() in ("1", "true", "yes")
    viacep_base_url: str = os.getenv("VIACEP_BASE_URL", "https://viacep.com.br").strip()
    # ── Fallback de CEP → endereço/coordenada (etapa 9) ────────────
    # Segundo elo do geocode (D2): quando o provedor NÃO conhece o logradouro,
    # o CEP ainda resolve endereço e coordenada. Cadeia fixa, testada no
    # endereço de aceite (CEP 66811-120): BrasilAPI (MIT, keyless, devolve
    # `location.coordinates`) → PontoFato (keyless, lat/lon do CNEFE/IBGE).
    # Sem chave comercial e sem Overpass.
    cep_fallback_enabled: bool = os.getenv("CEP_FALLBACK_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    brasilapi_enabled: bool = os.getenv("BRASILAPI_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    brasilapi_base_url: str = os.getenv("BRASILAPI_BASE_URL", "https://brasilapi.com.br").strip()
    pontofato_enabled: bool = os.getenv("PONTOFATO_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    pontofato_base_url: str = os.getenv("PONTOFATO_BASE_URL", "https://pontofato.com").strip()
    # Raio (metros) da busca das vias que cruzam o logradouro (etapa 6/Overpass).
    entre_ruas_radius_m: int = int(os.getenv("ENTRE_RUAS_RADIUS_M", "150"))
    # ── Overpass — passe próprio (D14: FORA do geocode frio) ───────
    # NÃO é o mesmo host do Nominatim nem o mesmo orçamento: cada rua paga um
    # passe a parte (etapa 8), com contagem e retomada próprias.
    overpass_base_url: str = os.getenv("OVERPASS_BASE_URL", "https://overpass-api.de/api/interpreter").strip()
    overpass_enabled: bool = os.getenv("OVERPASS_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    overpass_timeout_s: float = float(os.getenv("OVERPASS_TIMEOUT_S", "30"))
    # O Overpass público devolve 504/429 em rajada (medido no spike §8.0): o
    # retry importa mais aqui do que o número de ruas.
    overpass_max_attempts: int = int(os.getenv("OVERPASS_MAX_ATTEMPTS", "3"))
    overpass_rate_limit_s: float = float(os.getenv("OVERPASS_RATE_LIMIT_S", "1.0"))

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
            # F10.4: mesmo campo documentado acima — explícito aqui para o
            # valor seguir CORS_ORIGINS no from_env (e não só no default).
            public_signup_origins=[o.strip() for o in os.getenv("PUBLIC_SIGNUP_ORIGINS", "").split(",") if o.strip()],
            whatsapp_service_url=os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3000"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            session_ttl_minutes=int(os.getenv("SESSION_TTL_MINUTES", "60")),
        )


settings = Settings.from_env()
