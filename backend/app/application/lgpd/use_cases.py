"""LGPD D8 — portabilidade (export) e exclusão/anonimização (erase) de dados.

Titular = cliente (tabela `clients`). Duas operações, ambas idempotentes e
escopadas por tenant:

- ``ExportClientDataUseCase`` (art. 18, V): pacote JSON com tudo que o
  backend guarda sobre o titular — cliente, pedidos + itens, pagamentos,
  recebíveis, conversas WhatsApp + mensagens, entregas, paradas de rota,
  execuções de automação, leads do site, indicações em que ele é o
  INDICADO, pagamentos de serviço, pedidos importados e impressões
  (sem os bytes ESC/POS). PII de TERCEIROS fica de fora: em `referrals`,
  quem exporta é o titular indicado — os dados de quem o indicou nunca
  saem daqui.
- ``EraseClientDataUseCase`` (art. 18, VI): anonimiza a PII no lugar,
  preservando integridade referencial e fiscal. O ``codigo`` do cliente é
  chave estrutural (não é PII) e nunca muda: pedidos, itens, pagamentos e
  recebíveis seguem apontando para ele com valores intactos. A operação é
  idempotente — repetir não muda nada e responde 200.

O que é apagado (PII) vs. preservado:
  apagado: nome/telefone/endereço/email/observações/coordenadas do
  cliente; conteúdo, rascunho e telefone das conversas; endereço e notes
  dos pedidos; nome/endereço/notas das entregas e paradas; nome/telefone/
  texto das execuções de automação; nome/telefone de leads e indicações;
  chave PIX e notes de pagamentos; payload ESC/POS das impressões;
  dados brutos dos pedidos importados.
  preservado: código do cliente, itens e valores de pedidos, pagamentos e
  recebíveis (fiscal), status e timeline operacionais sem identificadores,
  prova de entrega em binário (exercício de direito em controvérsia —
  consumerista/consumidor).

Fora do escopo D8 (política, não código): a agenda/CRM do serviço
WhatsApp, que espelha contatos do backend e tem ciclo de vida próprio.
Conversas internas do assistente de IA também não são indexadas por
titular — não há join possível.
"""

import logging
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domain.client.entity import Client, normalize_phone
from app.domain.client.repository import ClientRepository
from app.infrastructure.repositories.coupon_model import ReferralModel
from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord
from app.infrastructure.repositories.financial_models import PaymentModel, ReceivableModel
from app.infrastructure.repositories.integration_model import ImportedOrderModel
from app.infrastructure.repositories.lead_model import LeadModel
from app.infrastructure.repositories.order_item_model import OrderItemModel
from app.infrastructure.repositories.order_model import OrderModel
from app.infrastructure.repositories.payment_model import PaymentServiceRecord
from app.infrastructure.repositories.print_job_model import PrintJobModel
from app.infrastructure.repositories.route_model import RouteRecord, RouteStopRecord
from app.infrastructure.repositories.whatsapp_automation_model import AutomationExecutionModel
from app.infrastructure.repositories.whatsapp_model import WhatsAppConversationModel, WhatsAppMessageModel

logger = logging.getLogger("gasflow.lgpd")

# Placeholder não reversível. O prefixo 5500 não corresponde a nenhum DDD
# real, e o sufixo é o codigo único do cliente (único por tenant), então a
# unicidade (tenant_id, telefone) nunca colide — nem na segunda execução.
_NOME_REMOVIDO = "Cliente removido (LGPD)"
_ENDERECO_REMOVIDO = "[endereço removido - LGPD]"
_ANON_PHONE_PREFIX = "5500000000"


def _dump_row(row: Any) -> Dict[str, Any]:
    """Linha SQLAlchemy -> dict plano (Decimal vira float; datetime o FastAPI codifica)."""
    data: Dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        data[column.name] = float(value) if isinstance(value, Decimal) else value
    return data


def _dump_all(rows: List[Any]) -> List[Dict[str, Any]]:
    return [_dump_row(row) for row in rows]


def _phones(client: Client) -> List[str]:
    """Telefones do titular, normalizados, para match em tabelas sem FK."""
    found = {client.telefone, normalize_phone(client.telefone_secundario or "")}
    return sorted(phone for phone in found if phone)


