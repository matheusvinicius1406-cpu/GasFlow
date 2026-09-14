"""Regressão P0 (3.8) — os 7 casos transversais do gate.

Consolida o "definition of done" do P0:
1. Usuário sem permissão → 403 (require_permission em /admin/*)
2. Entrega cancelada → estoque não muda (invariante mantida)
3. Snapshot do dia fecha correto (initial + deltas = closing)
4. Reset de senha → must_change_password=true; próximo login informa
   must_change_password ao cliente (base para forçar a troca)
5. Auditoria registra before_json/after_json em mutação sensível
6. DB legado (create_all sem alembic_version) → boot aplica migração +
   seed sem perder dados
7. DB novo → boot cria tudo + seed completo

Os casos 6 e 7 reutilizam `run_migrations()` de desktop_entry (mesma
estratégia validada em test_desktop_migrations.py), mas adicionam o
seed RBAC no critério.
"""

from __future__ import annotations

import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402
from desktop_entry import run_migrations  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _create_operator(client, admin_headers) -> tuple[str, str]:
    """Cria usuário OPERATOR; retorna (token, user_id)."""
    from sqlalchemy.orm import Session

    from app.infrastructure.database.init_db import engine

    db = Session(bind=engine)
    try:
        role_id = db.execute(text("SELECT id FROM auth_roles WHERE name = 'OPERATOR'")).scalar_one()
    finally:
        db.close()

    username = f"p0_{uuid.uuid4().hex[:8]}"
    res = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "email": f"{username}@gasflow.local",
            "password": "InitialPass1!",
            "role": "OPERATOR",
        },
    )
    assert res.status_code == 201, res.text
    user_id = res.json()["user_id"]

    login = client.post("/auth/login", json={"username": username, "password": "InitialPass1!"})
    assert login.status_code == 200
    return login.json()["token"], user_id


# ═══════════════════════════════════════════════════════════
# 1. Permissão ausente → 403
# ═══════════════════════════════════════════════════════════


def test_user_without_permission_gets_403(client, admin_headers):
    """OPERATOR (sem user.create) não pode criar usuário; ADMIN pode listar."""
    token, _ = _create_operator(client, admin_headers)
    res = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "should_fail",
            "email": "fail@gasflow.local",
            "password": "Whatever1!",
            "role": "OPERATOR",
        },
    )
    assert res.status_code == 403, res.text


# ═══════════════════════════════════════════════════════════
# 2/3. Estoque: cancelamento + snapshot
# ═══════════════════════════════════════════════════════════


def _isolated_stock_db():
    """Engine + session em memória com os models de estoque/entrega."""
    from sqlalchemy import event
    from sqlalchemy.orm import sessionmaker

    from app.infrastructure.database.base import Base

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return engine, Session()


def test_cancelled_delivery_does_not_change_stock():
    """CANCELLED (antes de entregar) não altera o estoque; invariante mantida.

    Decisão B3(a): sem débito no CONFIRMED, cancelar a entrega antes de
    DELIVERED é no-op — não gera SALE nem RETURN de DELIVERY.
    """
    from app.infrastructure.repositories.delivery_persistence_repository import (
        SQLAlchemyDeliveryPersistenceRepository,
    )
    from app.infrastructure.repositories.inventory_model import InventoryModel, StockMovementModel
    from app.infrastructure.repositories.order_item_model import OrderItemModel
    from app.infrastructure.repositories.product_model import ProductModel

    engine, db = _isolated_stock_db()
    try:
        db.add(ProductModel(codigo="P77777", nome="GLP P13", tipo="GAS", preco=100.0, estoque=10))
        db.add(InventoryModel(product_codigo="P77777", quantity=10, quantity_full=10, quantity_empty=0))
        db.add(
            OrderItemModel(
                order_codigo="777777",
                product_codigo="P77777",
                product_nome="GLP P13",
                quantity=4,
                unit_price=100,
                subtotal=400,
            )
        )
        db.commit()

        delivery_repo = SQLAlchemyDeliveryPersistenceRepository(db, "default")
        delivery_repo.create_delivery("d-p0-1", "777777")
        delivery_repo.assign_delivery("d-p0-1", "drv", None, 1)
        cancelled = delivery_repo.cancel_delivery("d-p0-1", 2)
        assert cancelled is not None and cancelled.status == "CANCELLED"

        inv = db.query(InventoryModel).first()
        assert inv.quantity == 10
        assert inv.quantity_full == 10
        assert inv.quantity_empty == 0
        # Entrega cancelada antes de DELIVERED não gerou movimento algum
        assert (
            db.query(StockMovementModel)
            .filter(StockMovementModel.reference_type == "DELIVERY", StockMovementModel.reference_id == "d-p0-1")
            .count()
            == 0
        )
        # Invariante P0
        assert inv.quantity == inv.quantity_full
    finally:
        db.close()
        engine.dispose()


