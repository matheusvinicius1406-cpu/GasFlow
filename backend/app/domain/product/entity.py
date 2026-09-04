"""
Product Domain Entity — Entidade de negócio do Produto.

Regras de Negócio:
- Todo produto possui código único
- Produto possui nome, tipo (GÁS/ÁGUA), preço e estoque
- Produto pode ser desativado (nunca apagado)
- Estoque não pode ficar negativo
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Product:
    """Entidade de domínio do Produto."""

    codigo: str
    nome: str
    tipo: str  # GAS / AGUA
    preco: float
    estoque: int = 0

    id: Optional[int] = None
    ativo: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Validações de negócio após construção."""
        if not self.codigo or len(self.codigo) != 6:
            raise ValueError("Código do produto deve ter 6 dígitos")
        if not self.nome or not self.nome.strip():
            raise ValueError("Nome do produto é obrigatório")
        if self.preco < 0:
            raise ValueError("Preço do produto não pode ser negativo")
        if self.estoque < 0:
            raise ValueError("Estoque do produto não pode ser negativo")

    def baixar_estoque(self, quantidade: int):
        """Baixa estoque do produto."""
        if quantidade <= 0:
            raise ValueError("Quantidade deve ser maior que 0")
        if self.estoque < quantidade:
            raise ValueError(
                f"Estoque insuficiente. Disponível: {self.estoque}, solicitado: {quantidade}"
            )
        self.estoque -= quantidade
        self.updated_at = datetime.utcnow()

    def repor_estoque(self, quantidade: int):
        """Repor estoque do produto."""
        if quantidade <= 0:
            raise ValueError("Quantidade deve ser maior que 0")
        self.estoque += quantidade
        self.updated_at = datetime.utcnow()

    def atualizar_preco(self, novo_preco: float):
        """Atualiza o preço do produto."""
        if novo_preco < 0:
            raise ValueError("Preço não pode ser negativo")
        self.preco = novo_preco
        self.updated_at = datetime.utcnow()

    def desativar(self):
        """Desativa o produto (soft delete)."""
        self.ativo = False
        self.updated_at = datetime.utcnow()
