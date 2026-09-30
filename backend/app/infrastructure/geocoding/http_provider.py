"""Base HTTP dos provedores de geocoding — rate limit, retry e User-Agent.

Nenhum método daqui levanta exceção para o chamador: erro de rede ou de HTTP
vira `None`, e o `GeocodingService` decide o status (PENDENTE/NAO_ENCONTRADO —
D3). Um provedor público fora do ar não pode derrubar a importação de 10.000
contatos.

O limite de 1 requisição/s não é frescura: é o teto que a política de uso do
Nominatim público exige, e é ele — não o volume da base — que determina o tempo
do "geocode frio" (ADR-0004).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional

import httpx

from app.core.config import settings
from app.domain.delivery.routing import GeocodingProvider
from app.infrastructure.routing.circuit_breaker import CircuitBreaker

logger = logging.getLogger("gasflow.geocoding")


class RateLimitedHttp:
    """GET JSON com intervalo mínimo entre chamadas e retry com backoff."""

    name = "http"

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: Optional[float] = None,
        user_agent: Optional[str] = None,
        rate_limit_s: Optional[float] = None,
        max_attempts: Optional[int] = None,
        client: Any = None,
        breaker: Optional[CircuitBreaker] = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        # Reusa o CircuitBreaker do OSRM em vez de reimplementar uma estratégia
        # de falha paralela. Diferença registrada no ADR-0004: para rota existe
        # fallback local (haversine), aqui não — breaker aberto vira PENDENTE e
        # o contato cai na triagem (D3), nunca num endereço chutado.
        self._breaker = breaker or CircuitBreaker(
            settings.geocoding_breaker_failures,
            settings.geocoding_breaker_cooldown_s,
        )
        self._base = (base_url or "").rstrip("/")
        self._timeout = float(timeout_s if timeout_s is not None else settings.geocoding_timeout_s)
        self._user_agent = user_agent or settings.geocoding_user_agent
        self._min_interval = float(rate_limit_s if rate_limit_s is not None else settings.geocoding_rate_limit_s)
        self._max_attempts = max(1, int(max_attempts if max_attempts is not None else settings.geocoding_max_attempts))
        # `client` injetado é o caminho dos testes (httpx.MockTransport); sem
        # ele, um httpx.Client por chamada — o provedor não guarda conexão viva.
        self._client = client
        self._sleep = sleeper
        self._clock = clock
        self._last_call = 0.0

    # ── Rate limit ───────────────────────────────────────

    def _aguardar_slot(self) -> None:
        """Dorme o que falta para respeitar o intervalo mínimo entre chamadas."""
        if self._min_interval <= 0 or not self._last_call:
            return
        decorrido = self._clock() - self._last_call
        if decorrido < self._min_interval:
            self._sleep(self._min_interval - decorrido)

    # ── HTTP ─────────────────────────────────────────────

    def _get_json(self, path: str, params: Dict[str, str]) -> Any:
        """GET → JSON. `None` = falhou (breaker aberto ou tentativas esgotadas)."""
        url = f"{self._base}{path}"
        headers = {"User-Agent": self._user_agent, "Accept": "application/json"}
        return self._executar(url, lambda: self._request(url, params, headers))

    def _post_json(self, data: Dict[str, str], path: str = "") -> Any:
        """POST → JSON. Mesmo contrato do `_get_json`.

        O Overpass recebe a query no corpo (`data={"data": q}`), não na query
        string. Mesmo breaker, mesmo rate limit, mesmo backoff — é o passe
        próprio da etapa 6/8 (D14) usando a mesma máquina de falha de sempre.
        """
        url = f"{self._base}{path}"
        headers = {"User-Agent": self._user_agent, "Accept": "application/json"}
        return self._executar(url, lambda: self._request_post(url, data, headers))

    def _executar(self, url: str, acao: Callable[[], Any]) -> Optional[Any]:
        """Núcleo comum de GET/POST: breaker → rate limit → retry → backoff.

        Nenhuma falha vira exceção para o chamador: HTTP 4xx, timeout, JSON
        inválido e breaker aberto terminam em `None`, e o consumidor decide o
        status (D3).
        """
        if not self._breaker.allow():
            # Breaker aberto: não paga o timeout inteiro de novo. Não há
            # fallback local para "onde fica esta rua" — o consumidor registra
            # PENDENTE e o contato vai para triagem.
            logger.warning("geocoding.breaker_open", extra={"url": url})
            return None

        for tentativa in range(1, self._max_attempts + 1):
            self._aguardar_slot()
            try:
                payload = acao()
                self._last_call = self._clock()
                self._breaker.record_success()
                return payload
            except httpx.HTTPStatusError as exc:
                self._last_call = self._clock()
                status = exc.response.status_code if exc.response is not None else 0
                logger.warning(
                    "geocoding.http_error",
                    extra={"url": url, "status": status, "attempt": tentativa},
                )
                if 400 <= status < 500:
                    # 4xx quer dizer que o serviço ESTÁ vivo: zera as falhas e
                    # não repete (a consulta é que está errada).
                    self._breaker.record_success()
                    return None
            except Exception as exc:  # timeout, DNS, JSON inválido...
                self._last_call = self._clock()
                logger.warning(
                    "geocoding.request_failed",
                    extra={"url": url, "error": str(exc), "attempt": tentativa},
                )
            if tentativa < self._max_attempts:
                self._sleep(self._backoff(tentativa))

        # Esgotou as tentativas: conta UMA falha para o breaker.
        self._breaker.record_failure()
        return None

    def _request(self, url: str, params: Dict[str, str], headers: Dict[str, str]) -> Any:
        if self._client is not None:
            response = self._client.get(url, params=params, headers=headers)
        else:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url, params=params, headers=headers)
        return self._json(response)

    def _request_post(self, url: str, data: Dict[str, str], headers: Dict[str, str]) -> Any:
        if self._client is not None:
            response = self._client.post(url, data=data, headers=headers)
        else:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, data=data, headers=headers)
        return self._json(response)

    @staticmethod
    def _json(response: "httpx.Response") -> Any:
        response.raise_for_status()
        dados = response.json()
        return dados if isinstance(dados, (dict, list)) else None

    @staticmethod
    def _backoff(tentativa: int) -> float:
        """1s, 2s, 4s... — cresce o suficiente sem explodir com 3 tentativas."""
        return float(2 ** (tentativa - 1))

    @staticmethod
    def _consulta(*partes: str) -> str:
        """Junta só os pedaços preenchidos: \"Rua X, Bairro, Cidade, UF\"."""
        return ", ".join(p.strip() for p in partes if p and p.strip())


class RateLimitedHttpProvider(RateLimitedHttp, GeocodingProvider):
    """Provedor de geocoding sobre HTTP — só falta o mapa resposta→GeocodeResult."""