def test_daily_snapshot_closes_correctly():
    """Snapshot fecha correto: closing reflete o estado final do dia e
    initial(d+1) == closing(d)."""
    from app.application.inventory.snapshot_service import StockDailySnapshotService
    from app.infrastructure.repositories.inventory_model import InventoryModel
    from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
    from app.infrastructure.repositories.product_model import ProductModel
    from app.infrastructure.repositories.rbac_model import StockDailySnapshotModel

    engine, db = _isolated_stock_db()
    try:
        db.add(ProductModel(codigo="P88888", nome="GLP P13", tipo="GAS", preco=100.0, estoque=10))
        db.add(InventoryModel(product_codigo="P88888", quantity=10, quantity_full=10, quantity_empty=2))
        db.commit()

        service = StockDailySnapshotService(db, "default")
        service.run_daily_snapshot()

        # Movimenta: entrega debita 3 cheios (3 devolvidos como vazios)
        repo = SQLAlchemyInventoryRepository(db)
        repo.deliver_stock_atomic("P88888", 3, reason="Venda", reference_type="DELIVERY", reference_id="dp0-1")

        # Tick seguinte do poller (mesmo dia): atualiza o closing do dia
        service.run_daily_snapshot()

        day1 = db.query(StockDailySnapshotModel).first().snapshot_date

        # Fechamento do dia seguinte herda o closing
        day2 = day1 + timedelta(days=1)
        service._snapshot_day(day2)

        snaps = {s.snapshot_date: s for s in db.query(StockDailySnapshotModel).all()}
        # Dia 1: initial = 10/2 (primeiro dia, estado no primeiro tick);
        # closing = estado final do dia (7 cheios, 5 vazios)
        assert snaps[day1].initial_full == 10
        assert snaps[day1].initial_empty == 2
        assert snaps[day1].closing_full == 7
        assert snaps[day1].closing_empty == 5
        # Dia 2: initial == closing(dia 1) — cadeia encadeada
        assert snaps[day2].initial_full == 7
        assert snaps[day2].initial_empty == 5
    finally:
        db.close()
        engine.dispose()


# ═══════════════════════════════════════════════════════════
# 4/5. Reset de senha + auditoria
# ═══════════════════════════════════════════════════════════


