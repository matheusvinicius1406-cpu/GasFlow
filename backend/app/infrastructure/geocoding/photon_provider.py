"""Provedor Photon — geocoding self-hosted do OSM (alternativa ao Nominatim).

Mesma semântica do `NominatimProvider`, resposta diferente: GeoJSON
(`features[0].geometry.coordinates` = [lng, lat], dados em `properties`).
Serve para trocar a instância pública por uma local sem tocar no resto do
pipeline — é só `GEOCODING_PROVIDER=photon` + `GEOCODING_BASE_URL`.
"""

from __future__ import annotations

from typing import Optional

from app.domain.delivery.routing import GeocodeResult
from app.infrastructure.geocoding.http_provider import RateLimitedHttpProvider

_API = "/api"


class PhotonProvider(RateLimitedHttpProvider):
    name = "photon"

    def geocode_street(self, rua: str, bairro: str = "", cidade: str = "", uf: str = "") -> Optional[GeocodeResult]:
        consulta = self._consulta(rua, bairro, cidade, uf)
        if not consulta:
            return None

        payload = self._get_json(_API, {"q": consulta, "limit": "1", "lang": "pt"})
        features = payload.get("features") if isinstance(payload, dict) else None
        if not features:
            return None

        melhor = features[0]
        if not isinstance(melhor, dict):
            return None
        props = melhor.get("properties") or {}
        coords = ((melhor.get("geometry") or {}).get("coordinates")) or []
        if len(coords) < 2:
            return None
        try:
            lng, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            return None

        return GeocodeResult(
            lat=lat,
            lng=lng,
            rua=props.get("street") or props.get("name") or rua,
            bairro=props.get("district") or props.get("locality") or bairro,
            cidade=props.get("city") or cidade,
            uf=(props.get("state") or uf or "").strip().upper()[:2],
            cep=props.get("postcode") or "",
            intersecoes=[],
        )
