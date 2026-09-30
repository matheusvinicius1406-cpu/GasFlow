"""
Client Repository Implementation — Implementação SQLAlchemy do repositório de clientes.

FASE 6: Adicionado search, pagination, phone normalization.
"""

from typing import Dict, Optional, List, Tuple
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.domain.client.entity import Client, normalize_phone
from app.domain.client.repository import ClientRepository
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.tenant_mixin import TenantMixin


class SQLAlchemyClientRepository(TenantMixin, ClientRepository):
    """Implementação do repositório de clientes usando SQLAlchemy."""

    # Máximo de parâmetros por IN — o SQLite limita variáveis por statement
    # (999), então 500 é o teto seguro para o lote inteiro caber em 1 query.
    _BULK_IN = 500

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
            cidade=model.cidade,
            uf=model.uf,
            nome_importado=model.nome_importado,
            cep=model.cep,
            entre_ruas=model.entre_ruas,
            geocode_status=model.geocode_status,
            lat=model.lat,
            lng=model.lng,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _apply_entity(self, model: ClientModel, entity: Client) -> None:
        """Copia os campos sincronizáveis da entidade para UM modelo existente.

        Extraído de _to_model (etapa 4) para ser o mesmo mapa de campos usado
        pelo salvar_lote — atualizar em lote precisa aplicar EXATAMENTE os
        mesmos campos que atualizar() aplicava linha a linha.
        """
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
        model.cidade = entity.cidade
        model.uf = entity.uf
        model.nome_importado = entity.nome_importado
        model.cep = entity.cep
        model.entre_ruas = entity.entre_ruas
        model.geocode_status = entity.geocode_status
        model.lat = entity.lat
        model.lng = entity.lng

    def _to_model(self, entity: Client) -> ClientModel:
        """Converte entidade de domínio para modelo SQLAlchemy."""
        if entity.id:
            model = self._filter_by_tenant(ClientModel).filter(ClientModel.id == entity.id).first()
            if model:
                self._apply_entity(model, entity)
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
            cidade=entity.cidade,
            uf=entity.uf,
            nome_importado=entity.nome_importado,
            cep=entity.cep,
            entre_ruas=entity.entre_ruas,
            geocode_status=entity.geocode_status,
            lat=entity.lat,
            lng=entity.lng,
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
                raise ValueError(f"Já existe cliente com telefone {client.telefone}") from e
            raise
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

    def buscar_por_telefones(self, telefones: List[str]) -> Dict[str, Client]:
        """Busca N telefones em UMA consulta (IN) — importação em lote (§18/4).

        Os telefones já chegam normalizados pelo ContactService; normalizamos
        de novo só para o chamador não precisar saber disso. Lotes grandes
        são recortados em blocos de _BULK_IN (limite de parâmetros do SQLite).
        """
        found: Dict[str, Client] = {}
        normalized = [t for t in {normalize_phone(t) for t in telefones if t} if t]
        for start in range(0, len(normalized), self._BULK_IN):
            bloco = normalized[start : start + self._BULK_IN]
            models = self._filter_by_tenant(ClientModel).filter(ClientModel.telefone.in_(bloco)).all()
            for model in models:
                found[model.telefone] = self._to_entity(model)
        return found

    def salvar_lote(self, criar: List[Client], atualizar: List[Client]) -> None:
        """Grava criações + atualizações em UMA transação (importação em lote).

        Duas fontes de custo por linha sumiam aqui: (1) cada criar/atualizar
        abria o próprio commit/refresh; (2) atualizar re-consultava o modelo
        por id. Agora os modelos de update saem de um único IN e o commit é um
        só. Qualquer erro desfaz a transação inteira — o ContactService cai no
        caminho linha a linha para que 1 contato ruim não derrube o lote.
        """
        try:
            for entity in criar:
                self.db.add(self._to_model(entity))

            ids = [e.id for e in atualizar if e.id]
            models = {}
            for start in range(0, len(ids), self._BULK_IN):
                bloco = ids[start : start + self._BULK_IN]
                for model in self._filter_by_tenant(ClientModel).filter(ClientModel.id.in_(bloco)).all():
                    models[model.id] = model
            for entity in atualizar:
                model = models.get(entity.id)
                if model is None:
                    raise ValueError(f"Cliente {entity.codigo} não encontrado para atualização em lote")
                self._apply_entity(model, entity)

            self.db.commit()
        except Exception:
            # Tudo ou nada: o ContactService desfaz o bloco inteiro e refaz
            # linha a linha, então 1 contato ruim não derruba os outros.
            self.db.rollback()
            raise

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
