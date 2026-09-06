"""
Client Domain Entity — Entidade de negócio do Cliente.

Regras de Negócio:
- Todo cliente possui código único permanente (ex: 000001)
- Código nunca muda, mesmo que troque telefone/endereço/nome
- Um cliente pode ter mais de um telefone
- Cliente pode ser desativado (nunca apagado)
- Telefone é normalizado no momento da criação
- Tipo classifica o cliente (CONSUMER, RESTAURANT, etc.)
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


def normalize_phone(phone: str) -> str:
    """Normaliza telefone brasileiro — remove caracteres não numéricos."""
    if not phone:
        return phone
    digits = re.sub(r"\D", "", phone)
    # Remove leading zeros (international prefix)
    if digits.startswith("00") and len(digits) > 10:
        digits = digits.lstrip("0")
    return digits


@dataclass
class Client:
    """Entidade de domínio do Cliente."""

    codigo: str
    nome: str
    telefone: str
    rua: str
    numero: str
    bairro: str

    id: Optional[int] = None
    telefone_secundario: Optional[str] = None
    complemento: Optional[str] = None
    referencia: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: bool = True

    # CRM fields
    tipo: Optional[str] = None  # CONSUMER, RESTAURANT, COMPANY, SCHOOL, OTHER
    email: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Validações de negócio após construção."""
        if not self.codigo or len(self.codigo) != 6:
            raise ValueError("Código do cliente deve ter 6 dígitos (ex: 000001)")
        if not self.nome or not self.nome.strip():
            raise ValueError("Nome do cliente é obrigatório")
        if not self.telefone or not self.telefone.strip():
            raise ValueError("Telefone do cliente é obrigatório")
        # Normalize phone on construction
        self.telefone = normalize_phone(self.telefone)
        if self.telefone_secundario:
            self.telefone_secundario = normalize_phone(self.telefone_secundario)

    @property
    def endereco_completo(self) -> str:
        """Retorna o endereço completo formatado."""
        parts = [self.rua, f"Nº{self.numero}"]
        if self.complemento:
            parts.append(self.complemento)
        parts.append(f"- {self.bairro}")
        return ", ".join(parts)

    @property
    def crm_name(self) -> str:
        """Nome formatado para CRM (padrão Marcos Gás)."""
        ref = f" ({self.referencia})" if self.referencia else ""
        return f"{self.codigo}= {self.rua} Nº{self.numero}{ref} ({self.nome})"

    def desativar(self):
        """Desativa o cliente (soft delete)."""
        self.ativo = False
        self.updated_at = datetime.utcnow()

    def ativar(self):
        """Ativa o cliente."""
        self.ativo = True
        self.updated_at = datetime.utcnow()

    def atualizar_endereco(
        self, rua: str, numero: str, bairro: str, complemento: Optional[str] = None, referencia: Optional[str] = None
    ):
        """Atualiza o endereço do cliente."""
        self.rua = rua
        self.numero = numero
        self.bairro = bairro
        self.complemento = complemento
        self.referencia = referencia
        self.updated_at = datetime.utcnow()
