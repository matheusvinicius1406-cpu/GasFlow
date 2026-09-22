"""Fase 7.2 — link público de rastreio.

Cobre:
- assinatura (token adulterado → None), escopo e expiração
- emissão só por admin/operador
- snapshot público sem autenticação e **sem PII**
- 401 para token inválido/expirado
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.application.tracking.public_tracking import (
    issue_public_tracking_token,
    verify_public_tracking_token,
)
from app.infrastructure.database.init_db import engine
from app.main import app


@pytest.fixture
def app_db():
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


class TestToken:
    def test_roundtrip_devolve_o_payload(self):
        token = issue_public_tracking_token(tenant_id="t1", driver_id="d1", ttl_seconds=3600)
        payload = verify_public_tracking_token(token)
        assert payload is not None
        assert payload["t"] == "t1"
        assert payload["d"] == "d1"
        assert payload["scope"] == "public_tracking"

    def test_assinatura_adulterada_e_recusada(self):
        token = issue_public_tracking_token(tenant_id="t1", driver_id="d1")
        body, _, signature = token.partition(".")
        # troca o último caractere da assinatura
        tampered = f"{body}.{signature[:-1]}{'A' if signature[-1] != 'A' else 'B'}"
        assert verify_public_tracking_token(tampered) is None

    def test_corpo_adulterado_e_recusado(self):
        token = issue_public_tracking_token(tenant_id="t1", driver_id="d1")
        _, _, signature = token.partition(".")
        other = issue_public_tracking_token(tenant_id="t2", driver_id="d9").partition(".")[0]
        assert verify_public_tracking_token(f"{other}.{signature}") is None

    def test_token_expirado_e_recusado(self):
        token = issue_public_tracking_token(tenant_id="t1", driver_id="d1", ttl_seconds=60)
        # reemite com exp no passado assinando com o mesmo segredo
        from app.application.tracking import public_tracking as pt

        body = pt._b64e(b'{"t":"t1","d":"d1","exp":1,"scope":"public_tracking"}')
        expired = f"{body}.{pt._sign(body)}"
        assert verify_public_tracking_token(expired) is None

    def test_lixo_e_recusado(self):
        assert verify_public_tracking_token("") is None
        assert verify_public_tracking_token("sem-ponto") is None
        assert verify_public_tracking_token("a.b") is None


class TestEndpoints:
    def test_link_exige_admin_ou_operador(self, client):
        res = client.post("/public/tracking/link?driver_id=qualquer")
        assert res.status_code in (401, 403), res.text

    def test_snapshot_sem_auth_e_sem_pii(self, client, app_db):
        driver_id = f"pub-{uuid.uuid4().hex[:6]}"
        from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDriverLocationRepository,
        )

        app_db.add(
            DeliveryDriverModel(
                tenant_id="default",
                codigo=driver_id,
                nome="Fulano da Silva",
                telefone="91999998888",
                ativo=True,
            )
        )
        app_db.commit()
        SQLAlchemyDriverLocationRepository(app_db).upsert_location("default", driver_id, -23.55, -46.63)

        token = issue_public_tracking_token(tenant_id="default", driver_id=driver_id)

        # Sem header de Authorization.
        res = client.get(f"/public/tracking/{token}")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["driver_id"] == driver_id
        assert body["latitude"] == -23.55
        assert body["longitude"] == -46.63
        # Sem PII: nada de nome/telefone/endereço no payload.
        assert "Fulano" not in res.text
        assert "91999998888" not in res.text
        assert set(body) == {"driver_id", "latitude", "longitude", "updated_at"}

    def test_snapshot_com_token_invalido_devolve_401(self, client):
        res = client.get("/public/tracking/nao-e-um-token-valido")
        assert res.status_code == 401, res.text

    def test_snapshot_de_entregador_sem_posicao_devolve_404(self, client):
        token = issue_public_tracking_token(tenant_id="default", driver_id=f"sem-pos-{uuid.uuid4().hex[:6]}")
        res = client.get(f"/public/tracking/{token}")
        assert res.status_code == 404, res.text

    def test_link_de_entregador_inexistente_devolve_404(self, client, admin_headers):
        res = client.post("/public/tracking/link?driver_id=nao-existe-12345", headers=admin_headers)
        assert res.status_code == 404, res.text

    def test_link_emitido_por_admin_funciona(self, client, admin_headers, app_db):
        driver_id = f"pub2-{uuid.uuid4().hex[:6]}"
        from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDriverLocationRepository,
        )

        app_db.add(DeliveryDriverModel(tenant_id="default", codigo=driver_id, nome="Beltrano", telefone="91999997777"))
        app_db.commit()
        SQLAlchemyDriverLocationRepository(app_db).upsert_location("default", driver_id, -23.5, -46.6)

        created = client.post(f"/public/tracking/link?driver_id={driver_id}", headers=admin_headers)
        assert created.status_code == 200, created.text
        token = created.json()["token"]

        res = client.get(f"/public/tracking/{token}")
        assert res.status_code == 200, res.text
        assert res.json()["driver_id"] == driver_id

    def test_updated_at_serializa_o_timestamp(self, client, app_db):
        driver_id = f"pub3-{uuid.uuid4().hex[:6]}"
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDriverLocationRepository,
        )

        SQLAlchemyDriverLocationRepository(app_db).upsert_location("default", driver_id, -23.5, -46.6)
        token = issue_public_tracking_token(tenant_id="default", driver_id=driver_id)
        body = client.get(f"/public/tracking/{token}").json()
        assert datetime.fromisoformat(body["updated_at"]) is not None
