"""Testes LGPD D8 — exportação (portabilidade) e exclusão/anonimização.

Cobre: 401 sem token, 404 para inexistente, payload completo de exportação
(com PII do titular e SEM dados de terceiros), anonimização que preserva
valores fiscais, idempotência, auditoria (auth_audit_log) e a matriz de
permissão (OPERATOR exporta, não apaga; apagar exige customer.*).
"""

from __future__ import annotations

import itertools
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app

_NOME_REMOVIDO = "Cliente removido (LGPD)"

# O proximo_codigo() dos pedidos faz int(last.codigo)+1 — o seed precisa de
# codigo numerico de 6 digitos num range alto para nao colidir com a
# sequencial real nem quebrar a geracao dos proximos testes.
_ORDER_CODIGO = itertools.count(990000)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    res = client.post("/auth/login", json={"username": "admin", "password": "test_password_123"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _db() -> Session:
    from app.infrastructure.database.init_db import engine

    return Session(bind=engine)


def _create_client(api: TestClient, headers: dict, telefone: str | None = None) -> tuple[str, str]:
    """Cria cliente via API; devolve (codigo, telefone normalizado)."""
    phone = telefone or f"5591{uuid.uuid4().hex[:9]}"
    res = api.post(
        "/clients/",
        headers=headers,
        json={
            "nome": "Titular LGPD",
            "telefone": phone,
            "rua": "Rua Titular",
            "numero": "42",
            "complemento": "Ap 1",
            "referencia": "praca",
            "bairro": "Centro",
            "observacoes": "observacao pessoal",
            "email": f"{uuid.uuid4().hex[:8]}@titular.test",
            "tipo": "CONSUMER",
        },
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["codigo"], res.json()["telefone"]


def _seed(db: Session, codigo: str, phone: str) -> dict:
    """Popula todas as tabelas do escopo D8 com PII do titular."""
    from app.infrastructure.repositories.coupon_model import ReferralModel
    from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord
    from app.infrastructure.repositories.financial_models import PaymentModel, ReceivableModel
    from app.infrastructure.repositories.integration_model import ImportedOrderModel
    from app.infrastructure.repositories.lead_model import LeadModel
    from app.infrastructure.repositories.order_item_model import OrderItemModel
    from app.infrastructure.repositories.order_model import OrderModel
    from app.infrastructure.repositories.payment_model import PaymentServiceRecord
    from app.infrastructure.repositories.print_job_model import PrintJobModel
    from app.infrastructure.repositories.route_model import RouteRecord, RouteStopRecord
    from app.infrastructure.repositories.whatsapp_automation_model import AutomationExecutionModel
    from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel, WhatsAppMessageModel

    order_codigo = f"{next(_ORDER_CODIGO):06d}"
    order = OrderModel(
        tenant_id="default",
        codigo=order_codigo,
        client_codigo=codigo,
        address_snapshot=f"Rua Titular, 42 - Centro ({phone})",
        status="DELIVERED",
        subtotal=Decimal("45.50"),
        total=Decimal("45.50"),
        notes="entregar depois das 18h",
    )
    db.add(order)
    db.add(
        OrderItemModel(
            tenant_id="default",
            order_codigo=order_codigo,
            product_codigo="GAS13",
            product_nome="Gas 13kg",
            quantity=1,
            unit_price=Decimal("45.50"),
            subtotal=Decimal("45.50"),
        )
    )
    db.add(
        PaymentModel(
            tenant_id="default",
            order_codigo=order_codigo,
            amount=Decimal("45.50"),
            method="PIX",
            status="PAID",
            notes="pagou em nome da esposa",
        )
    )
    db.add(
        ReceivableModel(
            tenant_id="default",
            customer_codigo=codigo,
            order_codigo=order_codigo,
            original_amount=Decimal("45.50"),
            status="OPEN",
        )
    )

    conversation = WhatsAppConversationModel(
        tenant_id="default",
        account_id="primary",
        phone_number=phone,
        client_codigo=codigo,
        last_message="quero 1 cilindro",
        draft_json='{"produto": "13kg"}',
    )
    db.add(conversation)
    db.flush()
    db.add(
        WhatsAppMessageModel(
            conversation_id=conversation.id,
            direction="INCOMING",
            sender="customer",
            content="meu endereco e Rua Titular, 42",
            raw_payload='{"from": "%s"}' % phone,
        )
    )

    delivery = DeliveryRecord(
        tenant_id="default",
        delivery_id=str(uuid.uuid4()),
        order_id=order_codigo,
        customer_codigo=codigo,
        customer_name="Titular LGPD",
        address_street="Rua Titular",
        address_number="42",
        address_neighborhood="Centro",
        status="DELIVERED",
    )
    db.add(delivery)
    route = RouteRecord(id=str(uuid.uuid4()), tenant_id="default", driver_id=str(uuid.uuid4()), status="COMPLETED")
    db.add(route)
    db.add(
        RouteStopRecord(
            id=str(uuid.uuid4()),
            route_id=route.id,
            delivery_id=delivery.delivery_id,
            customer_name="Titular LGPD",
            customer_phone=phone,
            address_snapshot="Rua Titular, 42 - Centro",
        )
    )
    db.add(
        AutomationExecutionModel(
            tenant_id="default",
            rule_id=1,
            customer_codigo=codigo,
            customer_nome="Titular LGPD",
            customer_phone=phone,
            message_text="Ola, quero gas?",
            status="SENT",
        )
    )
    lead_id = str(uuid.uuid4())
    db.add(
        LeadModel(
            id=lead_id,
            email=f"{uuid.uuid4().hex[:8]}@titular.test",
            name="Titular LGPD",
            phone=phone,
            message="quero gas a domicilio",
            source="site",
        )
    )
    referral_id = str(uuid.uuid4())
    db.add(
        ReferralModel(
            id=referral_id,
            tenant_id="default",
            invite_token=uuid.uuid4().hex,
            referrer_client_codigo="000099",
            referred_client_codigo=codigo,
            referred_name="Titular LGPD",
            referred_phone=phone,
        )
    )
    service_payment_id = str(uuid.uuid4())
    db.add(
        PaymentServiceRecord(
            tenant_id="default",
            id=service_payment_id,
            order_codigo=order_codigo,
            customer_codigo=codigo,
            amount=45.5,
            method_code="PIX",
            method_name="PIX",
            pix_key_used=phone,
            confirmation_notes="cliente ligou",
        )
    )
    print_job_id = str(uuid.uuid4())
    db.add(
        PrintJobModel(
            tenant_id="default",
            id=print_job_id,
            order_id=order_codigo,
            payload=b"ESCPOS-RECEIPT",
            requested_by="admin",
        )
    )
    imported_id = str(uuid.uuid4())
    db.add(
        ImportedOrderModel(
            tenant_id="default",
            id=imported_id,
            integration_id=str(uuid.uuid4()),
            external_id=f"EXT-{uuid.uuid4().hex[:8]}",
            external_data={"cliente": "Titular LGPD"},
            order_data={"nome": "Titular LGPD", "telefone": phone},
            gasflow_order_codigo=order_codigo,
        )
    )
    db.commit()
    return {
        "order_codigo": order_codigo,
        "conversation_id": conversation.id,
        "delivery_id": delivery.delivery_id,
        "lead_id": lead_id,
        "referral_id": referral_id,
        "service_payment_id": service_payment_id,
        "print_job_id": print_job_id,
        "imported_id": imported_id,
    }


# ── Export ─────────────────────────────────────────────


def test_export_requires_auth(client):
    assert client.post("/clients/000001/export").status_code == 401


def test_export_404(client, admin_headers):
    res = client.post("/clients/NAOEXSTE/export", headers=admin_headers)
    assert res.status_code == 404


def test_export_returns_full_payload(client, admin_headers):
    codigo, phone = _create_client(client, admin_headers)
    db = _db()
    try:
        _seed(db, codigo, phone)
    finally:
        db.close()

    # Terceiro: outro cliente com conversa própria — não pode vazar no export A.
    other_codigo, other_phone = _create_client(client, admin_headers)
    db = _db()
    try:
        from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel

        db.add(
            WhatsAppConversationModel(
                tenant_id="default",
                account_id="primary",
                phone_number=other_phone,
                client_codigo=other_codigo,
                last_message="terceiro",
            )
        )
        db.commit()
    finally:
        db.close()

    res = client.post(f"/clients/{codigo}/export", headers=admin_headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["titular"]["codigo"] == codigo
    assert data["cliente"]["nome"] == "Titular LGPD"
    assert data["cliente"]["telefone"] == phone
    assert data["cliente"]["email"].endswith("@titular.test")

    assert len(data["pedidos"]) == 1
    assert data["pedidos"][0]["total"] == 45.5
    assert data["pedidos"][0]["itens"][0]["product_nome"] == "Gas 13kg"
    assert data["pedidos"][0]["address_snapshot"] == f"Rua Titular, 42 - Centro ({phone})"

    assert data["pagamentos"][0]["notes"] == "pagou em nome da esposa"
    assert data["recebiveis"][0]["original_amount"] == 45.5
    assert data["recebiveis"][0]["customer_codigo"] == codigo

    conversas = data["conversas_whatsapp"]
    assert len(conversas) == 1
    assert conversas[0]["phone_number"] == phone
    assert "Rua Titular" in conversas[0]["mensagens"][0]["content"]
    assert phone in conversas[0]["mensagens"][0]["raw_payload"]

    assert data["entregas"][0]["customer_name"] == "Titular LGPD"
    assert data["paradas_de_rota"][0]["customer_phone"] == phone
    assert data["automacoes"][0]["customer_phone"] == phone
    assert data["leads"][0]["phone"] == phone
    assert data["indicacoes"][0]["referred_phone"] == phone
    assert data["pagamentos_servico"][0]["pix_key_used"] == phone
    assert data["pedidos_importados"][0]["order_data"]["telefone"] == phone

    impressoes = data["impressoes"]
    assert impressoes[0]["tem_payload"] is True
    assert "payload" not in impressoes[0]

    # Isolamento: nada do terceiro no export deste titular.
    assert all(conversa["phone_number"] != other_phone for conversa in conversas)
    assert all(conversa["client_codigo"] != other_codigo for conversa in conversas)


# ── Erase ──────────────────────────────────────────────


def test_erase_404(client, admin_headers):
    assert client.delete("/clients/NAOEXSTE/data", headers=admin_headers).status_code == 404


def test_erase_requires_auth(client):
    assert client.delete("/clients/000001/data").status_code == 401


def test_erase_anonymizes_and_preserves_fiscal(client, admin_headers):
    codigo, phone = _create_client(client, admin_headers)
    db = _db()
    try:
        seeded = _seed(db, codigo, phone)
    finally:
        db.close()

    res = client.delete(f"/clients/{codigo}/data", headers=admin_headers)
    assert res.status_code == 200, res.text
    counts = res.json()["registros_afetados"]
    for key in (
        "cliente",
        "conversas",
        "mensagens",
        "pedidos",
        "pagamentos",
        "pagamentos_servico",
        "impressoes",
        "pedidos_importados",
        "entregas",
        "paradas_de_rota",
        "automacoes",
        "leads",
        "indicacoes",
    ):
        assert counts[key] >= 1, key

    # Cadastro anonimizado, código preservado.
    perfil = client.get(f"/clients/{codigo}", headers=admin_headers).json()
    assert perfil["nome"] == _NOME_REMOVIDO
    assert perfil["telefone"] != phone
    assert perfil["telefone"] == f"5500000000{codigo}"
    assert perfil["email"] is None
    assert perfil["ativo"] is False

    db = _db()
    try:
        from app.infrastructure.repositories.coupon_model import ReferralModel
        from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord
        from app.infrastructure.repositories.financial_models import PaymentModel, ReceivableModel
        from app.infrastructure.repositories.integration_model import ImportedOrderModel
        from app.infrastructure.repositories.lead_model import LeadModel
        from app.infrastructure.repositories.order_model import OrderModel
        from app.infrastructure.repositories.payment_model import PaymentServiceRecord
        from app.infrastructure.repositories.print_job_model import PrintJobModel
        from app.infrastructure.repositories.route_model import RouteStopRecord
        from app.infrastructure.repositories.whatsapp_automation_model import AutomationExecutionModel
        from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel, WhatsAppMessageModel

        # Fiscal intacto.
        order = db.query(OrderModel).filter(OrderModel.codigo == seeded["order_codigo"]).one()
        assert order.total == Decimal("45.50")
        assert order.address_snapshot == "[endereço removido - LGPD]"
        assert order.notes is None
        payment = db.query(PaymentModel).filter(PaymentModel.order_codigo == seeded["order_codigo"]).one()
        assert payment.amount == Decimal("45.50")
        assert payment.notes is None
        receivable = db.query(ReceivableModel).filter(ReceivableModel.customer_codigo == codigo).one()
        assert receivable.original_amount == Decimal("45.50")

        # WhatsApp sem PII.
        conversation = (
            db.query(WhatsAppConversationModel).filter(WhatsAppConversationModel.id == seeded["conversation_id"]).one()
        )
        assert conversation.phone_number.startswith("lgpd-")
        assert conversation.last_message is None
        assert conversation.draft_json is None
        message = (
            db.query(WhatsAppMessageModel)
            .filter(WhatsAppMessageModel.conversation_id == seeded["conversation_id"])
            .one()
        )
        assert message.content is None
        assert message.raw_payload is None

        # Operações sem identificadores.
        delivery = db.query(DeliveryRecord).filter(DeliveryRecord.customer_codigo == codigo).one()
        assert delivery.customer_name == ""
        assert delivery.address_street == ""
        stop = db.query(RouteStopRecord).filter(RouteStopRecord.delivery_id == seeded["delivery_id"]).one()
        assert stop.customer_phone == ""
        assert stop.customer_name == ""
        automation = db.query(AutomationExecutionModel).filter(AutomationExecutionModel.customer_codigo == codigo).one()
        assert automation.customer_phone == ""
        assert automation.message_text == ""

        # Marketing / indicações / pagamento de serviço / impressão / import.
        lead = db.query(LeadModel).filter(LeadModel.id == seeded["lead_id"]).one()
        assert lead.phone is None
        assert lead.name is None
        assert lead.email.startswith("lgpd-")
        referral = db.query(ReferralModel).filter(ReferralModel.id == seeded["referral_id"]).one()
        assert referral.referred_phone is None
        assert referral.referred_name is None
        service_payment = (
            db.query(PaymentServiceRecord).filter(PaymentServiceRecord.id == seeded["service_payment_id"]).one()
        )
        assert service_payment.pix_key_used == ""
        assert service_payment.confirmation_notes == ""
        print_job = db.query(PrintJobModel).filter(PrintJobModel.id == seeded["print_job_id"]).one()
        assert print_job.payload is None
        imported = db.query(ImportedOrderModel).filter(ImportedOrderModel.id == seeded["imported_id"]).one()
        assert imported.order_data is None
        assert imported.external_data is None
    finally:
        db.close()


def test_erase_is_idempotent(client, admin_headers):
    codigo, phone = _create_client(client, admin_headers)
    db = _db()
    try:
        _seed(db, codigo, phone)
    finally:
        db.close()

    first = client.delete(f"/clients/{codigo}/data", headers=admin_headers)
    assert first.status_code == 200
    second = client.delete(f"/clients/{codigo}/data", headers=admin_headers)
    assert second.status_code == 200
    perfil = client.get(f"/clients/{codigo}", headers=admin_headers).json()
    assert perfil["nome"] == _NOME_REMOVIDO
    assert perfil["telefone"] == f"5500000000{codigo}"


def test_erase_writes_audit_trail(client, admin_headers):
    codigo, phone = _create_client(client, admin_headers)
    db = _db()
    try:
        _seed(db, codigo, phone)
    finally:
        db.close()

    res = client.delete(f"/clients/{codigo}/data", headers=admin_headers)
    assert res.status_code == 200

    db = _db()
    try:
        from sqlalchemy import text

        rows = db.execute(
            text(
                "SELECT action, resource, resource_id, actor_id FROM auth_audit_log WHERE action IN ('LGPD_ERASED', 'LGPD_EXPORTED') AND resource_id = :codigo"
            ),
            {"codigo": codigo},
        ).fetchall()
    finally:
        db.close()
    assert len(rows) >= 1
    actions = {row[0] for row in rows}
    assert "LGPD_ERASED" in actions
    assert all(row[1] == "client" for row in rows)
    assert all(row[3] for row in rows)  # actor rastreável


def test_export_writes_audit_trail(client, admin_headers):
    codigo, phone = _create_client(client, admin_headers)
    res = client.post(f"/clients/{codigo}/export", headers=admin_headers)
    assert res.status_code == 200

    db = _db()
    try:
        from sqlalchemy import text

        row = db.execute(
            text(
                "SELECT action, resource_id FROM auth_audit_log WHERE action = 'LGPD_EXPORTED' AND resource_id = :codigo"
            ),
            {"codigo": codigo},
        ).fetchone()
    finally:
        db.close()
    assert row is not None
    assert row[0] == "LGPD_EXPORTED"


# ── Permissões ─────────────────────────────────────────


def _create_operator(api: TestClient, admin_headers: dict) -> dict:
    """Cria OPERATOR, troca a senha temporária e devolve headers."""
    username = f"op_lgpd_{uuid.uuid4().hex[:6]}"
    res = api.post(
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
    login = api.post("/auth/login", json={"username": username, "password": "InitialPass1!"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    changed = api.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "InitialPass1!", "new_password": "OperatorPass1!"},
    )
    assert changed.status_code == 200, changed.text
    return {"Authorization": f"Bearer {token}"}


def test_operator_can_export_but_cannot_erase(client, admin_headers):
    codigo, phone = _create_client(client, admin_headers)
    operator_headers = _create_operator(client, admin_headers)

    export = client.post(f"/clients/{codigo}/export", headers=operator_headers)
    assert export.status_code == 200, export.text

    erase = client.delete(f"/clients/{codigo}/data", headers=operator_headers)
    assert erase.status_code == 403

    # Cliente intacto após a tentativa negada.
    perfil = client.get(f"/clients/{codigo}", headers=admin_headers).json()
    assert perfil["nome"] == "Titular LGPD"
    assert perfil["telefone"] == phone
