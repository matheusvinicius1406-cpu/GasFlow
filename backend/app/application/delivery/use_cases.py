"""
Delivery Use Cases — Casos de uso do Entregador.
"""

from datetime import datetime
from typing import Optional, List
from app.domain.delivery.entity import DeliveryDriver
from app.domain.delivery.repository import DeliveryDriverRepository


class CreateDriverUseCase:
    """Caso de uso: Criar um novo entregador."""

    def __init__(self, repository: DeliveryDriverRepository):
        self.repository = repository

    def execute(self, data: dict) -> DeliveryDriver:
        codigo = self.repository.proximo_codigo()

        driver = DeliveryDriver(
            codigo=codigo,
            nome=data["nome"],
            telefone=data["telefone"],
            placa=data.get("placa"),
            ativo=True,
            created_at=datetime.utcnow(),
        )

        return self.repository.criar(driver)


class GetDriverUseCase:
    """Caso de uso: Buscar entregador por código."""

    def __init__(self, repository: DeliveryDriverRepository):
        self.repository = repository

    def execute(self, codigo: str) -> Optional[DeliveryDriver]:
        return self.repository.buscar_por_codigo(codigo)


class ListDriversUseCase:
    """Caso de uso: Listar todos os entregadores."""

    def __init__(self, repository: DeliveryDriverRepository):
        self.repository = repository

    def execute(self) -> List[DeliveryDriver]:
        return self.repository.listar_todos()


class DisableDriverUseCase:
    """Caso de uso: Desativar entregador."""

    def __init__(self, repository: DeliveryDriverRepository):
        self.repository = repository

    def execute(self, codigo: str) -> Optional[DeliveryDriver]:
        return self.repository.desativar(codigo)