class ExportClientDataUseCase:
    """Caso de uso: exportação completa dos dados pessoais do titular (LGPD art. 18, V)."""

    def __init__(self, db: Session, client_repository: ClientRepository, tenant_id: str) -> None:
        self.db = db
        self.client_repository = client_repository
        self.tenant_id = tenant_id

    def execute(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Monta o pacote de exportação; ``None`` quando o cliente não existe."""
        client = self.client_repository.buscar_por_codigo(codigo)
        if client is None:
            return None
        phones = _phones(client)
        orders = self._orders(codigo)
        order_codigos = [str(order.codigo) for order in orders if order.codigo]
        payload: Dict[str, Any] = {
            "exportado_em": datetime.utcnow(),
            "titular": {"codigo": codigo, "tenant_id": self.tenant_id},
            "cliente": asdict(client),
        }
        payload.update(self._orders_block(orders, order_codigos))
        payload.update(self._financial_block(codigo, order_codigos))
        payload.update(self._whatsapp_block(codigo, phones))
        payload.update(self._operations_block(codigo, phones, order_codigos))
        logger.info("lgpd.export", extra={"codigo": codigo, "tenant": self.tenant_id})
        return payload

    # ── consultas base ──────────────────────────────────

    def _rows(self, model: Any, *criteria: Any) -> List[Any]:
        return self.db.query(model).filter(model.tenant_id == self.tenant_id, *criteria).all()

    def _orders(self, codigo: str) -> List[OrderModel]:
        return (
            self.db.query(OrderModel)
            .filter(OrderModel.tenant_id == self.tenant_id, OrderModel.client_codigo == codigo)
            .order_by(OrderModel.created_at)
            .all()
        )

    def _stops(self, delivery_ids: List[str], phones: List[str]) -> List[RouteStopRecord]:
        # RouteStopRecord não tem tenant_id: o escopo vem do join com a rota.
        criteria: List[Any] = []
        if delivery_ids:
            criteria.append(RouteStopRecord.delivery_id.in_(delivery_ids))
        if phones:
            criteria.append(RouteStopRecord.customer_phone.in_(phones))
        if not criteria:
            return []
        return (
            self.db.query(RouteStopRecord)
            .join(RouteRecord, RouteStopRecord.route_id == RouteRecord.id)
            .filter(RouteRecord.tenant_id == self.tenant_id)
            .filter(or_(*criteria))
            .all()
        )

    # ── blocos do payload ───────────────────────────────

    def _orders_block(self, orders: List[OrderModel], order_codigos: List[str]) -> Dict[str, Any]:
        items_by_order: Dict[str, List[Dict[str, Any]]] = {}
        items = self._rows(OrderItemModel, OrderItemModel.order_codigo.in_(order_codigos))
        for item in items:
            items_by_order.setdefault(str(item.order_codigo), []).append(_dump_row(item))
        pedidos: List[Dict[str, Any]] = []
        for order in orders:
            row = _dump_row(order)
            row["itens"] = items_by_order.get(str(order.codigo), [])
            pedidos.append(row)
        imported = self._rows(ImportedOrderModel, ImportedOrderModel.gasflow_order_codigo.in_(order_codigos))
        return {"pedidos": pedidos, "pedidos_importados": _dump_all(imported)}

    def _financial_block(self, codigo: str, order_codigos: List[str]) -> Dict[str, Any]:
        payments = self._rows(PaymentModel, PaymentModel.order_codigo.in_(order_codigos))
        receivables = self._rows(ReceivableModel, ReceivableModel.customer_codigo == codigo)
        return {"pagamentos": _dump_all(payments), "recebiveis": _dump_all(receivables)}

    def _whatsapp_block(self, codigo: str, phones: List[str]) -> Dict[str, Any]:
        conversations = (
            self.db.query(WhatsAppConversationModel)
            .filter(
                WhatsAppConversationModel.tenant_id == self.tenant_id,
                or_(
                    WhatsAppConversationModel.client_codigo == codigo,
                    WhatsAppConversationModel.phone_number.in_(phones),
                ),
            )
            .order_by(WhatsAppConversationModel.id)
            .all()
        )
        conv_ids = [conversation.id for conversation in conversations]
        messages_by_conv: Dict[int, List[Dict[str, Any]]] = {}
        if conv_ids:
            messages = (
                self.db.query(WhatsAppMessageModel)
                .filter(WhatsAppMessageModel.conversation_id.in_(conv_ids))
                .order_by(WhatsAppMessageModel.created_at)
                .all()
            )
            for message in messages:
                messages_by_conv.setdefault(message.conversation_id, []).append(_dump_row(message))
        payload: List[Dict[str, Any]] = []
        for conversation in conversations:
            row = _dump_row(conversation)
            row["mensagens"] = messages_by_conv.get(conversation.id, [])
            payload.append(row)
        return {"conversas_whatsapp": payload}

    def _operations_block(self, codigo: str, phones: List[str], order_codigos: List[str]) -> Dict[str, Any]:
        deliveries = self._rows(DeliveryRecord, DeliveryRecord.customer_codigo == codigo)
        stops = self._stops([str(d.delivery_id) for d in deliveries], phones)
        automations = self._rows(AutomationExecutionModel, AutomationExecutionModel.customer_codigo == codigo)
        service_payments = self._rows(PaymentServiceRecord, PaymentServiceRecord.customer_codigo == codigo)
        print_jobs = self._rows(PrintJobModel, PrintJobModel.order_id.in_(order_codigos))
        referrals = self._rows(
            ReferralModel,
            or_(ReferralModel.referred_client_codigo == codigo, ReferralModel.referred_phone.in_(phones)),
        )
        leads = self.db.query(LeadModel).filter(LeadModel.phone.in_(phones)).all() if phones else []
        impressions = []
        for job in print_jobs:
            row = _dump_row(job)
            row.pop("payload", None)  # bytes ESC/POS não são JSON — sai só a flag.
            row["tem_payload"] = job.payload is not None
            impressions.append(row)
        return {
            "entregas": _dump_all(deliveries),
            "paradas_de_rota": _dump_all(stops),
            "automacoes": _dump_all(automations),
            "pagamentos_servico": _dump_all(service_payments),
            "indicacoes": _dump_all(referrals),
            "leads": _dump_all(leads),
            "impressoes": impressions,
        }


class EraseClientDataUseCase:
    """Caso de uso: anonimização da PII do titular (LGPD art. 18, VI), preservando fiscal."""

    def __init__(self, db: Session, client_repository: ClientRepository, tenant_id: str) -> None:
        self.db = db
        self.client_repository = client_repository
        self.tenant_id = tenant_id

    def execute(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Anonimiza tudo do titular; ``None`` quando o cliente não existe.

        As mutações ficam na mesma sessão do repositório: o commit único
        acontece no ``atualizar`` do cliente, no fim — ou nada é gravado.
        """
        client = self.client_repository.buscar_por_codigo(codigo)
        if client is None:
            return None
        phones = _phones(client)
        counts: Dict[str, int] = {}
        counts.update(self._erase_whatsapp(codigo, phones))
        counts.update(self._erase_orders(codigo))
        counts.update(self._erase_financial(codigo))
        counts.update(self._erase_operations(codigo, phones))
        counts.update(self._erase_marketing(codigo, phones))
        counts["cliente"] = self._erase_client(client, codigo)
        logger.info("lgpd.erase", extra={"codigo": codigo, "tenant": self.tenant_id, "counts": counts})
        return {"codigo": codigo, "anonimizado_em": datetime.utcnow(), "registros_afetados": counts}

    # ── helpers ─────────────────────────────────────────

    def _rows(self, model: Any, *criteria: Any) -> List[Any]:
        return self.db.query(model).filter(model.tenant_id == self.tenant_id, *criteria).all()

    def _orders(self, codigo: str) -> List[OrderModel]:
        return (
            self.db.query(OrderModel)
            .filter(OrderModel.tenant_id == self.tenant_id, OrderModel.client_codigo == codigo)
            .all()
        )

    def _stops(self, delivery_ids: List[str], phones: List[str]) -> List[RouteStopRecord]:
        # RouteStopRecord não tem tenant_id: o escopo vem do join com a rota.
        criteria: List[Any] = []
        if delivery_ids:
            criteria.append(RouteStopRecord.delivery_id.in_(delivery_ids))
        if phones:
            criteria.append(RouteStopRecord.customer_phone.in_(phones))
        if not criteria:
            return []
        return (
            self.db.query(RouteStopRecord)
            .join(RouteRecord, RouteStopRecord.route_id == RouteRecord.id)
            .filter(RouteRecord.tenant_id == self.tenant_id)
            .filter(or_(*criteria))
            .all()
        )

    # ── passos da anonimização ──────────────────────────

    def _erase_whatsapp(self, codigo: str, phones: List[str]) -> Dict[str, int]:
        conversations = (
            self.db.query(WhatsAppConversationModel)
            .filter(
                WhatsAppConversationModel.tenant_id == self.tenant_id,
                or_(
                    WhatsAppConversationModel.client_codigo == codigo,
                    WhatsAppConversationModel.phone_number.in_(phones),
                ),
            )
            .all()
        )
        conv_ids = [conversation.id for conversation in conversations]
        messages_count = 0
        if conv_ids:
            messages = (
                self.db.query(WhatsAppMessageModel).filter(WhatsAppMessageModel.conversation_id.in_(conv_ids)).all()
            )
            for message in messages:
                message.content = None
                message.raw_payload = None
            messages_count = len(messages)
        for conversation in conversations:
            # "lgpd-<id>" é único (id é PK global) e respeita o limite de 20
            # chars da coluna — a unicidade (tenant, account, phone) não colide.
            conversation.phone_number = f"lgpd-{conversation.id}"
            conversation.last_message = None
            conversation.draft_json = None
        return {"conversas": len(conversations), "mensagens": messages_count}

    def _erase_orders(self, codigo: str) -> Dict[str, int]:
        orders = self._orders(codigo)
        for order in orders:
            order.address_snapshot = _ENDERECO_REMOVIDO
            order.notes = None
        return {"pedidos": len(orders)}

    def _erase_financial(self, codigo: str) -> Dict[str, int]:
        order_codigos = [str(order.codigo) for order in self._orders(codigo) if order.codigo]
        payments = self._rows(PaymentModel, PaymentModel.order_codigo.in_(order_codigos))
        for payment in payments:
            payment.notes = None
        service_payments = self._rows(PaymentServiceRecord, PaymentServiceRecord.customer_codigo == codigo)
        for service_payment in service_payments:
            service_payment.pix_key_used = ""
            service_payment.pix_copy_paste = ""
            service_payment.confirmation_notes = ""
            service_payment.refund_reason = ""
        print_jobs = self._rows(PrintJobModel, PrintJobModel.order_id.in_(order_codigos))
        for job in print_jobs:
            job.payload = None
        imported = self._rows(ImportedOrderModel, ImportedOrderModel.gasflow_order_codigo.in_(order_codigos))
        for order_import in imported:
            order_import.external_data = None
            order_import.order_data = None
        return {
            "pagamentos": len(payments),
            "pagamentos_servico": len(service_payments),
            "impressoes": len(print_jobs),
            "pedidos_importados": len(imported),
        }

    def _erase_operations(self, codigo: str, phones: List[str]) -> Dict[str, int]:
        deliveries = self._rows(DeliveryRecord, DeliveryRecord.customer_codigo == codigo)
        for delivery in deliveries:
            delivery.customer_name = ""
            delivery.address_street = ""
            delivery.address_number = ""
            delivery.address_complement = ""
            delivery.address_neighborhood = ""
            delivery.address_city = ""
            delivery.address_state = ""
            delivery.address_zip_code = ""
            delivery.address_reference = ""
            delivery.address_lat = None
            delivery.address_lng = None
            delivery.notes = ""
            delivery.failure_notes = ""
        stops = self._stops([str(delivery.delivery_id) for delivery in deliveries], phones)
        for stop in stops:
            stop.customer_name = ""
            stop.customer_phone = ""
            stop.address_snapshot = ""
        automations = self._rows(AutomationExecutionModel, AutomationExecutionModel.customer_codigo == codigo)
        for automation in automations:
            automation.customer_nome = ""
            automation.customer_phone = ""
            automation.message_text = ""
            automation.error_message = None
        return {"entregas": len(deliveries), "paradas_de_rota": len(stops), "automacoes": len(automations)}

    def _erase_marketing(self, codigo: str, phones: List[str]) -> Dict[str, int]:
        leads = self.db.query(LeadModel).filter(LeadModel.phone.in_(phones)).all() if phones else []
        for lead in leads:
            lead.name = None
            lead.phone = None
            lead.message = None
            lead.email = f"lgpd-{lead.id}@removido.invalid"
        referrals = self._rows(
            ReferralModel,
            or_(ReferralModel.referred_client_codigo == codigo, ReferralModel.referred_phone.in_(phones)),
        )
        for referral in referrals:
            referral.referred_name = None
            referral.referred_phone = None
        return {"leads": len(leads), "indicacoes": len(referrals)}

    def _erase_client(self, client: Client, codigo: str) -> int:
        client.nome = _NOME_REMOVIDO
        client.telefone = f"{_ANON_PHONE_PREFIX}{codigo}"
        client.telefone_secundario = None
        client.email = None
        client.rua = ""
        client.numero = ""
        client.complemento = None
        client.referencia = None
        client.bairro = ""
        client.observacoes = None
        client.ativo = False
        client.nome_importado = None
        client.cidade = None
        client.uf = None
        client.cep = None
        client.entre_ruas = None
        client.lat = None
        client.lng = None
        client.geocode_status = None
        client.marketing_status = "OPTED_OUT"
        client.has_name = None
        client.is_whatsapp = None
        client.last_interaction_at = None
        client.last_sync_at = None
        client.updated_at = datetime.utcnow()
        # Commit único da transação LGPD — tudo ou nada.
        self.client_repository.atualizar(client)
        return 1
