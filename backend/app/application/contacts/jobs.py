"""Jobs do renomeador em lote — Fase 2, etapa 8 (§5).

O padrão é **bounded-batch** (o mesmo de
`POST /whatsapp-automation/process-pending`): cada `processar_proximo_lote`
processa uma faixa e devolve o progresso, então nenhum request passa dos 30 s
do nginx. O estado vive em `contact_jobs`, não na memória do processo — um
restart do backend não perde o ponto de retomada.

Retomada é por **cursor keyset** (último `codigo`/`id` visto). Keyset, e não
offset, porque a base muda durante o passe: offset pularia item quando algo sai
do conjunto candidato, keyset não.

Tipos:

- ``GEOCODE``  — geocodifica contatos pendentes (cache-first por rua, ADR-0004);
- ``OVERPASS`` — preenche ``geocode_cache.intersecoes`` (passe próprio, D14);
  **UPDATE só dessa coluna** — nunca cria linha nem toca lat/lng/cep/status;
- ``APPLY``    — renomeia em lote com a regra dada, em blocos.

Falha de provedor **não** derruba o job: o contato/rua sai da faixa e fica para
triagem (D2/D3). Só erro inesperado (banco) marca o job como ``FALHOU``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_

from app.application.contacts.geocoding import (
    STATUS_PENDENTE as GEO_PENDENTE,
)
from app.application.contacts.geocoding import GeocodingService
from app.application.contacts.organizer import ContactOrganizer
from app.core.logging import setup_logging
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.contact_job_model import (
    STATUS_CONCLUIDO,
    STATUS_FALHOU,
    STATUS_PENDENTE,
    STATUS_PROCESSANDO,
    TIPO_APPLY,
    TIPO_GEOCODE,
    TIPO_OVERPASS,
    ContactJobModel,
)
from app.infrastructure.repositories.geocode_cache_model import GeocodeCacheModel

logger = setup_logging("INFO")

_TIPOS = (TIPO_GEOCODE, TIPO_OVERPASS, TIPO_APPLY)

# Lotes conservadores: geocode/Overpass pagam ~1 s por item (política dos
# provedores públicos), então o request tem de caber nos 30 s do nginx. O apply
# é local e cabe lote grande.
_LOTE_PADRAO = {TIPO_GEOCODE: 20, TIPO_OVERPASS: 15, TIPO_APPLY: 500}
_LOTE_MAX = {TIPO_GEOCODE: 100, TIPO_OVERPASS: 100, TIPO_APPLY: 2000}

_METRICA_ZERO: Dict[str, int] = {
    "ruas": 0,
    "ruas_com_2_ancoras": 0,
    "ruas_com_2_cruzamentos": 0,
    "ruas_com_intersecoes": 0,
    "inversoes_numero": 0,
}


class ContactJobService:
    """Cria, retoma e avança os jobs do renomeador de contatos."""

    def __init__(self, db, repo, tenant_id: str = "default", geocoding=None, overpass=None):
        self.db = db
        self.repo = repo
        self.tenant_id = tenant_id
        self._geocoding = geocoding
        self._overpass = overpass

    # ── Criação / consulta ────────────────────────────────

    def criar_job(
        self,
        tipo: str,
        filtro: Optional[Dict[str, Any]] = None,
        regra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Cria um job ``PENDENTE``. `total` é a contagem inicial dos candidatos."""
        tipo = (tipo or "").strip().upper()
        if tipo not in _TIPOS:
            raise ValueError(f"tipo de job inválido: {tipo!r} (use GEOCODE|OVERPASS|APPLY)")
        if tipo == TIPO_APPLY and not regra:
            raise ValueError("job APPLY exige a regra de renomeação")

        # Filtro vazio não é filtro: `{"bairro": None}` não pode virar critério.
        filtro_limpo = {k: v for k, v in (filtro or {}).items() if v not in (None, "")}
        job = ContactJobModel(
            id=uuid.uuid4().hex,
            tenant_id=self.tenant_id,
            tipo=tipo,
            status=STATUS_PENDENTE,
            filtro=filtro_limpo or None,
            regra=regra or None,
            total=self._contar(tipo, filtro_limpo or None),
            processados=0,
            alterados=0,
            metrica=dict(_METRICA_ZERO) if tipo == TIPO_OVERPASS else None,
        )
        self.db.add(job)
        self.db.commit()
        return self._to_dict(job)

    def status(self, job_id: str) -> Dict[str, Any]:
        job = self._buscar(job_id)
        if job is None:
            raise ValueError("job não encontrado")
        return self._to_dict(job)

    def processar_proximo_lote(self, job_id: str, limite: Optional[int] = None) -> Dict[str, Any]:
        """Processa a próxima faixa. Idempotente em job já concluído/falho."""
        job = self._buscar(job_id)
        if job is None:
            raise ValueError("job não encontrado")
        if job.status in (STATUS_CONCLUIDO, STATUS_FALHOU):
            return self._to_dict(job)

        limite = self._clamp(job.tipo, limite)
        job.status = STATUS_PROCESSANDO
        try:
            concluido = self._processar(job, limite)
            if concluido:
                job.status = STATUS_CONCLUIDO
            job.atualizado_em = datetime.utcnow()
            self.db.commit()
        except Exception as exc:  # erro inesperado (banco) — não engolir
            self.db.rollback()
            falho = self._buscar(job_id)
            if falho is not None:
                falho.status = STATUS_FALHOU
                falho.erro = str(exc)
                falho.atualizado_em = datetime.utcnow()
                self.db.commit()
            logger.warning("contact_job.falhou", extra={"job_id": job_id, "error": str(exc)})
            raise
        return self._to_dict(job)

    # ── Faixas por tipo ───────────────────────────────────

    def _processar(self, job: ContactJobModel, limite: int) -> bool:
        """Roda uma faixa. ``True`` = o job terminou (faixa incompleta)."""
        if job.tipo == TIPO_GEOCODE:
            return self._lote_geocode(job, limite)
        if job.tipo == TIPO_OVERPASS:
            return self._lote_overpass(job, limite)
        return self._lote_apply(job, limite)

    def _lote_geocode(self, job: ContactJobModel, limite: int) -> bool:
        codigos = self._codigos_geocode(job.cursor, limite)
        geocoder = self._geocoder()
        for codigo in codigos:
            cliente = self.repo.buscar_por_codigo(codigo)
            if cliente is not None:
                # Cache-first: rua já cacheada não faz requisição.
                geocoder.geocodificar_cliente(cliente)
                self.repo.atualizar(cliente)
            job.cursor = codigo
            job.processados += 1
        return len(codigos) < limite

    def _lote_overpass(self, job: ContactJobModel, limite: int) -> bool:
        linhas = self._cache_sem_intersecoes(job.cursor, limite)
        servico = self._overpasser()
        metrica = dict(job.metrica or _METRICA_ZERO)
        for linha in linhas:
            passe = servico.buscar_intersecoes(linha.rua or "", linha.lat, linha.lng)
            # UPDATE SÓ de `intersecoes` (§8.4): a linha já existe (é o próprio
            # SELECT), então não se cria nada e lat/lng/cep/geocode_status ficam
            # intactos. `[]` também é resultado válido (triagem, D2).
            linha.intersecoes = list(passe.intersecoes or [])
            metrica["ruas"] += 1
            if passe.ancoras >= 2:
                metrica["ruas_com_2_ancoras"] += 1
            if passe.cruzamentos >= 2:
                metrica["ruas_com_2_cruzamentos"] += 1
            if len(passe.intersecoes or []) >= 2:
                metrica["ruas_com_intersecoes"] += 1
            metrica["inversoes_numero"] += int(passe.inversoes_numero or 0)
            job.alterados += 1 if passe.intersecoes else 0
            job.cursor = str(linha.id)
            job.processados += 1
        job.metrica = metrica
        return len(linhas) < limite

    def _lote_apply(self, job: ContactJobModel, limite: int) -> bool:
        codigos = self._codigos_apply(job.filtro, job.cursor, limite)
        if codigos:
            organizer = ContactOrganizer(self.db, self.repo, self.tenant_id)
            resultado = organizer.apply_rename(job.regra or {}, codes=codigos)
            job.alterados += int(resultado.get("renamed", 0) or 0)
            job.processados += len(codigos)
            job.cursor = codigos[-1]
        return len(codigos) < limite

    # ── Candidatos (keyset) ───────────────────────────────

    def _geocode_pendente_criterios(self) -> List[Any]:
        rua = func.lower(func.trim(ClientModel.rua))
        return [
            ClientModel.tenant_id == self.tenant_id,
            ClientModel.rua.isnot(None),
            rua.notin_(["", "a definir"]),
            or_(
                ClientModel.geocode_status.is_(None),
                ClientModel.geocode_status == "",
                ClientModel.geocode_status == GEO_PENDENTE,
            ),
        ]

    def _codigos_geocode(self, cursor: Optional[str], limite: int) -> List[str]:
        q = self.db.query(ClientModel.codigo).filter(*self._geocode_pendente_criterios())
        if cursor:
            q = q.filter(ClientModel.codigo > cursor)
        return [row[0] for row in q.order_by(ClientModel.codigo).limit(limite).all()]

    def _cache_sem_intersecoes(self, cursor: Optional[str], limite: int) -> List[Any]:
        q = self.db.query(GeocodeCacheModel).filter(GeocodeCacheModel.lat.isnot(None))
        # `intersecoes IS NULL` = rua ainda não passou pelo Overpass. Linha já
        # gravada com `[]` conta como processada (a coluna é o marcador).
        q = q.filter(GeocodeCacheModel.intersecoes.is_(None))
        if cursor:
            q = q.filter(GeocodeCacheModel.id > int(cursor))
        return q.order_by(GeocodeCacheModel.id).limit(limite).all()

    def _filtro_apply_criterios(self, filtro: Optional[Dict[str, Any]]) -> List[Any]:
        criterios: List[Any] = [ClientModel.tenant_id == self.tenant_id]
        filtro = filtro or {}
        bairro = (filtro.get("bairro") or "").strip()
        if bairro:
            criterios.append(func.lower(func.trim(ClientModel.bairro)) == bairro.lower())
        status = (filtro.get("status") or "").strip().upper()
        if status:
            if status == "SEM_ENDERECO":
                rua = func.lower(func.trim(ClientModel.rua))
                criterios.append(or_(ClientModel.rua.is_(None), rua.in_(["", "a definir"])))
            else:
                criterios.append(func.upper(func.coalesce(ClientModel.geocode_status, "")) == status)
        return criterios

    def _codigos_apply(self, filtro: Optional[Dict[str, Any]], cursor: Optional[str], limite: int) -> List[str]:
        q = self.db.query(ClientModel.codigo).filter(*self._filtro_apply_criterios(filtro))
        if cursor:
            q = q.filter(ClientModel.codigo > cursor)
        return [row[0] for row in q.order_by(ClientModel.codigo).limit(limite).all()]

    def _contar(self, tipo: str, filtro: Optional[Dict[str, Any]]) -> int:
        if tipo == TIPO_GEOCODE:
            return int(
                self.db.query(func.count(ClientModel.codigo)).filter(*self._geocode_pendente_criterios()).scalar() or 0
            )
        if tipo == TIPO_OVERPASS:
            return int(
                self.db.query(func.count(GeocodeCacheModel.id))
                .filter(GeocodeCacheModel.lat.isnot(None), GeocodeCacheModel.intersecoes.is_(None))
                .scalar()
                or 0
            )
        return int(
            self.db.query(func.count(ClientModel.codigo)).filter(*self._filtro_apply_criterios(filtro)).scalar() or 0
        )

    # ── Helpers ───────────────────────────────────────────

    def _geocoder(self) -> GeocodingService:
        if self._geocoding is None:
            self._geocoding = GeocodingService(self.db)
        return self._geocoding

    def _overpasser(self):
        if self._overpass is None:
            from app.infrastructure.geocoding.overpass_provider import OverpassProvider

            self._overpass = OverpassProvider()
        return self._overpass

    def _buscar(self, job_id: str) -> Optional[ContactJobModel]:
        return (
            self.db.query(ContactJobModel)
            .filter(ContactJobModel.id == job_id, ContactJobModel.tenant_id == self.tenant_id)
            .first()
        )

    @staticmethod
    def _clamp(tipo: str, limite: Optional[int]) -> int:
        if limite is None:
            return _LOTE_PADRAO[tipo]
        return max(1, min(int(limite), _LOTE_MAX[tipo]))

    def _to_dict(self, job: ContactJobModel) -> Dict[str, Any]:
        return {
            "id": job.id,
            "tipo": job.tipo,
            "status": job.status,
            "cursor": job.cursor,
            "total": int(job.total or 0),
            "processados": int(job.processados or 0),
            "alterados": int(job.alterados or 0),
            "restantes": max(0, int(job.total or 0) - int(job.processados or 0)),
            "metrica": job.metrica or {},
            "erro": job.erro,
            "criado_em": job.criado_em.isoformat() if job.criado_em else None,
            "atualizado_em": job.atualizado_em.isoformat() if job.atualizado_em else None,
        }
