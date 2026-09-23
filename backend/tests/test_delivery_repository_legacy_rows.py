"""Cinto de segurança da listagem de entregadores.

Um registro com `codigo` fora do padrão de 6 dígitos (legado, corrompido ou
semeado por teste de rastreio público) não pode derrubar `GET /delivery-drivers/`
com ValueError — a validação vive na entidade, mas a listagem deve pular a linha
inválida com WARNING e devolver as válidas. Foi a causa exata do flaky
`test_delivery_filtered_by_tenant` no CI (500 intermitente na suíte completa).

Cobre também `proximo_codigo()`: código não-numérico no banco não pode estourar
`int(codigo)` — pula a linha e usa o último código válido.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.delivery.entity import DeliveryDriver
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _seed(db, codigo, nome="Válido", ativo=True):
    db.add(DeliveryDriverModel(tenant_id="default", codigo=codigo, nome=nome, telefone="11999990000", ativo=ativo))
    db.commit()


class TestListagemTolerante:
    def test_linha_invalida_e_pulada_e_validas_voltam(self, db):
        """Registro com codigo alfanumérico não derruba a listagem inteira."""
        _seed(db, "000001", nome="Ana")
        _seed(db, "000002", nome="Bruno")
        # Simula registro legado/teste: codigo fora do padrão (não-número, 10 chars).
        db.add(
            DeliveryDriverModel(
                tenant_id="default", codigo="rev-abc123", nome="Registro Legado", telefone="11999995555", ativo=True
            )
        )
        db.commit()

        drivers = SQLAlchemyDeliveryDriverRepository(db, "default").listar_todos()

        codigos = [d.codigo for d in drivers]
        assert "000001" in codigos and "000002" in codigos
        assert "rev-abc123" not in codigos

    def test_todas_invalidas_devolve_lista_vazia_sem_erro(self, db):
        _seed(db, "rev-abc123", nome="Só Inválido")
        drivers = SQLAlchemyDeliveryDriverRepository(db, "default").listar_todos()
        assert drivers == []

    def test_entity_guarda_continua_validando_criacao(self, db):
        """A validação da entidade NÃO foi afrouxada: criar driver com código
        curto continua rejeitado — o cinto existe só na leitura em lote."""
        with pytest.raises(ValueError, match="6 dígitos"):
            DeliveryDriver(codigo="123", nome="Curto", telefone="11999990000")


class TestProximoCodigoTolerante:
    def test_linha_invalida_no_topo_nao_estoura_int(self, db):
        """`proximo_codigo` ignorava linha com codigo não-numérico —
        `int('rev-abc123')` estourava ValueError na CRIAÇÃO."""
        _seed(db, "000007", nome="Sete")
        db.add(
            DeliveryDriverModel(
                tenant_id="default", codigo="rev-abc123", nome="Legado", telefone="11999995555", ativo=False
            )
        )
        db.commit()

        repo = SQLAlchemyDeliveryDriverRepository(db, "default")
        assert repo.proximo_codigo() == "000008"

    def test_somente_invalidas_recomeca_em_000001(self, db):
        _seed(db, "rev-abc123", nome="Legado")
        repo = SQLAlchemyDeliveryDriverRepository(db, "default")
        assert repo.proximo_codigo() == "000001"
