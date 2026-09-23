"""Auto-update do APK — ``GET /mobile/version``.

Rota publica (sem auth) que o app do entregador consulta no boot. Cobre:

- contrato em ``/api/v1/mobile/version`` (o path que o mobile usa) e na raiz
  (compat do desktop embutido);
- leitura do ``mobile_version.json`` versionado na **raiz do repositorio**
  — se o path resolver errar, a rota cai nos defaults e ``download_url``
  volta vazio, o que faz o app descartar a resposta;
- override por ``MOBILE_VERSION_FILE`` e fallback quando o arquivo nao existe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

PAYLOAD_FIELDS = {
    "latest_version",
    "download_url",
    "changelog",
    "min_required",
    "release_date",
}

# backend/tests/test_mobile_version.py → raiz do repo (GasFlow)
ROOT_VERSION_FILE = Path(__file__).resolve().parents[2] / "mobile_version.json"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_v1_route_reflete_o_arquivo_da_raiz(client):
    """O endpoint do mobile precisa ler o arquivo real, nao os defaults."""
    assert ROOT_VERSION_FILE.is_file(), "mobile_version.json sumiu da raiz do repo"

    res = client.get("/api/v1/mobile/version")

    assert res.status_code == 200
    data = res.json()
    assert set(data) == PAYLOAD_FIELDS

    versionado = json.loads(ROOT_VERSION_FILE.read_text(encoding="utf-8"))
    assert data["latest_version"] == versionado["latest_version"]
    assert data["download_url"] == versionado["download_url"]
    # o default tem download_url vazio — o app leria isso como resposta invalida
    assert data["download_url"].startswith("http")


def test_raiz_compat_desktop_serve_o_mesmo_payload(client):
    raiz = client.get("/mobile/version")
    v1 = client.get("/api/v1/mobile/version")

    assert raiz.status_code == 200
    assert raiz.json() == v1.json()


def test_mobile_version_file_override(client, tmp_path, monkeypatch):
    custom = tmp_path / "custom_version.json"
    custom.write_text(
        json.dumps(
            {
                "latest_version": "9.9.9",
                "download_url": "https://example.test/app-release.apk",
                "changelog": "build de teste",
                "min_required": "9.0.0",
                "release_date": "2030-01-01",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOBILE_VERSION_FILE", str(custom))

    data = client.get("/api/v1/mobile/version").json()

    assert data["latest_version"] == "9.9.9"
    assert data["download_url"] == "https://example.test/app-release.apk"


def test_arquivo_ausente_cai_nos_defaults(client, tmp_path, monkeypatch):
    monkeypatch.setenv("MOBILE_VERSION_FILE", str(tmp_path / "nao-existe.json"))

    res = client.get("/api/v1/mobile/version")

    assert res.status_code == 200
    data = res.json()
    assert data["latest_version"] == "1.2.0"
    assert data["download_url"] == ""
