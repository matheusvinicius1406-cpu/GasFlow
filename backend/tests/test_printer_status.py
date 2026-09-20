"""
F10.7 — status do agente de impressão (app/core/printer_status.py).

Cobre o que a tela do operador depende:
- Nunca reportado / report velho → `stale=True` (a tela diz "sem sinal" em vez
  de "Pronta").
- Report fresco → `stale=False`.
- TTL: o que expirou some (app fechado não deixa estado eterno).
- Modo Redis: o estado é COMPARTILHADO entre instâncias (workers diferentes),
  que é o motivo de o store existir.
- Redis fora: cai para memória sem derrubar a requisição.
"""

import json
import time
from datetime import datetime, timedelta

import pytest

from app.core import printer_status
from app.core.config import settings
from app.core.printer_status import (
    NEVER_REPORTED,
    PrinterStatusStore,
    _is_stale,
    get_agent_status,
    report_agent_status,
)


class FakeRedis:
    """Cliente mínimo do que o store usa (set com EX, get, ping)."""

    def __init__(self):
        self.data = {}

    def ping(self):
        return True

    def set(self, key, value, ex=None):
        self.data[key] = value
        return True

    def get(self, key):
        return self.data.get(key)


@pytest.fixture(autouse=True)
def _memory_mode(monkeypatch):
    """Por padrão os testes rodam no modo memória (sem Redis de verdade)."""
    monkeypatch.setattr(settings, "rate_limit_mode", "memory", raising=False)
    store = printer_status.get_printer_status_store()
    store._memory = printer_status._MemoryStore()
    store._client = None
    store._redis_ok = None
    store._checked_at = 0.0
    yield store


def _redis_store(monkeypatch, client) -> PrinterStatusStore:
    """Store em modo Redis com cliente injetado (sem tocar na rede)."""
    monkeypatch.setattr(settings, "rate_limit_mode", "redis", raising=False)
    store = PrinterStatusStore()
    store._client = client
    store._redis_ok = True
    store._checked_at = time.time() + 60  # pula o ping real
    return store


class TestStaleness:
    def test_never_reported_is_stale(self):
        status = get_agent_status()

        assert status["status"] == NEVER_REPORTED["status"]
        assert status["reported_at"] is None
        assert status["stale"] is True

    def test_fresh_report_is_not_stale(self):
        reported = report_agent_status("ONLINE", "GT710", "spooler ok")

        assert reported["stale"] is False
        status = get_agent_status()
        assert status["status"] == "ONLINE"
        assert status["printer_name"] == "GT710"
        assert status["stale"] is False

    def test_old_report_is_stale(self):
        """App fechado: o último estado fica no banco do store, mas com aviso."""
        old = (datetime.utcnow() - timedelta(seconds=120)).isoformat()
        raw = json.dumps({"status": "ONLINE", "printer_name": "GT710", "detail": "", "reported_at": old})
        printer_status.get_printer_status_store()._memory.set(raw)

        status = get_agent_status()

        assert status["printer_name"] == "GT710"
        assert status["stale"] is True

    def test_expired_report_disappears(self):
        """TTL: passado o prazo, é como se nunca tivesse reportado."""
        report_agent_status("ONLINE", "GT710")
        store = printer_status.get_printer_status_store()
        store._memory._at = time.time() - (printer_status.STATUS_TTL_SECONDS + 1)

        status = get_agent_status()

        assert status["reported_at"] is None
        assert status["stale"] is True

    @pytest.mark.parametrize("reported_at", [None, "", "não é data", "2026-13-45T99:99:99"])
    def test_unparseable_timestamp_is_stale(self, reported_at):
        assert _is_stale(reported_at) is True


class TestSharedAcrossWorkers:
    def test_redis_mode_is_visible_to_another_instance(self, monkeypatch):
        """Duas instâncias = dois workers do uvicorn: o que um grava o outro lê.

        Era exatamente isto que faltava: em memória, o POST caía no worker A e o
        GET podia ser atendido pelo B, que respondia "Não configurada".
        """
        client = FakeRedis()
        worker_a = _redis_store(monkeypatch, client)
        worker_b = _redis_store(monkeypatch, client)

        worker_a.report("ERROR", "GT710", "sem papel")

        status = worker_b.get()
        assert status["status"] == "ERROR"
        assert status["detail"] == "sem papel"
        assert status["stale"] is False

    def test_redis_writes_with_ttl(self, monkeypatch):
        client = FakeRedis()
        store = _redis_store(monkeypatch, client)

        store.report("ONLINE", "GT710")

        assert printer_status.STATUS_KEY in client.data

    def test_redis_failure_falls_back_to_memory(self, monkeypatch):
        """Status é informativo: Redis fora não pode derrubar o endpoint."""
        client = FakeRedis()

        def _boom(*_args, **_kwargs):
            raise RuntimeError("redis fora")

        client.set = _boom  # type: ignore[method-assign]
        store = _redis_store(monkeypatch, client)

        reported = store.report("ONLINE", "GT710", "ok")

        assert reported["stale"] is False
        assert store._memory.get() is not None, "deveria ter guardado na memória"