def test_reset_password_forces_change_on_next_login(client, admin_headers):
    """Reset → must_change_password=true; login seguinte expõe a flag;
    enforce completo: /auth/me expõe, política rejeita senha fraca, troca
    correta limpa a flag e a temporária deixa de funcionar."""
    token, user_id = _create_operator(client, admin_headers)

    reset = client.post(f"/admin/users/{user_id}/reset-password", headers=admin_headers)
    assert reset.status_code == 200, reset.text
    temp_password = reset.json()["temporary_password"]
    assert reset.json()["must_change_password"] is True

    # Senha antiga não funciona mais
    old_login = client.post(
        "/auth/login", json={"username": _username_of(client, admin_headers, user_id), "password": "InitialPass1!"}
    )
    assert old_login.status_code == 401

    # Login com a temporária: flag presente na resposta
    username = _username_of(client, admin_headers, user_id)
    login = client.post("/auth/login", json={"username": username, "password": temp_password})
    assert login.status_code == 200, login.text
    assert login.json()["user"]["must_change_password"] is True
    _ = token  # token anterior permanece válido (revogação é decisão de produto)

    # ═══ Enforce P0 (3.8): cliente bloqueia o app até a troca ═══
    temp_token = login.json()["token"]
    forced_headers = {"Authorization": f"Bearer {temp_token}"}

    # /auth/me também expõe a flag (caso de refresh/reload da página)
    me = client.get("/auth/me", headers=forced_headers)
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True

    # Política de senha rejeitada (sem maiúscula)
    weak = client.post(
        "/auth/change-password",
        headers=forced_headers,
        json={"current_password": temp_password, "new_password": "fraca1234"},
    )
    assert weak.status_code == 422, weak.text

    # Senha atual incorreta → 403 (não 400 de validação)
    wrong_current = client.post(
        "/auth/change-password",
        headers=forced_headers,
        json={"current_password": "Errada123!", "new_password": "NovaSenha123"},
    )
    assert wrong_current.status_code == 403, wrong_current.text

    # Troca correta limpa a flag
    changed = client.post(
        "/auth/change-password",
        headers=forced_headers,
        json={"current_password": temp_password, "new_password": "NovaSenha123"},
    )
    assert changed.status_code == 200, changed.text

    # Flag limpa: /auth/me não força mais a troca
    me_after = client.get("/auth/me", headers=forced_headers)
    assert me_after.status_code == 200
    assert me_after.json()["must_change_password"] is False

    # A nova senha funciona sem flag (rate limit de login: 5/300s por usuário —
    # manter o nº de logins do teste dentro do limite)
    new_login = client.post("/auth/login", json={"username": username, "password": "NovaSenha123"})
    assert new_login.status_code == 200, new_login.text
    assert new_login.json()["user"]["must_change_password"] is False


def _username_of(client, admin_headers, user_id: str) -> str:
    res = client.get("/admin/users", headers=admin_headers)
    assert res.status_code == 200
    for u in res.json()["users"]:
        if u["id"] == user_id:
            return u["username"]
    raise AssertionError("user not found in listing")


def test_audit_records_before_after_json(client, admin_headers):
    """Mutação sensível grava before_json/after_json (sem segredos)."""
    username = f"p0audit_{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "email": f"{username}@gasflow.local",
            "password": "InitialPass1!",
            "role": "OPERATOR",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["user_id"]

    # Mutação: atualiza display_name
    patched = client.patch(
        f"/admin/users/{user_id}",
        headers=admin_headers,
        json={"display_name": "P0 Audit"},
    )
    assert patched.status_code == 200, patched.text

    # Consulta auditoria filtrando pelo alvo
    audit = client.get(f"/admin/audit?resource=user&resource_id={user_id}", headers=admin_headers)
    assert audit.status_code == 200, audit.text
    records = audit.json()["records"]
    assert records, "nenhum registro de auditoria para a mutação"

    modified = [r for r in records if r["action"] == "RESOURCE_MODIFIED"]
    assert modified, "RESOURCE_MODIFIED não encontrado"
    row = modified[0]
    assert row["before_json"] is not None
    assert row["after_json"] is not None
    assert row["before_json"].get("display_name") != "P0 Audit"
    assert row["after_json"].get("display_name") == "P0 Audit"
    # Segredos nunca aparecem no snapshot
    for snap in (row["before_json"], row["after_json"]):
        assert "password" not in snap and "password_hash" not in snap


# ═══════════════════════════════════════════════════════════
# 6/7. Boot com DB legado e DB novo (migração + seed)
# ═══════════════════════════════════════════════════════════


def _runtime_tables() -> set[str]:
    from app.infrastructure.database.init_db import Base

    return set(Base.metadata.tables.keys())


def _seed_catalog_sizes() -> tuple[int, int]:
    """Tamanhos esperados do catálogo, lidos do próprio módulo de seed
    (fonte única — o teste não quebra quando o catálogo cresce)."""
    from app.infrastructure.database.rbac_seed import PERMISSIONS, ROLE_MATRIX

    return len(PERMISSIONS), len(ROLE_MATRIX)


