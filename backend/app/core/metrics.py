"""
Prometheus metrics do backend GasFlow.

Endpoint: GET /metrics (formato text/plain do Prometheus).
Métricas de aplicação:
- gasflow_http_requests_total{method,endpoint,status} — requisições HTTP
- gasflow_http_request_duration_seconds{method,endpoint} — latência (histograma)
Plus default process metrics (CPU, memória, GC, Python).
"""

import logging
import os
import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
    start_http_server,
)

logger = logging.getLogger("gasflow.metrics")

# ── Registry (suporta múltiplos workers uvicorn via PROMETHEUS_MULTIPROC_DIR) ──

MP_DIR = os.getenv("PROMETHEUS_MULTIPROC_DIR", "")


def _registry() -> CollectorRegistry:
    """Registry apropriado: multiprocess quando configurado, senão o default."""
    if MP_DIR:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    from prometheus_client import REGISTRY

    return REGISTRY


# ── Métricas de aplicação ────────────────────────────────

HTTP_REQUESTS_TOTAL = Counter(
    "gasflow_http_requests_total",
    "Requisições HTTP por método, endpoint e status",
    labelnames=("method", "endpoint", "status"),
)

HTTP_REQUEST_DURATION = Histogram(
    "gasflow_http_request_duration_seconds",
    "Duração das requisições HTTP",
    labelnames=("method", "endpoint"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

WHATSAPP_SEND_TOTAL = Counter(
    "gasflow_whatsapp_send_total",
    "Envios WhatsApp realizados pelo backend (gateway)",
    labelnames=("provider", "status"),
)

# ── Endpoint /metrics ────────────────────────────────────


def render_metrics() -> tuple:
    """Retorna (body, content_type) para a resposta do /metrics."""
    return generate_latest(_registry()), CONTENT_TYPE_LATEST


def start_metrics_server(port: int = 9090) -> None:
    """Servidor HTTP separado para métricas (modo worker único, opcional)."""
    start_http_server(port)


# ── Middleware de métricas HTTP ──────────────────────────


class MetricsMiddleware:
    """Middleware ASGI puro — conta requisições e latência por rota.

    Usar via app.add_middleware(MetricsMiddleware) — não instrumenta rotas
    de health/metrics para não poluir as séries.
    """

    EXCLUDE = {"/metrics", "/health", "/ready", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.EXCLUDE:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        start = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            status = str(status_holder["status"])
            # Normaliza path com parâmetros (evita cardinalidade explosiva):
            # /orders/42 → /orders/{id}
            route = getattr(scope, "route", None)
            endpoint = getattr(route, "path", path)
            HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status=status).inc()
            HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
