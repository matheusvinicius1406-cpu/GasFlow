"""Regressão: login de entregador sem hash cadastrado deve falhar (401).

Histórico (03/11/2026): tanto `/auth/mobile/login` quanto o login legado
`/api/v1/driver/auth/login` faziam

    if driver.password_hash:
        if not bcrypt.checkpw(...):
            raise 401

Ou seja, quando `password_hash` era vazio/NULL a verificação era **pulada** e
qualquer senha autenticava. Um entregador criado pelo fluxo canônico
(`POST /api/v1/admin/drivers`) nasce com `delivery_drivers.password_hash`
vazio — a condição era alcançável.

A correção inverte o contrato: sem hash, 401.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _db():
    from sqlalchemy.orm import Session

    from app.infrastructure.database.init_db import engine

    return Session(bind=engine)


def _driver_without_hash(username: str) -> None:
    from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

    db = _db()
    try:
        existing = db.query(DeliveryDriverModel).filter(DeliveryDriverModel.codigo == "999001").first()
        if existing:
            existing.username = username
            existing.password_hash = None
            existing.ativo = True
        else:
            db.add(
                DeliveryDriverModel(
                    tenant_id="default",
                    codigo="999001",
                    nome="Motorista Sem Hash",
                    telefone="11999990001",
                    username=username,
                    password_hash=None,
                    ativo=True,
                )
            )
        db.commit()
    finally:
        db.close()


def test_mobile_login_rejects_driver_without_password_hash(client):
    _driver_without_hash("sem_hash_mobile")

    resp = client.post(
        "/auth/mobile/login",
        json={"username": "sem_hash_mobile", "password": "qualquer_senha"},
    )

    assert resp.status_code == 401


def test_legacy_driver_login_rejects_driver_without_password_hash(client):
    _driver_without_hash("sem_hash_legacy")

    resp = client.post(
        "/api/v1/driver/auth/login",
        json={"username": "sem_hash_legacy", "password": "qualquer_senha"},
    )

    assert resp.status_code == 401
