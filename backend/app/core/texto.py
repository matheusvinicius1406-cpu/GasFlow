"""Normalização de texto de endereço — usada por application E infrastructure.

Separado de propósito: a chave do cache (application) e o casamento de nome do
logradouro contra o OSM (o provider Overpass, em infrastructure) precisam
produzir **exatamente** a mesma forma do mesmo texto. Dois normalizadores
iguais-por-copia divergem no primeiro acento maluco e o resultado é uma rua
cacheada que o Overpass nunca acha.

Camada neutra (nem domain, nem application) para que infra não precise importar
de application — que seria a dependência invertida.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_NAO_ALFANUM = re.compile(r"[^0-9a-z]+")


def normalizar(value: Any) -> str:
    """minúsculas, sem acento, sem pontuação, espaços colapsados."""
    texto = unicodedata.normalize("NFKD", str(value or ""))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return " ".join(_NAO_ALFANUM.sub(" ", texto.lower()).split())
