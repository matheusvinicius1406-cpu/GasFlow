"""Mobile version endpoint — check for APK updates.

Endpoint publico (sem auth) que retorna a versao mais recente do APK.
O admin atualiza version.json no deploy; o app mobile consulta esta rota
no boot para verificar se ha atualizacao disponivel.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/mobile", tags=["mobile-update"])


class MobileVersionResponse(BaseModel):
    latest_version: str
    download_url: str
    changelog: str
    min_required: str
    release_date: str


# Caminho para o arquivo version.json (configuravel via env ou fallback)
_VERSION_FILE = Path(__file__).resolve().parent.parent.parent.parent / "mobile_version.json"

# Versao padrao caso o arquivo nao exista
_DEFAULT_VERSION = {
    "latest_version": "1.2.0",
    "download_url": "",
    "changelog": "Sistema operacional de entregas com rastreamento em tempo real.",
    "min_required": "1.0.0",
    "release_date": "2026-09-22",
}


@router.get("/version", response_model=MobileVersionResponse)
async def get_mobile_version():
    """Retorna a versao mais recente do APK para o app mobile.

    Consulta o arquivo mobile_version.json na raiz do projeto.
    Se nao existir ou estiver incompleto, retorna os valores padrao.
    """
    data = dict(_DEFAULT_VERSION)

    if _VERSION_FILE.is_file():
        try:
            with open(_VERSION_FILE, "r", encoding="utf-8") as f:
                file_data = json.load(f)
            # Merge: arquivo sobrescreve defaults
            for key in data:
                if key in file_data and file_data[key]:
                    data[key] = str(file_data[key])
        except (json.JSONDecodeError, OSError):
            pass  # Mantem defaults

    return MobileVersionResponse(**data)