def _boot_seed(url: str) -> None:
    """Simula o boot após a migração: seed RBAC + AuthService init.

    O usuário admin é persistido pelo AuthService._init_defaults() (fonte
    do ADMIN_PASSWORD), não pela migração — replicar a ordem real do boot:
    run_migrations → seed RBAC → app start (AuthService persiste
    tenant/roles/admin).
    """
    from sqlalchemy import create_engine as ce
    from sqlalchemy.orm import Session as ORMSession

    from app.application.security.auth_service import AuthService
    from app.infrastructure.database.rbac_seed import seed_rbac

    eng = ce(url)
    try:
        with eng.begin() as conn:  # begin = commit no fim (seed persiste)
            seed_rbac(conn)
        AuthService(ORMSession(bind=eng))  # persiste defaults (admin inclusos)
    finally:
        eng.dispose()


def test_legacy_db_boot_migrates_and_seeds_without_data_loss(tmp_path, monkeypatch):
    """DB legado create_all: stamp + upgrade + seed; dados preservados."""
    url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    eng = create_engine(url)
    try:
        # Cria schema legado (create_all, sem alembic_version) com um dado
        from app.infrastructure.database.base import Base

        Base.metadata.create_all(bind=eng)
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO products (codigo, nome, tipo, preco, estoque) "
                    "VALUES ('P99999', 'GLP Legado', 'GAS', 100, 10)"
                )
            )
        assert "alembic_version" not in inspect(eng).get_table_names()
    finally:
        eng.dispose()

    run_migrations()

    # Seed via fonte única + AuthService (ordem real do boot)
    _boot_seed(url)

    eng = create_engine(url)
    try:
        tables = set(inspect(eng).get_table_names())
        # Migração aplicou o schema completo
        missing = _runtime_tables() - tables
        assert not missing, f"tabelas ausentes após migração: {missing}"
        assert "alembic_version" in tables
        # Dado legado preservado
        with eng.connect() as conn:
            estoque = conn.execute(text("SELECT estoque FROM products WHERE codigo='P99999'")).scalar_one()
            assert estoque == 10
            # Seed RBAC completo (quantidades exatas do catálogo da fonte)
            expected_perms, expected_roles = _seed_catalog_sizes()
            perms = conn.execute(text("SELECT COUNT(*) FROM permissions")).scalar_one()
            roles = conn.execute(text("SELECT COUNT(*) FROM auth_roles")).scalar_one()
            admin = conn.execute(text("SELECT COUNT(*) FROM auth_users WHERE username='admin'")).scalar_one()
        assert perms == expected_perms, f"catálogo de permissões incompleto: {perms}/{expected_perms}"
        assert roles == expected_roles, f"roles padrão ausentes: {roles}/{expected_roles}"
        assert admin >= 1, "usuário admin ausente"
    finally:
        eng.dispose()


def test_fresh_db_boot_creates_and_seeds_everything(tmp_path, monkeypatch):
    """DB novo: cadeia completa + seed RBAC (permissões, roles, admin)."""
    url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    run_migrations()
    _boot_seed(url)

    eng = create_engine(url)
    try:
        tables = set(inspect(eng).get_table_names())
        missing = _runtime_tables() - tables
        assert not missing, f"tabelas ausentes: {missing}"
        assert "alembic_version" in tables
        with eng.connect() as conn:
            perms = conn.execute(text("SELECT COUNT(*) FROM permissions")).scalar_one()
            matrix = conn.execute(text("SELECT COUNT(*) FROM role_permissions")).scalar_one()
            admin = conn.execute(text("SELECT COUNT(*) FROM auth_users WHERE username='admin'")).scalar_one()
        expected_perms, _expected_roles = _seed_catalog_sizes()
        assert perms == expected_perms, f"esperado {expected_perms} permissões, veio {perms}"
        assert matrix > 0
        assert admin >= 1
    finally:
        eng.dispose()
