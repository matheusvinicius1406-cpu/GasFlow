"""ViaCEP — fallback de CEP (público, open source, sem chave).

Só entra quando o `postcode` do OSM não veio: o ViaCEP é indexado por CEP, e a
consulta por endereço (`/ws/{uf}/{cidade}/{rua}/json/`) exige cidade e UF. Sem
esses dois campos não há o que consultar — devolve `None` em vez de chutar.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from app.infrastructure.geocoding.http_provider import RateLimitedHttp

# O ViaCEP não responde bem com ruas muito curtas ("R." etc.) — abaixo disso a
# consulta é ruído e gasta uma requisição do rate limit por nada.
_MIN_RUA = 3


class ViaCepClient(RateLimitedHttp):
    name = "viacep"

    def buscar_cep(self, uf: str, cidade: str, rua: str) -> Optional[str]:
        """CEP do logradouro. `None` quando falta cidade/uf ou nada é achado."""
        uf = (uf or "").strip()
        cidade = (cidade or "").strip()
        rua = (rua or "").strip()
        if not uf or not cidade or len(rua) < _MIN_RUA:
            return None

        # quote() por segmento: "Rua São João" tem acento e espaço e viraria
        # URL inválida se fosse concatenado cru.
        path = f"/ws/{quote(uf, safe='')}/{quote(cidade, safe='')}/{quote(rua, safe='')}/json/"
        payload = self._get_json(path, {})
        registros = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []

        for registro in registros:
            if not isinstance(registro, dict) or registro.get("erro"):
                continue
            cep = str(registro.get("cep") or "").strip()
            if cep:
                return cep
        return None
