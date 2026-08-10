"""Exceções de domínio do GasFlow.

Serviços levantam estas exceções tipadas em vez de `Exception` genérica.
Um handler global em `app.main` as traduz para respostas HTTP adequadas.
"""


class DomainError(Exception):
    """Erro de regra de negócio. Mapeado para HTTP 422 por padrão."""

    status_code: int = 422

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(DomainError):
    """Recurso não encontrado. Mapeado para HTTP 404."""

    status_code = 404


class ConflictError(DomainError):
    """Conflito de estado (ex.: código duplicado). Mapeado para HTTP 409."""

    status_code = 409


class UnauthorizedError(DomainError):
    """Falha de autenticação (token ausente/inválido). Mapeado para HTTP 401."""

    status_code = 401


class ForbiddenError(DomainError):
    """Sem permissão para a operação (papel insuficiente). Mapeado para HTTP 403."""

    status_code = 403


class ValidationError(DomainError):
    """Violação de regra de negócio. Mapeado para HTTP 422."""

    status_code = 422


class InsufficientStockError(ValidationError):
    """Estoque insuficiente para atender o pedido."""
