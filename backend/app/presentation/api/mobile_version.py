"""Mobile version endpoint — check for APK updates.

Endpoint publico (sem auth) que retorna a versao mais recente do APK.
O admin atualiza version.json no deploy; o app mobile consulta esta rota
no boot para verificar se ha atualizacao disponivel.
"""

from __future__ import annotations

import json
import os
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


# Nome do arquivo de versao na raiz do repositorio
_VERSION_FILENAME = "mobile_version.json"


def _version_file() -> Path:
    """Localiza o `mobile_version.json`.

    Ordem de resolucao:
    1. env `MOBILE_VERSION_FILE` (caminho absoluto ou relativo ao cwd);
    2. raiz do repositorio — `backend/app/presentation/api/mobile_version.py`
       sobe 4 pastas (api → presentation → app → backend) ate `GasFlow/`,
       onde o arquivo e versionado no deploy.

    Resolvido a cada request (e nao no import) para que o override por env
    funcione em runtime e nos testes.
    """
    override = os.getenv("MOBILE_VERSION_FILE")
    if override:
        return Path(override)
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / _VERSION_FILENAME


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
    version_file = _version_file()

    if version_file.is_file():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                file_data = json.load(f)
            # Merge: arquivo sobrescreve defaults
            for key in data:
                if key in file_data and file_data[key]:
                    data[key] = str(file_data[key])
        except (json.JSONDecodeError, OSError):
            pass  # Mantem defaults

    return MobileVersionResponse(**data)
