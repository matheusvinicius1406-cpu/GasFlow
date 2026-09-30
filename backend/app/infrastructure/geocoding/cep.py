"""Fallback de CEP → endereço + coordenada — Fase 2, etapa 9 (catálogo de APIs).

Segundo elo do geocode (D2): quando o provedor de geocoding **não conhece o
logradouro**, o CEP ainda resolve endereço E coordenada — sem chave, sem
Overpass e sem passar pelo teto de 1 req/s do Nominatim.

Ordem fixa, medida no endereço de aceite (CEP 66811-120):

1. **BrasilAPI** (``/api/cep/v2/{cep}``) — MIT, keyless, devolve
   ``location.coordinates``; host Cloudflare, sem header de limite.
2. **PontoFato** (``/api/cep/{cep}``) — keyless, endereço do CNEFE/IBGE com
   ``lat``/``lon`` por ponto.

Os dois passaram no ``curl`` do endereço de aceite (ver
``docs/auditoria/catalogo-apis-externas.md``). Nenhum método levanta: CEP
inválido, provedor fora do ar e resposta sem coordenada terminam em ``None``, e
o contato segue para triagem (D3).

**Um CEP de rua cobre um trecho, não a casa.** Por isso o resultado entra como
*fallback* — e a coluna ``provider`` do cache registra quem respondeu
(``brasilapi``/``pontofato``), para o dado não se confundir com o do OSM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from app.core.config import settings
from app.infrastructure.geocoding.http_provider import RateLimitedHttp

_NAO_DIGITO = re.compile(r"\D+")

# 8 dígitos é a forma canônica do CEP; qualquer outra coisa não vira consulta
# (o provedor devolveria erro por nada e gastaria uma requisição do rate limit).
_DIGITOS_CEP = 8


def somente_digitos_cep(cep: object) -> str:
    """``66811-120`` / ``66.811-120`` → ``66811120``. Inválido → ``""``."""
    digitos = _NAO_DIGITO.sub("", str(cep or ""))
    return digitos if len(digitos) == _DIGITOS_CEP else ""


def _to_float(valor: object) -> Optional[float]:
    """Float tolerante: ``-1.45``, ``"-1.45583"``. Resto → ``None``."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


@dataclass
class EnderecoCep:
    """Endereço resolvido a partir de um CEP. Coordenada pode faltar."""

    cep: str = ""
    rua: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    provider: str = ""

    @property
    def tem_coordenada(self) -> bool:
        return self.lat is not None and self.lng is not None


# ── Clientes ──────────────────────────────────────────────


class _CepClient(RateLimitedHttp):
    """Base dos provedores de CEP — mesma máquina de falha do geocoding."""

    name = "cep"

    def buscar(self, cep: str) -> Optional[EnderecoCep]:  # pragma: no cover
        raise NotImplementedError


class BrasilApiCepClient(_CepClient):
    """``GET /api/cep/v2/{cep}`` — endereço + ``location.coordinates``."""

    name = "brasilapi"

    def buscar(self, cep: str) -> Optional[EnderecoCep]:
        cep8 = somente_digitos_cep(cep)
        if not cep8:
            return None
        payload = self._get_json(f"/api/cep/v2/{cep8}", {})
        if not isinstance(payload, dict) or not payload:
            return None

        location = payload.get("location")
        coords = location.get("coordinates") if isinstance(location, dict) else None
        coords = coords if isinstance(coords, dict) else {}
        return EnderecoCep(
            cep=str(payload.get("cep") or "").strip() or cep8,
            rua=str(payload.get("street") or "").strip(),
            bairro=str(payload.get("neighborhood") or "").strip(),
            cidade=str(payload.get("city") or "").strip(),
            uf=str(payload.get("state") or "").strip(),
            lat=_to_float(coords.get("latitude")),
            lng=_to_float(coords.get("longitude")),
            provider=self.name,
        )


class PontoFatoCepClient(_CepClient):
    """``GET /api/cep/{cep}`` — 1º ponto com ``lat``/``lon`` do CNEFE/IBGE."""

    name = "pontofato"

    def buscar(self, cep: str) -> Optional[EnderecoCep]:
        cep8 = somente_digitos_cep(cep)
        if not cep8:
            return None
        payload = self._get_json(f"/api/cep/{cep8}", {})
        if not isinstance(payload, dict):
            return None

        pontos = payload.get("pontos")
        if not isinstance(pontos, list):
            return None
        for ponto in pontos:
            if not isinstance(ponto, dict):
                continue
            lat = _to_float(ponto.get("lat"))
            lng = _to_float(ponto.get("lon"))
            if lat is None or lng is None:
                # Ponto sem coordenada não serve: o fallback existe para
                # conseguir lat/lng, não para reescrever o endereço.
                continue
            return EnderecoCep(
                cep=str(ponto.get("cep") or payload.get("cep") or "").strip() or cep8,
                rua=str(ponto.get("logradouro") or "").strip(),
                bairro=str(ponto.get("bairro") or "").strip(),
                cidade=str(ponto.get("cidade") or "").strip(),
                uf=str(ponto.get("uf") or "").strip(),
                lat=lat,
                lng=lng,
                provider=self.name,
            )
        return None


class CepFallback:
    """Cadeia BrasilAPI → PontoFato. Devolve o 1º resultado **com** coordenada.

    A cadeia é construída dos ``settings`` na primeira consulta (os clientes
    injetados são o caminho dos testes). Um provedor que falha não impede o
    próximo: o ``except`` aqui é a razão de existir do fallback.
    """

    def __init__(self, clientes: Optional[List[_CepClient]] = None):
        self._clientes = clientes

    def _cadeia(self) -> List[_CepClient]:
        if self._clientes is None:
            self._clientes = build_cep_clients()
        return self._clientes

    def buscar(self, cep: str) -> Optional[EnderecoCep]:
        if not somente_digitos_cep(cep):
            return None
        for cliente in self._cadeia():
            try:
                endereco = cliente.buscar(cep)
            except Exception:  # provedor é plugável: não se assume que é total
                endereco = None
            if endereco is not None and endereco.tem_coordenada:
                return endereco
        return None


def build_cep_clients() -> List[_CepClient]:
    """Clientes configurados, na ordem fixa BrasilAPI → PontoFato."""
    clientes: List[_CepClient] = []
    if settings.brasilapi_enabled:
        clientes.append(BrasilApiCepClient(settings.brasilapi_base_url))
    if settings.pontofato_enabled:
        clientes.append(PontoFatoCepClient(settings.pontofato_base_url))
    return clientes
