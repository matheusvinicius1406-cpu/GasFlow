"""
WhatsApp Limits — F4.5: rate limit de auto-cadastro + cap de ofertas.

Resolve os dois TODOs de produção da F4.5:

1. **Rate limit do auto-cadastro por indicação** (tools_impl.py): o limite
   por **telefone** é o único efetivo no contexto WhatsApp — o IP não é
   extraído do webhook (a conexão vem do serviço WhatsApp Node, não do
   cliente final). O parâmetro `ip` do rate limiter é mantido para o
   futuro endpoint web público (fallback (b) do spec §5), mas é inócuo
   hoje; documentado como R1 (verificado).

2. **Cap de 1 oferta de cupom por conversa** (gateway.py): persistir entre
   reinícios do backend quando `RATE_LIMIT_MODE=redis`.

Ambos usam o mesmo padrão do rate limiter do core: **Redis quando
disponível (RATE_LIMIT_MODE=redis), fallback in-memory fail-open** —
se o Redis estiver fora, a memória local assume (limitação: contagem
por worker) em vez de derrubar a conversa. Mesma semântica de
`rate_limit.py`/`rate_limit_redis.py`, reusando o cliente/singleton.
"""

import threading
import time
from collections import defaultdict
from typing import Optional, Tuple

from app.core.logging import setup_logging
from app.core.config import settings

logger = setup_logging("INFO")

# ── Backend compartilhado (reusa o limiter do core) ────────────


def _get_redis_backend():
    """Retorna o limiter Redis do core quando o modo é 'redis'; None caso contrário.

    Import tardio: evita dependência de Redis em dev/testes (o cliente é
    lazy no RedisSlidingWindowRateLimiter, então nem conecta aqui).
    """
    if getattr(settings, "rate_limit_mode", "memory") != "redis":
        return None
    try:
        from app.core.rate_limit import _limiter  # singleton já configurado

        return _limiter if getattr(_limiter, "available", False) else None
    except Exception:
        return None


class _MemoryTTLStore:
    """Sliding-window in-memory (por worker) — fallback e modo 'memory'."""

    def __init__(self):
        self._events: dict = defaultdict(list)
        self._lock = threading.Lock()

    def count_and_record(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """Rate limit clássico: True se excedeu; retorna (excedeu, count)."""
        now = time.time()
        with self._lock:
            bucket = self._events[key]
            bucket[:] = [t for t in bucket if now - t < window_seconds]
            if len(bucket) >= max_requests:
                return True, len(bucket)
            bucket.append(now)
            return False, len(bucket)

    def is_marked(self, key: str, window_seconds: int) -> bool:
        """Consulta sem marcar (usado no cap para montar contexto da IA)."""
        now = time.time()
        with self._lock:
            bucket = self._events.get(key, [])
            return any(now - t < window_seconds for t in bucket)

    def mark(self, key: str, window_seconds: int) -> None:
        now = time.time()
        with self._lock:
            self._events[key].append(now)


class WhatsAppLimitStore:
    """Store TTL dos limites do WhatsApp — Redis compartilhado ou memória local.

    Interface única para os dois limites da F4.5:
    - Rate limit (count_and_record): N tentativas por janela.
    - Marcação única (mark/is_marked): cap 1 oferta de cupom por conversa.
    """

    def __init__(self):
        self._memory = _MemoryTTLStore()
        self._redis_checked_at = 0.0
        self._redis_probe_interval = 5.0

    def _backend(self):
        """Backend Redis vivo (com probe throttled) ou None → memória."""
        now = time.time()
        if now - self._redis_checked_at > self._redis_probe_interval:
            self._redis_checked_at = now
            self._redis = _get_redis_backend()
        return getattr(self, "_redis", None)

    # ── Rate limit (auto-cadastro) ─────────────────────────

    def allow(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """True se permitido dentro do limite; retorna (permitido, tentativas)."""
        backend = self._backend()
        if backend is not None:
            try:
                now = time.time()
                cutoff = now - window_seconds
                client = backend._connect() if hasattr(backend, "_connect") else backend._client
                client.zremrangebyscore(key, "-inf", cutoff)
                count = client.zcard(key)
                if count >= max_requests:
                    return False, int(count)
                member = f"{now:.6f}"
                client.zadd(key, {member: now})
                client.pexpire(key, int(window_seconds * 1000))
                return True, int(count) + 1
            except Exception:
                logger.warning("whatsapp_limits: Redis falhou no allow(%s) — memória", key)
        exceeded, count = self._memory.count_and_record(key, max_requests, window_seconds)
        return (not exceeded), count

    # ── Cap de oferta (marcação única) ─────────────────────

    def is_marked(self, key: str, window_seconds: int) -> bool:
        backend = self._backend()
        if backend is not None:
            try:
                client = backend._connect() if hasattr(backend, "_connect") else backend._client
                score = client.zscore(key, "marker")
                return score is not None and (time.time() - float(score)) < window_seconds
            except Exception:
                logger.warning("whatsapp_limits: Redis falhou no is_marked(%s) — memória", key)
        return self._memory.is_marked(key, window_seconds)

    def mark(self, key: str, window_seconds: int) -> None:
        backend = self._backend()
        if backend is not None:
            try:
                client = backend._connect() if hasattr(backend, "_connect") else backend._client
                client.zadd(key, {"marker": time.time()})
                client.pexpire(key, int(window_seconds * 1000))
                return
            except Exception:
                logger.warning("whatsapp_limits: Redis falhou no mark(%s) — memória", key)
        self._memory.mark(key, window_seconds)


# Singleton — mesmo padrão do rate limiter do core (uma instância por
# processo; Redis compartilha entre processos, memória não).
_store: Optional[WhatsAppLimitStore] = None
_store_lock = threading.Lock()


def get_whatsapp_limit_store() -> WhatsAppLimitStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = WhatsAppLimitStore()
    return _store


def reset_whatsapp_limit_store() -> None:
    """Reseta o singleton (testes)."""
    global _store
    with _store_lock:
        _store = None
