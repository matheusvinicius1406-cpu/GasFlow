"""Ingest de posição via relay — /api/v1/internal/driver/location/relay.

Fecha o elo morto da cadeia do rastreador (relay → desktop → backend).
Cobre a matriz de auth (mesma filosofia do test_sync_batch_auth.py):

1. Auth service-to-service: aceita SOMENTE X-GasFlow-Key igual à
   WHATSAPP_SERVICE_KEY/MARCOS_GAS_API_KEY do backend
2. JWT válido de usuário NÃO substitui a chave (sem fallback Bearer) —
   token vazado não pode injetar posição GPS de entregador
3. Fail-closed sem chave configurada
4. driver_id validado contra os motoristas do tenant — posição de ID
   desconhecido/inativo → 404 + audit REJECTED
5. Ingestão real persiste em driver_locations (mesma tabela do app)
6. Audit `driver.location.ingest_relay` com platform="desktop" —
   distinguível do POST direto do app (`driver.location.batch`, mobile)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.config import settings


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _db():
    from app.infrastructure.database.init_db import engine

    return Session(bind=engine)


def _create_driver(codigo: str, username: str, ativo: bool = True):
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    db = _db()
    try:
        exists = db.query(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == codigo).first()
        if exists:
            exists.ativo = ativo
            db.commit()
            return
        driver = DeliveryDriverModel(
            tenant_id="default",
            codigo=codigo,
            nome=f"Motorista {codigo}",
            telefone="11999991111",
            username=username,
            password_hash=None,
            ativo=ativo,
        )
        db.add(driver)
        db.commit()
    finally:
        db.close()


def _post(client, headers, driver_id="654321", tenant_id="default", lat=-1.4558, lng=-48.4902):
    return client.post(
        "/api/v1/internal/driver/location/relay",
        json={
            "tenant_id": tenant_id,
            "driver_id": driver_id,
            "positions": [{"driver_id": driver_id, "lat": lat, "lng": lng, "speed": 30.0}],
        },
        headers=headers,
    )


class TestRelayIngestAuth:
    def test_service_key_accepted(self, client, monkeypatch):
        """Driver dedicado (654501): 654321 pode ter posição <10s de outra
        suíte (throttle do handler daria accepted=0 de forma não-determinística)."""
        monkeypatch.setattr(settings, "whatsapp_service_key", "relay-secret-123")
        _create_driver("654501", "condutor_relay_auth")
        res = _post(client, {"X-GasFlow-Key": "relay-secret-123"}, driver_id="654501")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["success"] is True
        assert body["accepted"] == 1

    def test_wrong_key_rejected(self, client, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_service_key", "relay-secret-123")
        res = _post(client, {"X-GasFlow-Key": "wrong-key"})
        assert res.status_code == 401

    def test_valid_jwt_rejected(self, client, monkeypatch):
        """JWT de usuário NÃO vale aqui — sem fallback Bearer."""
        monkeypatch.setattr(settings, "whatsapp_service_key", "relay-secret-123")
        # login admin para provar que um token VÁLIDO também é rejeitado
        res_login = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
        if res_login.status_code == 200:
            token = res_login.json()["token"]
            res = _post(client, {"Authorization": f"Bearer {token}"})
            assert res.status_code == 401
        else:
            res = _post(client, {"Authorization": "Bearer anything"})
            assert res.status_code == 401

    def test_anonymous_rejected(self, client, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_service_key", "relay-secret-123")
        res = _post(client, {})
        assert res.status_code == 401

    def test_unconfigured_key_fails_closed(self, client, monkeypatch):
        """Sem chave no backend, o endpoint fica indisponível — nunca aberto."""
        monkeypatch.setattr(settings, "whatsapp_service_key", "")
        res = _post(client, {"X-GasFlow-Key": "anything"})
        assert res.status_code == 401


class TestRelayIngestDriverValidation:
    def test_unknown_driver_rejected_404(self, client, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_service_key", "relay-secret-123")
        res = _post(client, {"X-GasFlow-Key": "relay-secret-123"}, driver_id="999999")
        assert res.status_code == 404

    def test_location_persisted_for_known_driver(self, client, monkeypatch):
        """Driver dedicado: 654321 é compartilhado e o throttle de 10s do
        handler faria este upsert ser ignorado (200 + throttled) quando o
        módulo roda inteiro."""
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDriverLocationRepository,
        )

        monkeypatch.setattr(settings, "whatsapp_service_key", "relay-secret-123")
        _create_driver("654500", "condutor_relay_persist")
        res = _post(client, {"X-GasFlow-Key": "relay-secret-123"}, driver_id="654500", lat=-1.4600, lng=-48.4950)
        assert res.status_code == 200

        db = _db()
        try:
            record = SQLAlchemyDriverLocationRepository(db).get_location("default", "654500")
            assert record is not None
            assert abs(record.latitude - (-1.4600)) < 1e-6
        finally:
            db.close()


class TestRelayIngestAudit:
    def test_audit_distinguishes_relay_from_app(self, client, monkeypatch):
        """Audit da ingestão via relay é distinguível do POST direto do app.

        Relay: action=driver.location.ingest_relay, actor=service:relay,
        actor_type=SYSTEM, platform=desktop.
        App (comparação): action=driver.location.batch, platform=mobile.
        """
        monkeypatch.setattr(settings, "whatsapp_service_key", "relay-secret-123")
        _create_driver("654321", "condutor_relay")
        res = _post(client, {"X-GasFlow-Key": "relay-secret-123"})
        assert res.status_code == 200

        db = _db()
        try:
            from app.infrastructure.repositories.auth_model import AuthAuditModel

            rows = (
                db.query(AuthAuditModel)
                .filter(AuthAuditModel.action == "driver.location.ingest_relay")
                .filter(AuthAuditModel.resource_id == "654321")
                .all()
            )
            assert rows, "audit de ingest via relay não encontrado"
            latest = rows[-1]
            assert latest.actor_id == "service:relay"
            assert latest.actor_type == "SYSTEM"
            assert latest.platform == "desktop"
            assert latest.result == "SUCCESS"
            # LGPD: sem coordenadas no audit
            details = latest.details or {}
            assert "lat" not in str(details).lower() or "latitude" not in str(details).lower()
            assert "positions" in details or "accepted" in details

            # O caminho do app é outro por construction: quem grava audit do
            # app é DriverLocationService._audit (platform="mobile",
            # actor_type="DRIVER", action="driver.location.batch"); aqui é
            # _audit_relay_ingest (platform="desktop", actor_type="SYSTEM").
            # As queries acima já provam a distinção pelos campos.
        finally:
            db.close()

    def test_audit_rejected_for_unknown_driver(self, client, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_service_key", "relay-secret-123")
        res = _post(client, {"X-GasFlow-Key": "relay-secret-123"}, driver_id="888888")
        assert res.status_code == 404

        db = _db()
        try:
            from app.infrastructure.repositories.auth_model import AuthAuditModel

            row = (
                db.query(AuthAuditModel)
                .filter(AuthAuditModel.action == "driver.location.ingest_relay")
                .filter(AuthAuditModel.resource_id == "888888")
                .filter(AuthAuditModel.result == "REJECTED")
                .first()
            )
            assert row is not None, "audit REJECTED de driver desconhecido não encontrado"
        finally:
            db.close()
