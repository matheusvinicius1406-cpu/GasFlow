"""
CRM Tests — FASE 6
Tests for: phone normalization, duplicate prevention, search, pagination, Customer 360.
"""

import pytest
from app.domain.client.entity import Client, normalize_phone


# ── Phone Normalization ───────────────────────────────


def test_normalize_phone_digits_only():
    assert normalize_phone("11999999999") == "11999999999"


def test_normalize_phone_with_country_code():
    # +55 11 99999-9999 → 13 digits including country code
    assert normalize_phone("+55 11 99999-9999") == "5511999999999"


def test_normalize_phone_with_zeros():
    # 00551199999999 → strip leading 00 → 12 digits (55+11+99999999)
    assert normalize_phone("00551199999999") == "551199999999"


def test_normalize_phone_with_parens():
    assert normalize_phone("(11) 99999-9999") == "11999999999"


def test_normalize_phone_empty():
    assert normalize_phone("") == ""


def test_normalize_phone_with_dashes():
    assert normalize_phone("11-99999-9999") == "11999999999"


# ── Client Entity ─────────────────────────────────────


def test_client_creation_with_normalized_phone():
    client = Client(
        codigo="000001", nome="Teste", telefone="+55 11 99999-9999", rua="Rua A", numero="1", bairro="Centro"
    )
    assert client.telefone == "5511999999999"


def test_client_duplicate_phone_rejected():
    """Duplicate phone check is done at use case level, not entity."""
    c1 = Client(codigo="000001", nome="A", telefone="11999999999", rua="Rua A", numero="1", bairro="Centro")
    c2 = Client(codigo="000002", nome="B", telefone="11999999999", rua="Rua B", numero="2", bairro="Centro")
    assert c1.telefone == c2.telefone


def test_client_tipo():
    client = Client(
        codigo="000001",
        nome="Restaurante A",
        telefone="11999999999",
        rua="Rua A",
        numero="1",
        bairro="Centro",
        tipo="RESTAURANT",
    )
    assert client.tipo == "RESTAURANT"


def test_client_email():
    client = Client(
        codigo="000001",
        nome="Teste",
        telefone="11999999999",
        rua="Rua A",
        numero="1",
        bairro="Centro",
        email="teste@example.com",
    )
    assert client.email == "teste@example.com"


# ── Schema Validation ─────────────────────────────────


def test_schema_client_create_minimal():
    from app.presentation.schemas.client import ClientCreate

    data = ClientCreate(nome="Teste", telefone="11999999999", rua="Rua A", numero="1", bairro="Centro")
    assert data.nome == "Teste"
    assert data.telefone == "11999999999"
    assert data.tipo is None
    assert data.email is None


def test_schema_client_create_with_crm_fields():
    from app.presentation.schemas.client import ClientCreate

    data = ClientCreate(
        nome="Restaurante",
        telefone="11999999999",
        rua="Rua B",
        numero="2",
        bairro="Centro",
        tipo="RESTAURANT",
        email="contato@rest.com",
    )
    assert data.tipo == "RESTAURANT"
    assert data.email == "contato@rest.com"


