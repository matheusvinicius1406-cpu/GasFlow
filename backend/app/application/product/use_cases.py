"""
Product Use Cases — Casos de uso do Produto.
"""

from datetime import datetime
from typing import Optional, List
from app.domain.product.entity import Product
from app.domain.product.repository import ProductRepository


class CreateProductUseCase:
    """Caso de uso: Criar um novo produto."""

    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def execute(self, data: dict) -> Product:
        codigo = self.repository.proximo_codigo()

        product = Product(
            codigo=codigo,
            nome=data["nome"],
            tipo=data["tipo"],
            preco=data["preco"],
            estoque=data.get("estoque", 0),
            ativo=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        return self.repository.criar(product)


class GetProductUseCase:
    """Caso de uso: Buscar produto por código."""

    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def execute(self, codigo: str) -> Optional[Product]:
        return self.repository.buscar_por_codigo(codigo)


class ListProductsUseCase:
    """Caso de uso: Listar todos os produtos."""

    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def execute(self) -> List[Product]:
        return self.repository.listar_todos()


class UpdateProductUseCase:
    """Caso de uso: Atualizar produto."""

    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def execute(self, codigo: str, data: dict) -> Optional[Product]:
        product = self.repository.buscar_por_codigo(codigo)
        if not product:
            return None

        if data.get("nome") is not None:
            product.nome = data["nome"]
        if data.get("tipo") is not None:
            product.tipo = data["tipo"]
        if data.get("preco") is not None:
            product.preco = data["preco"]
        if data.get("estoque") is not None:
            product.estoque = data["estoque"]
        if data.get("ativo") is not None:
            product.ativo = data["ativo"]

        product.updated_at = datetime.utcnow()
        return self.repository.atualizar(product)


class DisableProductUseCase:
    """Caso de uso: Desativar produto."""

    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def execute(self, codigo: str) -> Optional[Product]:
        return self.repository.desativar(codigo)
