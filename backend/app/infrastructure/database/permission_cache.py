"""Cache em memória genérico, thread-safe, com TTL por chave.

Usado pelo PermissionPolicyLoader (3.2): evita query de permissões por
request; TTL curto + invalidação por evento `permissions.changed`.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable


class TTLCache:
    """Dict + timestamp, thread-safe, TTL por entrada. Sem dependências."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            return None  # expirado — get_or_load recarrega
        return value

    def set(self, key: str, value: Any, ttl_seconds: float = 60.0) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + ttl_seconds, value)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        """Invalida todas as chaves que começam com o prefixo."""
        with self._lock:
            stale = [k for k in self._store if k.startswith(prefix)]
            for k in stale:
                self._store.pop(k, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def get_or_load(self, key: str, loader: Callable[[], Any], ttl_seconds: float = 60.0) -> Any:
        """Retorna do cache; se ausente/expirado, carrega uma vez (single-flight)."""
        cached = self.get(key)
        if cached is not None:
            return cached
        with self._lock:
            # Double-check dentro do lock (single-flight por chave).
            entry = self._store.get(key)
            if entry is not None and time.monotonic() < entry[0]:
                return entry[1]
            value = loader()
            self._store[key] = (time.monotonic() + ttl_seconds, value)
            return value
