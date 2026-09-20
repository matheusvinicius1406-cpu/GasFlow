"""
Status do agente de impressão — estado compartilhado entre workers (F10.7).

`POST /printer/agent/status` (app desktop) grava; `GET /printer/status` (tela do
operador) lê. Em memória de processo isso só é verdade com UM worker: prod roda
`BACKEND_WORKERS=2` (docker-compose.prod.yml) e as duas requisições podem cair em
workers diferentes — a tela oscilava entre "Pronta" e "Não configurada" sem
padrão, e um erro de impressora podia nunca aparecer.

Mesmo padrão de `app/core/whatsapp_limits.py` e `approval_redis.py`: **Redis
quando `RATE_LIMIT_MODE=redis`** (mesma infra já configurada em prod, sem env var
nova), **fallback in-memory**. O status é informativo → degradar para memória de
um worker é melhor que derrubar a requisição.

TTL: o que foi reportado expira (Redis `EX` / carimbo de tempo na memória). App
fechado some da tela em vez de ficar "Pronta" para sempre. Antes disso o payload
já traz `stale` — o worker faz poll a cada 3s, então 30s de silêncio é anomalia
e a tela avisa em vez de prometer impressão.
"""

import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logging import setup_logging

logger = setup_logging("INFO")

STATUS_KEY = "printer:agent:status"
# Status mais velho que isto é descartado (app fechado não deixa "Pronta" no ar).
STATUS_TTL_SECONDS = 300
# Poll do agente é 3s: 30s sem sinal é "o app parou", não "rede lenta".
STALE_AFTER_SECONDS = 30

# Nada nunca reportado — mesmo default de quando o agente nunca falou.
NEVER_REPORTED: Dict[str, Any] = {
    "status": "NOT_CONFIGURED",
    "printer_name": None,
    "detail": "",
    "reported_at": None,
}


def _is_stale(reported_at: Optional[str]) -> bool:
    """True quando o último relato é velho demais (ou inexistente)."""
    if not reported_at:
        return True
    try:
        reported = datetime.fromisoformat(reported_at)
    except (TypeError, ValueError):
        return True
    return (datetime.utcnow() - reported).total_seconds() > STALE_AFTER_SECONDS


class _MemoryStore:
    """Último relato neste processo, com o mesmo TTL do Redis."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._raw: Optional[str] = None
        self._at = 0.0

    def set(self, raw: str) -> None:
        with self._lock:
            self._raw = raw
            self._at = time.time()

    def get(self) -> Optional[str]:
        with self._lock:
            if self._raw is None or (time.time() - self._at) > STATUS_TTL_SECONDS:
                return None
            return self._raw


class PrinterStatusStore:
    """KV de um único registro: o último estado reportado pelo agente."""

    def __init__(self, url: Optional[str] = None) -> None:
        self._memory = _MemoryStore()
        self._url = url or getattr(settings, "rate_limit_redis_url", "redis://localhost:6379/0")
        self._client = None
        self._redis_ok: Optional[bool] = None
        self._checked_at = 0.0

    def _redis(self):
        """Cliente Redis quando configurado e respondendo; senão None.

        Circuit breaker curto (mesmo espírito do rate limiter/approval): não
        paga o timeout de conexão em cada requisição quando o Redis caiu.
        """
        if getattr(settings, "rate_limit_mode", "memory") != "redis":
            return None
        now = time.time()
        if now < self._checked_at:
            return self._client if self._redis_ok else None
        self._checked_at = now + 5
        try:
            if self._client is None:
                import redis

                self._client = redis.Redis.from_url(self._url, socket_connect_timeout=1.5, socket_timeout=1.5)
            self._client.ping()
            self._redis_ok = True
            return self._client
        except Exception:  # noqa: BLE001 — status é informativo
            self._redis_ok = False
            logger.warning("printer_status: Redis indisponível — status restrito a este worker")
            return None

    def report(self, status: str, printer_name: Optional[str], detail: str = "") -> Dict[str, Any]:
        payload = {
            "status": status,
            "printer_name": printer_name,
            "detail": detail,
            "reported_at": datetime.utcnow().isoformat(),
        }
        raw = json.dumps(payload, ensure_ascii=False)
        client = self._redis()
        if client is not None:
            try:
                client.set(STATUS_KEY, raw, ex=STATUS_TTL_SECONDS)
                return {**payload, "stale": False}
            except Exception:  # noqa: BLE001
                logger.warning("printer_status: falha ao gravar no Redis — memória local")
        self._memory.set(raw)
        return {**payload, "stale": False}

    def get(self) -> Dict[str, Any]:
        raw: Optional[str] = None
        client = self._redis()
        if client is not None:
            try:
                value = client.get(STATUS_KEY)
                raw = value.decode("utf-8") if isinstance(value, bytes) else value
            except Exception:  # noqa: BLE001
                logger.warning("printer_status: falha ao ler do Redis — memória local")
        if raw is None:
            raw = self._memory.get()
        if raw is None:
            # Nunca reportou (ou o TTL venceu): a tela precisa saber disso.
            return {**NEVER_REPORTED, "stale": True}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("printer_status: registro corrompido — tratando como ausente")
            return {**NEVER_REPORTED, "stale": True}
        return {**data, "stale": _is_stale(data.get("reported_at"))}


_store: Optional[PrinterStatusStore] = None
_store_lock = threading.Lock()


def get_printer_status_store() -> PrinterStatusStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = PrinterStatusStore()
        return _store


def report_agent_status(status: str, printer_name: Optional[str], detail: str = "") -> Dict[str, Any]:
    """Agente publica o estado AGORA (chamado por POST /printer/agent/status)."""
    return get_printer_status_store().report(status, printer_name, detail)


def get_agent_status() -> Dict[str, Any]:
    """Estado mais recente + `stale`.

    `stale=True` quando o último relato é velho demais (ou não existe) — a tela
    do operador usa isso para dizer "sem sinal do app" em vez de "Pronta".
    """
    return get_printer_status_store().get()
