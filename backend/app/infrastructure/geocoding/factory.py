"""Factory do provedor de geocoding (env `GEOCODING_PROVIDER`).

Default = `nominatim` (D8): público, open source, sem chave. `mock` é o caminho
de dev/testes (zero rede). `photon` é o self-host.

Os timeouts/rate limit continuam vindo de `settings` na hora de construir o
provider — trocar de provedor não exige mexer em nenhum chamador.
"""

from __future__ import annotations

from app.core.config import settings
from app.domain.delivery.routing import GeocodingProvider, MockGeocodingProvider
from app.infrastructure.geocoding.nominatim_provider import NominatimProvider
from app.infrastructure.geocoding.photon_provider import PhotonProvider

_NOMINATIM_DEFAULT = "https://nominatim.openstreetmap.org"
_PHOTON_DEFAULT = "http://localhost:2322"


def get_geocoding_provider() -> GeocodingProvider:
    """Provider configurado. Nome desconhecido cai no Nominatim, não em erro."""
    nome = (settings.geocoding_provider or "nominatim").strip().lower()

    if nome == "mock":
        return MockGeocodingProvider()
    if nome == "photon":
        base = settings.geocoding_base_url
        # O default de GEOCODING_BASE_URL é o do Nominatim: apontar o Photon
        # para lá consultaria o serviço errado. Só herda a URL se ela tiver
        # sido trocada de propósito.
        if not base or "nominatim" in base:
            base = _PHOTON_DEFAULT
        return PhotonProvider(base)
    return NominatimProvider(settings.geocoding_base_url or _NOMINATIM_DEFAULT)
