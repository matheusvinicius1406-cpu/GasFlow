"""Seleção do provedor de roteamento (Fase 10).

Default: haversine. O sistema inteiro funciona sem nenhuma infra extra — o OSRM
só entra quando `ROUTING_PROVIDER=osrm` **e** `OSRM_BASE_URL` estão definidos.
Se a env apontar para osrm sem URL, ficamos no default em vez de estourar no
boot: uma env incompleta não pode derrubar o processo.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.domain.routing.provider import RoutingProvider
from app.infrastructure.routing.haversine_provider import HaversineRoutingProvider

logger = logging.getLogger("gasflow.routing.factory")


def get_routing_provider() -> RoutingProvider:
    """Provider configurado. Nunca levanta exceção."""
    if settings.routing_provider == "osrm":
        if not settings.osrm_base_url:
            logger.warning("routing.osrm_sem_base_url — usando haversine")
            return HaversineRoutingProvider()
        # Import tardio: sem a env ligada, o módulo OSRM nem é carregado.
        from app.infrastructure.routing.osrm_provider import OsrmRoutingProvider

        return OsrmRoutingProvider(settings.osrm_base_url)
    return HaversineRoutingProvider()
