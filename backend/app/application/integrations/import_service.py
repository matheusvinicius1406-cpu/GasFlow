"""
Integration Service — processamento de pedidos importados de sites de revendas.

Fluxo:
  agente extrai pedido do site → POST /integrations/import (com import_token)
  → normaliza → garante cliente (por telefone/nome, cria se não existir)
  → garante produto (por código/nome, cria se não existir, com estoque inicial)
  → cria pedido via CreateOrderUseCase (preço/estoque do backend são autoridade)
  → registra ImportedOrder + SyncLog + last_sync na integração

Importante: o agente é executado pelo próprio dono da revenda sobre o PRÓPRIO
site (ou site autorizado). Nenhuma técnica de evasão/bypass é usada — apenas
HTTP com as credenciais configuradas.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.application.order.use_cases import CreateOrderUseCase
from app.infrastructure.repositories.client_model import ClientModel
from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
from app.infrastructure.repositories.integration_model import (
    ImportedOrderModel,
    IntegrationModel,
    SyncLogModel,
)
from app.infrastructure.repositories.inventory_model import InventoryModel
from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
from app.infrastructure.repositories.order_item_repository import SQLAlchemyOrderItemRepository
from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
from app.infrastructure.repositories.product_model import ProductModel
from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository

logger = logging.getLogger("gasflow")

BR_PHONE_RE = re.compile(r"\(?\d{2}\)?\s?9?\d{4}-?\d{4}")


class IntegrationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _digits(s: Optional[str]) -> str:
    return re.sub(r"\D", "", s or "")


def parse_money(value: Any) -> Optional[float]:
    """Converte 'R$ 1.234,56' / '1234.56' / 12.3 → float ou None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"[^\d,.]", "", text)
    if not text:
        return None
    # heurística pt-BR: 1.234,56 → 1234.56 | 1234,56 → 1234.56
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


@dataclass
class NormalizedItem:
    product_name: str = ""
    product_codigo: str = ""
    quantity: int = 1
    unit_price: Optional[float] = None


@dataclass
class NormalizedOrder:
    external_id: str = ""
    client_name: str = ""
    client_phone: str = ""
    client_email: str = ""
    address: str = ""
    items: List[NormalizedItem] = field(default_factory=list)
    total: Optional[float] = None
    delivery_fee: Optional[float] = None
    payment_method: Optional[str] = None
    status: str = ""
    notes: str = ""


def normalize_order(raw: Dict[str, Any]) -> NormalizedOrder:
    """Converte o dicionário cru (agente/site) em NormalizedOrder.

    Aceita chaves em português ou inglês, extras ignorados.
    """

    def pick(*keys: str) -> Any:
        for k in keys:
            if k in raw and raw[k] not in (None, ""):
                return raw[k]
        return None

    order = NormalizedOrder()
    order.external_id = str(pick("external_id", "id", "codigo", "numero", "number", "order_id") or "")
    order.client_name = str(pick("client_name", "cliente", "client", "nome", "customer", "name") or "")
    order.client_phone = str(pick("client_phone", "telefone", "phone", "whatsapp", "celular") or "")
    order.client_email = str(pick("client_email", "email", "e-mail") or "")
    order.address = str(pick("address", "endereco", "endereço", "delivery_address") or "")
    order.total = parse_money(pick("total", "valor_total", "valor", "amount"))
    order.delivery_fee = parse_money(pick("delivery_fee", "frete", "entrega", "shipping"))
    order.payment_method = pick("payment_method", "pagamento", "forma_pagamento")
    order.status = str(pick("status", "situacao") or "")
    order.notes = str(pick("notes", "observacoes", "observações", "note") or "")

    raw_items = raw.get("items") or raw.get("itens") or raw.get("products") or raw.get("produtos") or []
    if isinstance(raw_items, list):
        for it in raw_items:
            if not isinstance(it, dict):
                # formato "2x P13" ou "P13"
                text = str(it).strip()
                m = re.match(r"^(\d+)\s*[xX×]\s*(.+)$", text)
                if m:
                    order.items.append(NormalizedItem(product_name=m.group(2).strip(), quantity=int(m.group(1))))
                elif text:
                    order.items.append(NormalizedItem(product_name=text))
                continue
            qty_raw = it.get("quantity", it.get("quantidade", it.get("qty", 1)))
            try:
                qty = int(float(qty_raw))
            except (TypeError, ValueError):
                qty = 1
            order.items.append(
                NormalizedItem(
                    product_name=str(
                        it.get("product_name", it.get("nome", it.get("produto", it.get("name", ""))) or "")
                    ),
                    product_codigo=str(it.get("product_codigo", it.get("codigo", it.get("code", ""))) or ""),
                    quantity=qty if qty > 0 else 1,
                    unit_price=parse_money(it.get("unit_price", it.get("preco", it.get("price", None)))),
                )
            )
    return order


