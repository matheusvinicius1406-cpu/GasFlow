"""
Client Repository Implementation — Implementação SQLAlchemy do repositório de clientes.

FASE 6: Adicionado search, pagination, phone normalization.
"""

from typing import Optional, List, Tuple
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.domain.client.entity import Client, normalize_phone
from app.domain.client.repository import ClientRepository
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.tenant_mixin import TenantMixin


class SQLAlchemyClientRepository(TenantMixin, ClientRepository):
    """Implementação do repositório de clientes usando SQLAlchemy."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        super().__init__(db, tenant_id)

    def _to_entity(self, model: ClientModel) -> Client:
        """Converte modelo SQLAlchemy para entidade de domínio."""
        return Client(
            id=model.id,
            codigo=model.codigo,
            nome=model.nome,
            telefone=model.telefone,
            telefone_secundario=model.telefone_secundario,
            rua=model.rua,
            numero=model.numero,
            complemento=model.complemento,
            referencia=model.referencia,
            bairro=model.bairro,
            observacoes=model.observacoes,
            ativo=model.ativo,
            tipo=model.tipo,
            email=model.email,
            has_name=model.has_name,
            is_whatsapp=model.is_whatsapp,
            last_interaction_at=model.last_interaction_at,
            last_sync_at=model.last_sync_at,
            marketing_status=model.marketing_status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Client) -> ClientModel:
        """Converte entidade de domínio para modelo SQLAlchemy."""
        if entity.id:
            model = self._filter_by_tenant(ClientModel).filter(ClientModel.id == entity.id).first()
            if model:
                model.codigo = entity.codigo
                model.nome = entity.nome
                model.telefone = entity.telefone
                model.telefone_secundario = entity.telefone_secundario
                model.rua = entity.rua
                model.numero = entity.numero
                model.complemento = entity.complemento
                model.referencia = entity.referencia
                model.bairro = entity.bairro
                model.observacoes = entity.observacoes
                model.ativo = entity.ativo
                model.tipo = entity.tipo
                model.email = entity.email
                model.has_name = entity.has_name
                model.is_whatsapp = entity.is_whatsapp
                model.last_interaction_at = entity.last_interaction_at
                model.last_sync_at = entity.last_sync_at
                model.marketing_status = entity.marketing_status
                return model

        return ClientModel(
            tenant_id=self.tenant_id,
            codigo=entity.codigo,
            nome=entity.nome,
            telefone=entity.telefone,
            telefone_secundario=entity.telefone_secundario,
            rua=entity.rua,
            numero=entity.numero,
            complemento=entity.complemento,
            referencia=entity.referencia,
            bairro=entity.bairro,
            observacoes=entity.observacoes,
            ativo=entity.ativo,
            has_name=entity.has_name,
            is_whatsapp=entity.is_whatsapp,
            last_interaction_at=entity.last_interaction_at,
            last_sync_at=entity.last_sync_at,
            marketing_status=entity.marketing_status,
            tipo=entity.tipo,
            email=entity.email,
        )

    def criar(self, client: Client) -> Client:
        model = self._to_model(client)
        model.tenant_id = self.tenant_id
        self.db.add(model)
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            if "UNIQUE constraint failed" in str(e) and "telefone" in str(e):
                raise ValueError(f"Já existe cliente com telefone {client.telefone}")
            raise
        self.db.refresh(model)
        return self._to_entity(model)

    def buscar_por_codigo(self, codigo: str) -> Optional[Client]:
        model = self._filter_by_tenant(ClientModel).filter(ClientModel.codigo == codigo).first()
        return self._to_entity(model) if model else None

    def buscar_por_id(self, id: int) -> Optional[Client]:
        model = self._filter_by_tenant(ClientModel).filter(ClientModel.id == id).first()
        return self._to_entity(model) if model else None

    def buscar_por_telefone(self, telefone: str) -> Optional[Client]:
        normalized = normalize_phone(telefone)
        model = self._filter_by_tenant(ClientModel).filter(ClientModel.telefone == normalized).first()
        return self._to_entity(model) if model else None

    def listar_todos(self) -> List[Client]:
        models = self._filter_by_tenant(ClientModel).filter(ClientModel.ativo == True).all()
        return [self._to_entity(m) for m in models]

    def buscar(
        self,
        query: str = "",
        tipo: Optional[str] = None,
        ativo: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Client], int]:
        """Busca clientes com filtros, paginação e contagem total."""
        q = self._filter_by_tenant(ClientModel)

        if query:
            search = f"%{query}%"
            q = q.filter(
                or_(
                    ClientModel.nome.ilike(search),
                    ClientModel.codigo.ilike(search),
                    ClientModel.telefone.ilike(search),
                    ClientModel.bairro.ilike(search),
                    ClientModel.email.ilike(search) if ClientModel.email is not None else False,
                )
            )

        if tipo is not None:
            q = q.filter(ClientModel.tipo == tipo)

        if ativo is not None:
            q = q.filter(ClientModel.ativo == ativo)

        total = q.count()
        offset = (page - 1) * page_size
        models = q.order_by(ClientModel.nome).offset(offset).limit(page_size).all()

        return [self._to_entity(m) for m in models], total

    def atualizar(self, client: Client) -> Client:
        model = self._to_model(client)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def desativar(self, codigo: str) -> Optional[Client]:
        model = self._filter_by_tenant(ClientModel).filter(ClientModel.codigo == codigo).first()
        if not model:
            return None
        model.ativo = False
        model.updated_at = __import__("datetime").datetime.utcnow()
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def proximo_codigo(self) -> str:
        last = self._filter_by_tenant(ClientModel).order_by(ClientModel.id.desc()).first()
        if not last:
            return "000001"
        next_id = int(last.codigo) + 1
        return f"{next_id:06d}"
