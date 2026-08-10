import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Importa os modelos para registrar as tabelas no metadata.
import app.models.client  # noqa: F401
import app.models.company  # noqa: F401
import app.models.delivery_driver  # noqa: F401
import app.models.order  # noqa: F401
import app.models.product  # noqa: F401
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
def client(db_session):
    """TestClient com o get_db sobrescrito para o banco de teste."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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
