"""Provedor Nominatim — geocoding público do OSM (default; D8).

O endpoint `/search` devolve o logradouro estruturado em `address` (road,
suburb, city, state_code, postcode). O que ele **não** devolve são as vias que
cruzam o logradouro: `intersecoes` sai vazio de propósito, e quem preenche é o
Overpass na etapa 6 (D9). Devolver um palpite ali seria inventar "entre ruas"
(D2).
"""

from __future__ import annotations

from typing import Optional

from app.domain.delivery.routing import GeocodeResult
from app.infrastructure.geocoding.http_provider import RateLimitedHttpProvider

_SEARCH = "/search"


class NominatimProvider(RateLimitedHttpProvider):
    name = "nominatim"

    def geocode_street(self, rua: str, bairro: str = "", cidade: str = "", uf: str = "") -> Optional[GeocodeResult]:
        consulta = self._consulta(rua, bairro, cidade, uf)
        if not consulta:
            return None

        payload = self._get_json(
            _SEARCH,
            {
                "q": consulta,
                "format": "jsonv2",
                "addressdetails": "1",
                "limit": "1",
                "countrycodes": "br",
            },
        )
        if not isinstance(payload, list) or not payload:
            return None

        melhor = payload[0]
        if not isinstance(melhor, dict):
            return None
        try:
            lat = float(melhor["lat"])
            lng = float(melhor["lon"])
        except (KeyError, TypeError, ValueError):
            return None

        endereco = melhor.get("address") or {}
        return GeocodeResult(
            lat=lat,
            lng=lng,
            rua=endereco.get("road") or rua,
            bairro=endereco.get("suburb") or endereco.get("neighbourhood") or bairro,
            cidade=endereco.get("city") or endereco.get("town") or endereco.get("village") or cidade,
            # Só `state_code` ("SP") serve como UF — `state` é "São Paulo" e
            # cortar os 2 primeiros caracteres daria "Sã".
            uf=(endereco.get("state_code") or uf or "").strip().upper()[:2],
            cep=endereco.get("postcode") or "",
            intersecoes=[],
        )
