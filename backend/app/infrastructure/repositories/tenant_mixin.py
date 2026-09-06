"""
Tenant Filter Mixin — Adiciona filtering por tenant_id a repositories SQLAlchemy.

Usage:
    class SQLAlchemyClientRepository(TenantMixin, ClientRepository):
        def __init__(self, db: Session, tenant_id: str = "default"):
            super().__init__(db, tenant_id)
"""

from typing import TypeVar
from sqlalchemy.orm import Session, Query

ModelType = TypeVar("ModelType")


class TenantMixin:
    """Mixin that adds tenant_id filtering to SQLAlchemy repositories."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        self.db = db
        self.tenant_id = tenant_id

    def _tenant_filter(self, query: Query, model_class=None) -> Query:
        """Add tenant_id filter to a query if the model has a tenant_id column."""
        if model_class is None:
            # Try to detect model class from query
            try:
                model_class = query.column_descriptions[0]["type"]
            except (AttributeError, IndexError):
                return query

        if hasattr(model_class, "tenant_id"):
            return query.filter(model_class.tenant_id == self.tenant_id)
        return query

    def _filter_by_tenant(self, model_class) -> Query:
        """Create a base query filtered by tenant_id."""
        query = self.db.query(model_class)
        return self._tenant_filter(query, model_class)