@dataclass
class ImportResult:
    imported_order_id: str
    status: str  # success | error
    gasflow_order_codigo: Optional[str] = None
    error_message: Optional[str] = None


class IntegrationImportService:
    def __init__(self, db: DBSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

        import os

        try:
            self.initial_stock = int(os.getenv("INTEGRATIONS_INITIAL_STOCK", "100"))
        except ValueError:
            self.initial_stock = 100

    # ── Lookups ──────────────────────────────────────────

    def get_integration(self, integration_id: str) -> Optional[IntegrationModel]:
        return (
            self.db.query(IntegrationModel)
            .filter(
                IntegrationModel.id == integration_id,
                IntegrationModel.tenant_id == self.tenant_id,
            )
            .first()
        )

    def list_integrations(self, include_inactive: bool = True) -> List[IntegrationModel]:
        q = self.db.query(IntegrationModel).filter(IntegrationModel.tenant_id == self.tenant_id)
        if not include_inactive:
            q = q.filter(IntegrationModel.is_active.is_(True))
        return q.order_by(IntegrationModel.created_at.desc()).all()

    # ── Auto-create de cliente/produto ───────────────────

    def _find_client(self, order: NormalizedOrder) -> Optional[ClientModel]:
        q = self.db.query(ClientModel).filter(ClientModel.tenant_id == self.tenant_id)
        digits = _digits(order.client_phone)
        if digits:
            row = q.filter(ClientModel.telefone.contains(digits[-10:] if len(digits) >= 10 else digits)).first()
            if row:
                return row
        name = order.client_name.strip().lower()
        if name:
            row = q.filter(ClientModel.nome.ilike(name)).first()
            if row:
                return row
        return None

    def _client_codigo(self) -> str:
        repo = SQLAlchemyClientRepository(self.db, self.tenant_id)
        return repo.proximo_codigo()

    def _ensure_client(self, order: NormalizedOrder) -> ClientModel:
        existing = self._find_client(order)
        if existing:
            return existing

        address_parts = [p.strip() for p in re.split(r"[,;-]", order.address) if p.strip()] if order.address else []
        rua = address_parts[0] if address_parts else "A confirmar"
        numero = address_parts[1] if len(address_parts) > 1 else "S/N"
        bairro = address_parts[2] if len(address_parts) > 2 else "A confirmar"
        # clients tem UNIQUE (tenant_id, telefone) — sem telefone conhecido,
        # gera um placeholder único (o operador corrige depois).
        phone = order.client_phone or f"IMPORT-{uuid.uuid4().hex[:10]}"

        model = ClientModel(
            tenant_id=self.tenant_id,
            codigo=self._client_codigo(),
            nome=order.client_name.strip() or f"Cliente {order.external_id or 'importado'}",
            telefone=phone,
            rua=rua[:120],
            numero=numero[:20],
            bairro=bairro[:80],
            observacoes=f"Importado de integração externa em {datetime.utcnow().isoformat()}",
            ativo=True,
            tipo="CONSUMER",
            email=order.client_email or None,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        logger.info("integration client auto-created", extra={"client_codigo": model.codigo})
        return model

    def _find_product(self, item: NormalizedItem) -> Optional[ProductModel]:
        q = self.db.query(ProductModel).filter(ProductModel.tenant_id == self.tenant_id)
        if item.product_codigo:
            row = q.filter(ProductModel.codigo == item.product_codigo).first()
            if row:
                return row
        name = item.product_name.strip().lower()
        if name:
            row = q.filter(ProductModel.nome.ilike(name)).first()
            if row:
                return row
        return None

    def _product_codigo(self) -> str:
        repo = SQLAlchemyProductRepository(self.db, self.tenant_id)
        return repo.proximo_codigo()

    def _ensure_product(self, item: NormalizedItem) -> ProductModel:
        existing = self._find_product(item)
        if existing:
            return existing

        name = item.product_name.strip()
        if not name and item.product_codigo:
            name = item.product_codigo
        if not name:
            raise IntegrationError("ITEM_INVALID", "Item sem nome nem código de produto.")

        # preço: unit_price informado > total/qty do pedido > 0 (operador ajusta)
        price = item.unit_price or 0.0
        model = ProductModel(
            tenant_id=self.tenant_id,
            codigo=item.product_codigo.strip() if item.product_codigo else self._product_codigo(),
            nome=name[:100],
            tipo="OUTROS",
            preco=price,
            estoque=self.initial_stock,
            ativo=True,
        )
        self.db.add(model)
        self.db.flush()
        # estoque inicial no inventário (autoridade de stock) — ajustável pelo operador
        self.db.add(
            InventoryModel(
                tenant_id=self.tenant_id,
                product_codigo=model.codigo,
                quantity=self.initial_stock,
                minimum_quantity=0,
            )
        )
        self.db.commit()
        self.db.refresh(model)
        logger.info("integration product auto-created", extra={"product_codigo": model.codigo})
        return model

    # ── Processamento ────────────────────────────────────

    def process_order(self, integration: IntegrationModel, raw_order: Dict[str, Any]) -> ImportResult:
        """Importa 1 pedido: registra ImportedOrder e tenta criar o pedido no GasFlow."""
        order = normalize_order(raw_order)

        # dedupe: external_id JÁ IMPORTADO COM SUCESSO nesta integração?
        # (imports com erro NÃO bloqueiam retry — reprocess depende disso)
        if order.external_id:
            dup = (
                self.db.query(ImportedOrderModel)
                .filter(
                    ImportedOrderModel.integration_id == integration.id,
                    ImportedOrderModel.external_id == order.external_id,
                    ImportedOrderModel.tenant_id == self.tenant_id,
                    ImportedOrderModel.status == "success",
                )
                .first()
            )
            if dup:
                return ImportResult(
                    imported_order_id=dup.id,
                    status=dup.status,
                    gasflow_order_codigo=dup.gasflow_order_codigo,
                    error_message="Já importado (duplicado ignorado)",
                )

        imported = ImportedOrderModel(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            integration_id=integration.id,
            external_id=order.external_id or f"auto-{uuid.uuid4().hex[:8]}",
            external_data=raw_order,
            status="pending",
            created_at=datetime.utcnow(),
        )
        self.db.add(imported)

        try:
            if not order.items:
                raise IntegrationError("NO_ITEMS", "Pedido sem itens.")

            client = self._ensure_client(order)

            # resolve itens → product_codigo (criando quando necessário)
            items_payload = []
            for item in order.items:
                product = self._ensure_product(item)
                items_payload.append({"product_codigo": product.codigo, "quantity": item.quantity})

            use_case = CreateOrderUseCase(
                order_repo=SQLAlchemyOrderRepository(self.db, self.tenant_id),
                order_item_repo=SQLAlchemyOrderItemRepository(self.db, self.tenant_id),
                client_repo=SQLAlchemyClientRepository(self.db, self.tenant_id),
                product_repo=SQLAlchemyProductRepository(self.db, self.tenant_id),
                inventory_repo=SQLAlchemyInventoryRepository(self.db, self.tenant_id),
            )
            created = use_case.execute(
                {
                    "client_codigo": client.codigo,
                    "items": items_payload,
                    "delivery_fee": order.delivery_fee or 0.0,
                    "payment_method": order.payment_method,
                    "source": "INTEGRATION",
                    "notes": (f"[{integration.name}] " if integration.name else "") + (order.notes or ""),
                }
            )

            imported.status = "success"
            imported.gasflow_order_codigo = created.codigo
            imported.processed_at = datetime.utcnow()
            self.db.commit()
            return ImportResult(
                imported_order_id=imported.id,
                status="success",
                gasflow_order_codigo=created.codigo,
            )
        except (IntegrationError, ValueError) as e:
            self.db.rollback()
            # rollback detacha objetos pending — re-anexa antes de persistir o erro
            self.db.add(imported)
            imported.error_message = str(e)[:500]
            imported.status = "error"
            imported.processed_at = datetime.utcnow()
            self.db.commit()
            return ImportResult(imported_order_id=imported.id, status="error", error_message=str(e)[:500])
        except Exception as e:  # noqa: BLE001 — import não pode derrubar o sync
            self.db.rollback()
            self.db.add(imported)
            imported.error_message = f"erro inesperado: {e}"[:500]
            imported.status = "error"
            imported.processed_at = datetime.utcnow()
            self.db.commit()
            return ImportResult(imported_order_id=imported.id, status="error", error_message=str(e)[:500])

    def process_sync_run(
        self,
        integration: IntegrationModel,
        orders: List[Dict[str, Any]],
        agent_errors: Optional[List[Dict[str, Any]]] = None,
        trigger: str = "manual",
    ) -> SyncLogModel:
        """Importa um lote do agente e registra o SyncLog da execução."""
        started = datetime.utcnow()
        results = [self.process_order(integration, o) for o in orders]
        agent_errors = agent_errors or []

        total_found = len(orders) + len(agent_errors)
        total_imported = sum(1 for r in results if r.status == "success")
        total_errors = sum(1 for r in results if r.status == "error") + len(agent_errors)

        error_details = [{"message": r.error_message, "origin": "import"} for r in results if r.status == "error"] + [
            {"message": e.get("message"), "external_ref": e.get("external_ref"), "origin": "agent"}
            for e in agent_errors
        ]

        status = "success"
        if total_errors and total_imported:
            status = "partial"
        elif total_errors and not total_imported:
            status = "error"

        log = SyncLogModel(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            integration_id=integration.id,
            started_at=started,
            finished_at=datetime.utcnow(),
            status=status,
            trigger=trigger,
            total_found=total_found,
            total_imported=total_imported,
            total_errors=total_errors,
            error_details=error_details or None,
        )
        integration.last_sync_at = datetime.utcnow()
        integration.last_sync_status = status
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    # ── Consultas p/ API ─────────────────────────────────

    def list_imported_orders(
        self, integration_id: str, status: Optional[str] = None, limit: int = 200
    ) -> List[ImportedOrderModel]:
        q = self.db.query(ImportedOrderModel).filter(
            ImportedOrderModel.integration_id == integration_id,
            ImportedOrderModel.tenant_id == self.tenant_id,
        )
        if status:
            q = q.filter(ImportedOrderModel.status == status)
        return q.order_by(ImportedOrderModel.created_at.desc()).limit(min(limit, 500)).all()

    def list_sync_logs(self, integration_id: str, limit: int = 50) -> List[SyncLogModel]:
        return (
            self.db.query(SyncLogModel)
            .filter(
                SyncLogModel.integration_id == integration_id,
                SyncLogModel.tenant_id == self.tenant_id,
            )
            .order_by(SyncLogModel.started_at.desc())
            .limit(min(limit, 200))
            .all()
        )

    def get_imported_order(self, imported_order_id: str) -> Optional[ImportedOrderModel]:
        return (
            self.db.query(ImportedOrderModel)
            .filter(
                ImportedOrderModel.id == imported_order_id,
                ImportedOrderModel.tenant_id == self.tenant_id,
            )
            .first()
        )

    def reprocess(self, imported_order_id: str) -> ImportResult:
        """Reimporta um pedido com erro (ex.: após repor estoque)."""
        imported = self.get_imported_order(imported_order_id)
        if not imported:
            raise IntegrationError("NOT_FOUND", "Pedido importado não encontrado.", 404)
        if imported.status == "success":
            raise IntegrationError("ALREADY_OK", "Pedido já processado com sucesso.", 409)

        integration = self.get_integration(imported.integration_id)
        if not integration:
            raise IntegrationError("NOT_FOUND", "Integração não encontrada.", 404)

        result = self.process_order(integration, imported.external_data or {})
        return result

    # ── Teste de conexão (preview server-side) ───────────

    async def test_connection(self, integration: IntegrationModel) -> Dict[str, Any]:
        """Busca a página de pedidos e extrai cabeçalhos de tabelas (preview).

        Extração completa roda no agente Node; aqui apenas validamos
        conectividade + presença de candidatos a tabela de pedidos.
        """
        import httpx
        from html.parser import HTMLParser

        class _TableHeaders(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_table = 0
                self.in_row = False
                self.in_cell = False
                self.cell_buf: List[str] = []
                self.row: List[str] = []
                self.tables: List[List[str]] = []
                self.title = ""

            def handle_starttag(self, tag, attrs):
                if tag == "table":
                    self.in_table += 1
                elif tag == "tr" and self.in_table:
                    self.in_row = True
                    self.row = []
                elif tag in ("th", "td") and self.in_row:
                    self.in_cell = True
                    self.cell_buf = []
                elif tag == "title" and not self.title:
                    self._in_title = True

            def handle_endtag(self, tag):
                if tag == "table" and self.in_table:
                    self.in_table -= 1
                elif tag == "tr" and self.in_row:
                    self.in_row = False
                    if self.row and self.in_table:
                        self.tables.append(self.row)
                elif tag in ("th", "td") and self.in_cell:
                    self.in_cell = False
                    self.row.append(" ".join("".join(self.cell_buf).split()))
                elif tag == "title":
                    self._in_title = False

            def handle_data(self, data):
                if getattr(self, "_in_title", False) and not self.title:
                    self.title += data
                if self.in_cell:
                    self.cell_buf.append(data)

        base = integration.base_url.rstrip("/")
        path = integration.orders_path or "/pedidos"
        url = f"{base}{path}"

        auth = None
        headers: Dict[str, str] = {}
        if integration.auth_type == "basic":
            user = (integration.auth_config or {}).get("username", "")
            pwd = (integration.auth_config or {}).get("password", "")
            auth = (user, pwd)
        elif integration.auth_type == "token":
            token = (integration.auth_config or {}).get("token", "")
            headers["Authorization"] = f"Bearer {token}"
        elif integration.auth_type == "cookie":
            cookie = (integration.auth_config or {}).get("cookie", "")
            headers["Cookie"] = cookie

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True, auth=auth) as client:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "url": url,
                "error": f"Falha ao acessar o site: {e}",
                "hint": "Verifique URL, credenciais e se a página de pedidos responde.",
            }

        parser = _TableHeaders()
        parser.feed(resp.text)

        # linhas que parecem cabeçalho (contêm palavras-chave de pedido)
        keywords = ("cliente", "produto", "valor", "total", "status", "pedido", "quantid", "endere", "data")
        candidates = [row for row in parser.tables if sum(1 for c in row if any(k in c.lower() for k in keywords)) >= 2]

        return {
            "ok": True,
            "url": url,
            "http_status": resp.status_code,
            "page_title": parser.title.strip()[:120],
            "tables_found": len(parser.tables),
            "order_table_candidates": candidates[:3],
            "detection": "candidate" if candidates else "none",
            "hint": (
                "Tabela de pedidos provável encontrada — configure o agente ou deixe a detecção automática."
                if candidates
                else "Nenhuma tabela com cabeçalhos de pedido encontrada neste caminho; tente outro orders_path."
            ),
        }
