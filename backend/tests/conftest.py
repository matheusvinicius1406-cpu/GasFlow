import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Importa os modelos para registrar as tabelas no metadata.
# (antes de `from app.main import app`, para não rebindar o nome `app`.)
import app.models.client  # noqa: F401
import app.models.company  # noqa: F401
import app.models.delivery_driver  # noqa: F401
import app.models.order  # noqa: F401
import app.models.order_item  # noqa: F401
import app.models.order_status_history  # noqa: F401
import app.models.product  # noqa: F401
import app.models.stock_movement  # noqa: F401
import app.models.user  # noqa: F401
from app.database.base import Base
from app.database.dependencies import get_db
from app.main import app


@pytest.fixture
def db_session():
    """Banco SQLite em memória, isolado por teste."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def raw_client(db_session):
    """TestClient SEM autenticação (para testar /auth e respostas 401)."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_company(test_client, empresa_nome, email, senha="senha123", nome="Owner"):
    """Registra empresa + OWNER e devolve o token de acesso."""
    resp = test_client.post(
        "/auth/register",
        json={"empresa_nome": empresa_nome, "nome": nome, "email": email, "senha": senha},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(raw_client):
    """TestClient autenticado como OWNER de uma empresa de teste."""
    token = register_company(raw_client, "Depósito Teste", "owner@test.com")
    raw_client.headers["Authorization"] = f"Bearer {token}"
    return raw_client


@pytest.fixture
def sample_product(client):
    return client.post(
        "/products/",
        json={"nome": "Gás 13kg", "tipo": "GAS", "preco": 100.0, "estoque": 10},
    ).json()


@pytest.fixture
def sample_client(client):
    return client.post(
        "/clients/",
        json={
            "nome": "Maria",
            "telefone": "11999999999",
            "rua": "Rua da Paz",
            "numero": "19",
            "bairro": "Centro",
        },
    ).json()