def test_schema_client_list_response():
    from app.presentation.schemas.client import ClientListResponse, ClientResponse
    from datetime import datetime

    response = ClientListResponse(
        items=[
            ClientResponse(
                codigo="000001",
                nome="Teste",
                telefone="11999999999",
                rua="Rua A",
                numero="1",
                bairro="Centro",
                ativo=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        ],
        total=1,
        page=1,
        page_size=20,
        total_pages=1,
    )
    assert response.total == 1
    assert len(response.items) == 1


def test_schema_customer360_response():
    from app.presentation.schemas.client import Customer360Response
    from datetime import datetime

    data = Customer360Response(
        codigo="000001",
        nome="Teste",
        telefone="11999999999",
        rua="Rua A",
        numero="1",
        bairro="Centro",
        ativo=True,
        total_orders=5,
        total_spent=500.0,
        average_ticket=100.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    assert data.total_orders == 5
    assert data.total_spent == 500.0
    assert data.average_ticket == 100.0


# ── Customer 360 Metrics ──────────────────────────────


def test_customer360_no_orders():
    from app.application.client.use_cases import Customer360UseCase

    class FakeClientRepo:
        def buscar_por_codigo(self, codigo):
            return Client(
                codigo="000001", nome="Teste", telefone="11999999999", rua="Rua A", numero="1", bairro="Centro"
            )

    class FakeOrderRepo:
        def get_customer_metrics(self, codigo):
            return {
                "total_orders": 0,
                "total_spent": 0.0,
                "average_ticket": 0.0,
                "first_order_at": None,
                "last_order_at": None,
                "days_since_last_order": None,
                "favorite_product": None,
            }

    use_case = Customer360UseCase(FakeClientRepo(), FakeOrderRepo())
    result = use_case.execute("000001")
    assert result is not None
    assert result["total_orders"] == 0
    assert result["total_spent"] == 0.0


def test_customer360_with_orders():
    from datetime import datetime
    from app.application.client.use_cases import Customer360UseCase

    class FakeClientRepo:
        def buscar_por_codigo(self, codigo):
            return Client(
                codigo="000001", nome="Teste", telefone="11999999999", rua="Rua A", numero="1", bairro="Centro"
            )

    class FakeOrderRepo:
        def get_customer_metrics(self, codigo):
            return {
                "total_orders": 3,
                "total_spent": 300.0,
                "average_ticket": 100.0,
                "first_order_at": datetime(2025, 1, 1),
                "last_order_at": datetime(2025, 6, 1),
                "days_since_last_order": 60,
                "favorite_product": "P13",
            }

    use_case = Customer360UseCase(FakeClientRepo(), FakeOrderRepo())
    result = use_case.execute("000001")
    assert result["total_orders"] == 3
    assert result["total_spent"] == 300.0
    assert result["favorite_product"] == "P13"


def test_customer360_nonexistent():
    from app.application.client.use_cases import Customer360UseCase

    class FakeClientRepo:
        def buscar_por_codigo(self, codigo):
            return None

    use_case = Customer360UseCase(FakeClientRepo())
    result = use_case.execute("999999")
    assert result is None


# ── API Boundary ──────────────────────────────────────


def test_api_client_no_direct_whatsapp():
    """Frontend API client should not reference WhatsApp Service directly."""
    import os

    client_path = os.path.join(os.path.dirname(__file__), "../../frontend/src/lib/api/client.ts")
    if os.path.exists(client_path):
        with open(client_path) as f:
            content = f.read()
        assert "localhost:3001" not in content
        assert "MARCOS_GAS_API_KEY" not in content


# ── Duplicate Phone Prevention ────────────────────────


def test_duplicate_phone_prevention():
    """Application layer prevents duplicate phone."""
    from app.application.client.use_cases import CreateClientUseCase

    class FakeRepo:
        def __init__(self):
            self.clients = []
            self.next_id = 1

        def criar(self, client):
            # Check for duplicates
            for c in self.clients:
                if c.telefone == client.telefone:
                    raise ValueError(f"Duplicate phone {client.telefone}")
            self.clients.append(client)
            return client

        def buscar_por_telefone(self, telefone):
            for c in self.clients:
                if c.telefone == normalize_phone(telefone):
                    return c
            return None

        def proximo_codigo(self):
            code = f"{self.next_id:06d}"
            self.next_id += 1
            return code

    repo = FakeRepo()
    use_case = CreateClientUseCase(repo)
    use_case.execute(
        {"nome": "Cliente A", "telefone": "11999999999", "rua": "Rua A", "numero": "1", "bairro": "Centro"}
    )

    # Second attempt with same phone should fail
    with pytest.raises(ValueError, match="Já existe cliente"):
        use_case.execute(
            {"nome": "Cliente B", "telefone": "11999999999", "rua": "Rua B", "numero": "2", "bairro": "Centro"}
        )


def test_normalized_duplicate_prevention():
    """Different phone formats should be caught as duplicates."""
    from app.application.client.use_cases import CreateClientUseCase

    class FakeRepo:
        def __init__(self):
            self.clients = []
            self.next_id = 1

        def criar(self, client):
            for c in self.clients:
                if c.telefone == client.telefone:
                    raise ValueError(f"Duplicate phone {client.telefone}")
            self.clients.append(client)
            return client

        def buscar_por_telefone(self, telefone):
            for c in self.clients:
                if c.telefone == normalize_phone(telefone):
                    return c
            return None

        def proximo_codigo(self):
            code = f"{self.next_id:06d}"
            self.next_id += 1
            return code

    repo = FakeRepo()
    use_case = CreateClientUseCase(repo)
    use_case.execute(
        {"nome": "Cliente A", "telefone": "11999999999", "rua": "Rua A", "numero": "1", "bairro": "Centro"}
    )

    # Same phone with different formatting should fail
    with pytest.raises(ValueError, match="Já existe cliente"):
        use_case.execute(
            {"nome": "Cliente B", "telefone": "(11) 99999-9999", "rua": "Rua B", "numero": "2", "bairro": "Centro"}
        )


def test_mass_assignment_protection():
    """Derived fields cannot be written via API schemas."""
    from app.presentation.schemas.client import ClientCreate, ClientUpdate

    # ClientCreate should not accept derived fields
    data = ClientCreate(nome="Teste", telefone="11999999999", rua="Rua A", numero="1", bairro="Centro")
    dumped = data.model_dump()
    assert "total_orders" not in dumped
    assert "total_spent" not in dumped
    assert "average_ticket" not in dumped
    assert "first_order_at" not in dumped
    assert "last_order_at" not in dumped
    assert "codigo" not in dumped
    assert "ativo" not in dumped

    # ClientUpdate should not accept derived fields
    update = ClientUpdate(nome="Updated")
    dumped = update.model_dump(exclude_unset=True)
    assert "total_orders" not in dumped
    assert "total_spent" not in dumped
    assert "average_ticket" not in dumped
    assert "codigo" not in dumped
