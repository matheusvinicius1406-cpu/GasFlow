"""Circuit breaker simples para o provedor OSRM (Fase 10).

Motivo: com o OSRM fora do ar, cada request pagaria o timeout inteiro antes de
cair para o cálculo local. O breaker corta isso depois de N falhas seguidas e
volta a sondar depois do cooldown — uma tentativa só, que fecha em caso de
sucesso e reabre imediatamente em caso de falha.
"""

from __future__ import annotations

import threading
import time
from typing import Callable


class CircuitBreaker:
    """Breaker thread-safe com estado closed / open / half-open."""

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._threshold = max(1, int(failure_threshold))
        self._cooldown_s = max(0.0, float(cooldown_s))
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._probing = False
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._opened_at is not None

    @property
    def failures(self) -> int:
        with self._lock:
            return self._failures

    def allow(self) -> bool:
        """True quando vale a pena tentar o serviço real.

        Deixa passar uma única tentativa (half-open) depois do cooldown.
        """
        with self._lock:
            if self._opened_at is None:
                return True
            if (self._clock() - self._opened_at) >= self._cooldown_s:
                self._probing = True
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._probing = False

    def record_failure(self) -> None:
        with self._lock:
            if self._probing:
                # A sondagem do half-open falhou: reabre sem esperar o limiar.
                self._probing = False
                self._failures = self._threshold
                self._opened_at = self._clock()
                return
            self._failures += 1
            if self._failures >= self._threshold:
                self._opened_at = self._clock()
