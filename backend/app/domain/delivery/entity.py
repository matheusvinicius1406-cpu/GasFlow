"""
DeliveryDriver Domain Entity — Entidade de negócio do Entregador.

Regras de Negócio:
- Todo entregador possui código único
- Entregador possui nome, telefone e placa
- Entregador pode ser desativado (nunca apagado)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class DeliveryDriver:
    """Entidade de domínio do Entregador."""

    codigo: str
    nome: str
    telefone: str

    id: Optional[int] = None
    placa: Optional[str] = None
    ativo: bool = True
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Validações de negócio após construção."""
        if not self.codigo or len(self.codigo) != 6:
            raise ValueError("Código do entregador deve ter 6 dígitos")
        if not self.nome or not self.nome.strip():
            raise ValueError("Nome do entregador é obrigatório")
        if not self.telefone or not self.telefone.strip():
            raise ValueError("Telefone do entregador é obrigatório")

    def desativar(self):
        """Desativa o entregador (soft delete)."""
        self.ativo = False

    def ativar(self):
        """Ativa o entregador."""
        self.ativo = True
