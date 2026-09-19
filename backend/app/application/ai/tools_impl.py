"""
Tool Implementations — FASE 9

Read and Write tools that wrap existing use cases.
Tools NEVER access repositories directly — always through use cases.
"""

from typing import Dict, Any, Optional

from app.domain.ai.tools import ToolResult
from app.core.whatsapp_limits import get_whatsapp_limit_store


class AIToolsFactory:
    """Creates tool handlers that delegate to existing use cases."""

    def __init__(self, db_session=None):
        self.db = db_session

    def _get_session(self):
        if self.db:
            return self.db
        from app.infrastructure.database.connection import SessionLocal

        return SessionLocal()

    def _close_session(self, session):
        if not self.db:
            session.close()

    # ── READ TOOLS ──────────────────────────────────────

    def get_customer(self, args: Dict[str, Any]) -> ToolResult:
        """Look up a customer by code, name, or phone."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository

            repo = SQLAlchemyClientRepository(session)
            codigo = args.get("customer_codigo")
            nome = args.get("customer_name")
            telefone = args.get("phone")

            if codigo:
                client = repo.buscar_por_codigo(codigo)
            elif telefone:
                client = repo.buscar_por_telefone(telefone)
            elif nome:
                clients, _ = repo.buscar(query=nome)
                client = clients[0] if clients else None
            else:
                return ToolResult(success=False, error="Provide customer_codigo, customer_name, or phone")

            if not client:
                return ToolResult(success=False, error="Cliente não encontrado")

            return ToolResult(
                success=True,
                data={
                    "codigo": client.codigo,
                    "nome": client.nome,
                    "telefone": client.telefone,
                    "email": client.email,
                    "tipo": client.tipo,
                    "ativo": client.ativo,
                    "rua": client.rua,
                    "numero": client.numero,
                    "bairro": client.bairro,
                },
            )
        finally:
            self._close_session(session)

    def search_customers(self, args: Dict[str, Any]) -> ToolResult:
        """Search customers with filters."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository

            repo = SQLAlchemyClientRepository(session)
            busca = args.get("query", "")
            clients, total = repo.buscar(query=busca)
            return ToolResult(
                success=True,
                data={
                    "total": total,
                    "items": [{"codigo": c.codigo, "nome": c.nome, "telefone": c.telefone} for c in clients[:10]],
                },
            )
        finally:
            self._close_session(session)

    def get_customer_360(self, args: Dict[str, Any]) -> ToolResult:
        """Get Customer 360 with metrics."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
            from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
            from app.infrastructure.repositories.financial_repositories import SQLAlchemyReceivableRepository
            from app.application.client.use_cases import Customer360UseCase

            codigo = args.get("customer_codigo")
            if not codigo:
                return ToolResult(success=False, error="Provide customer_codigo")

            uc = Customer360UseCase(
                SQLAlchemyClientRepository(session),
                SQLAlchemyOrderRepository(session),
                receivable_repository=SQLAlchemyReceivableRepository(session),
            )
            result = uc.execute(codigo)
            if not result:
                return ToolResult(success=False, error="Cliente não encontrado")
            return ToolResult(success=True, data=result)
        finally:
            self._close_session(session)

    def get_order(self, args: Dict[str, Any]) -> ToolResult:
        """Look up an order by code."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
            from app.infrastructure.repositories.order_item_repository import SQLAlchemyOrderItemRepository

            codigo = args.get("order_codigo")
            if not codigo:
                return ToolResult(success=False, error="Provide order_codigo")

            repo = SQLAlchemyOrderRepository(session)
            item_repo = SQLAlchemyOrderItemRepository(session)
            order = repo.buscar_por_codigo(codigo)
            if not order:
                return ToolResult(success=False, error="Pedido não encontrado")

            items = item_repo.listar_por_pedido(codigo)
            return ToolResult(
                success=True,
                data={
                    "codigo": order.codigo,
                    "client_codigo": order.client_codigo,
                    "status": order.status.value if hasattr(order.status, "value") else str(order.status),
                    "total": float(order.total),
                    "payment_status": order.payment_status.value
                    if hasattr(order.payment_status, "value")
                    else str(order.payment_status),
                    "items": [
                        {"product": i.product_nome, "qty": i.quantity, "price": float(i.unit_price)} for i in items
                    ],
                },
            )
        finally:
            self._close_session(session)

    def get_inventory(self, args: Dict[str, Any]) -> ToolResult:
        """Get inventory for a product."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository

            repo = SQLAlchemyInventoryRepository(session)
            codigo = args.get("product_codigo")
            if not codigo:
                return ToolResult(success=False, error="Provide product_codigo")

            inv = repo.get_by_product(codigo)
            if not inv:
                return ToolResult(success=False, error="Produto não encontrado no inventário")

            return ToolResult(
                success=True,
                data={
                    "product_codigo": inv.product_codigo,
                    "quantity": inv.quantity,
                    "minimum_quantity": inv.minimum_quantity,
                    "stock_status": inv.stock_status.value
                    if hasattr(inv.stock_status, "value")
                    else str(inv.stock_status),
                },
            )
        finally:
            self._close_session(session)

    def get_low_stock(self, args: Dict[str, Any]) -> ToolResult:
        """Get products with low or zero stock."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository

            repo = SQLAlchemyInventoryRepository(session)
            items = repo.list_all()
            low = [i for i in items if i.stock_status.value in ("LOW_STOCK", "OUT_OF_STOCK")]
            return ToolResult(
                success=True,
                data={
                    "count": len(low),
                    "items": [
                        {
                            "product_codigo": i.product_codigo,
                            "quantity": i.quantity,
                            "minimum": i.minimum_quantity,
                            "status": i.stock_status.value,
                        }
                        for i in low
                    ],
                },
            )
        finally:
            self._close_session(session)

    def get_inventory_summary(self, args: Dict[str, Any]) -> ToolResult:
        """Get inventory summary."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository

            repo = SQLAlchemyInventoryRepository(session)
            items = repo.list_all()
            total = len(items)
            low = sum(1 for i in items if i.stock_status.value == "LOW_STOCK")
            out = sum(1 for i in items if i.stock_status.value == "OUT_OF_STOCK")
            return ToolResult(
                success=True,
                data={
                    "total_products": total,
                    "in_stock": total - low - out,
                    "low_stock": low,
                    "out_of_stock": out,
                },
            )
        finally:
            self._close_session(session)

    def get_payments(self, args: Dict[str, Any]) -> ToolResult:
        """Get payments."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.financial_repositories import SQLAlchemyPaymentRepository

            repo = SQLAlchemyPaymentRepository(session)
            order_codigo = args.get("order_codigo")
            if order_codigo:
                payments = repo.get_by_order(order_codigo)
            else:
                payments, _ = repo.list_all(page=1, page_size=10)
            return ToolResult(
                success=True,
                data={
                    "count": len(payments),
                    "items": [
                        {"id": p.id, "order": p.order_codigo, "amount": float(p.amount), "status": p.status.value}
                        for p in payments
                    ],
                },
            )
        finally:
            self._close_session(session)

    def get_receivables(self, args: Dict[str, Any]) -> ToolResult:
        """Get receivables."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.financial_repositories import SQLAlchemyReceivableRepository

            repo = SQLAlchemyReceivableRepository(session)
            customer = args.get("customer_codigo")
            if customer:
                items = repo.get_by_customer(customer)
            else:
                items, _ = repo.list_open(page=1, page_size=10)
            return ToolResult(
                success=True,
                data={
                    "count": len(items),
                    "items": [
                        {
                            "order": r.order_codigo,
                            "customer": r.customer_codigo,
                            "original": float(r.original_amount),
                            "paid": float(r.paid_amount),
                            "remaining": float(r.remaining_amount),
                            "status": r.status.value,
                        }
                        for r in items
                    ],
                },
            )
        finally:
            self._close_session(session)

    def get_financial_summary(self, args: Dict[str, Any]) -> ToolResult:
        """Get financial summary."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.financial_repositories import (
                SQLAlchemyPaymentRepository,
                SQLAlchemyCashMovementRepository,
            )

            pay_repo = SQLAlchemyPaymentRepository(session)
            cash_repo = SQLAlchemyCashMovementRepository(session)
            balance = cash_repo.current_balance()
            payments, total = pay_repo.list_all(page=1, page_size=1000)
            total_received = sum(float(p.amount) for p in payments if p.status.value == "PAID")
            return ToolResult(
                success=True,
                data={
                    "cash_balance": float(balance),
                    "total_received": total_received,
                    "total_payments": total,
                },
            )
        finally:
            self._close_session(session)

    def get_sales_summary(self, args: Dict[str, Any]) -> ToolResult:
        """Get sales summary."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository

            repo = SQLAlchemyOrderRepository(session)
            orders = repo.listar_todos()
            total = len(orders)
            total_value = sum(float(o.total or 0) for o in orders)
            return ToolResult(
                success=True,
                data={
                    "total_orders": total,
                    "total_sales_value": total_value,
                },
            )
        finally:
            self._close_session(session)

    def search_products(self, args: Dict[str, Any]) -> ToolResult:
        """Search products."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository

            repo = SQLAlchemyProductRepository(session)
            products = repo.listar_todos()
            busca = args.get("query", "").lower()
            if busca:
                products = [p for p in products if busca in p.nome.lower() or busca in p.codigo.lower()]
            return ToolResult(
                success=True,
                data={
                    "count": len(products),
                    "items": [
                        {"codigo": p.codigo, "nome": p.nome, "preco": float(p.preco), "tipo": p.tipo}
                        for p in products[:10]
                    ],
                },
            )
        finally:
            self._close_session(session)

    # ── WRITE TOOLS ─────────────────────────────────────

    def create_order(self, args: Dict[str, Any]) -> ToolResult:
        """Create an order (requires confirmation)."""
        session = self._get_session()
        try:
            from app.application.order.use_cases import CreateOrderUseCase
            from app.infrastructure.repositories.order_repository import SQLAlchemyOrderRepository
            from app.infrastructure.repositories.order_item_repository import SQLAlchemyOrderItemRepository
            from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
            from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
            from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository

            order_repo = SQLAlchemyOrderRepository(session)
            item_repo = SQLAlchemyOrderItemRepository(session)
            uc = CreateOrderUseCase(
                order_repo=order_repo,
                order_item_repo=item_repo,
                client_repo=SQLAlchemyClientRepository(session),
                product_repo=SQLAlchemyProductRepository(session),
                inventory_repo=SQLAlchemyInventoryRepository(session),
            )
            order = uc.execute(args)
            return ToolResult(
                success=True,
                data={"order_codigo": order.codigo, "total": float(order.total)},
                display_message=f"Pedido {order.codigo} criado com total R$ {order.total:.2f}",
            )
        except Exception as e:
            session.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            self._close_session(session)

    def add_stock(self, args: Dict[str, Any]) -> ToolResult:
        """Add stock entry (requires confirmation)."""
        session = self._get_session()
        try:
            from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository

            repo = SQLAlchemyInventoryRepository(session)
            result = repo.add_stock_atomic(
                product_codigo=args["product_codigo"],
                quantity=args["quantity"],
                reason=args.get("reason", "AI entry"),
            )
            return ToolResult(
                success=True,
                data={"new_balance": float(result["inventory"].quantity)},
                display_message=f"Entrada de {args['quantity']} unidades. Saldo: {result['inventory'].quantity}",
            )
        except Exception as e:
            session.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            self._close_session(session)

    def register_payment(self, args: Dict[str, Any]) -> ToolResult:
        """Register a payment (requires confirmation)."""
        session = self._get_session()
        try:
            from app.application.financial.use_cases import RegisterPaymentUseCase
            from app.infrastructure.repositories.financial_repositories import (
                SQLAlchemyPaymentRepository,
                SQLAlchemyReceivableRepository,
                SQLAlchemyCashMovementRepository,
                SQLAlchemyFinancialLedgerRepository,
            )

            uc = RegisterPaymentUseCase(
                SQLAlchemyPaymentRepository(session),
                SQLAlchemyReceivableRepository(session),
                SQLAlchemyCashMovementRepository(session),
                SQLAlchemyFinancialLedgerRepository(session),
            )
            result = uc.execute(args)
            return ToolResult(
                success=True,
                data={"payment_id": result["payment"].id, "status": result["status"]},
                display_message=f"Pagamento de R$ {args['amount']} registrado.",
            )
        except Exception as e:
            session.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            self._close_session(session)

    def update_client_address(self, args: Dict[str, Any]) -> ToolResult:
        """Atualiza o endereço do cliente (requer confirmação).

        Usado quando o cliente informa correção de endereço na conversa
        (ex.: resposta à reativação). Chave: phone (número do remetente)
        ou customer_codigo.
        """
        session = self._get_session()
        try:
            from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository

            repo = SQLAlchemyClientRepository(session)
            client = None
            if args.get("phone"):
                client = repo.buscar_por_telefone(args["phone"])
            elif args.get("customer_codigo"):
                client = repo.buscar_por_codigo(args["customer_codigo"])
            if not client:
                return ToolResult(success=False, error="Cliente não encontrado")

            rua = (args.get("rua") or "").strip()
            numero = (args.get("numero") or "").strip()
            bairro = (args.get("bairro") or "").strip()
            if not rua or not numero or not bairro:
                return ToolResult(success=False, error="rua, numero e bairro são obrigatórios")

            client.atualizar_endereco(
                rua=rua,
                numero=numero,
                bairro=bairro,
                complemento=(args.get("complemento") or None),
                referencia=(args.get("referencia") or None),
            )
            repo.atualizar(client)
            return ToolResult(
                success=True,
                data={"codigo": client.codigo, "endereco": client.endereco_completo},
                display_message=f"Endereço atualizado: {client.endereco_completo}",
            )
        except Exception as e:
            session.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            self._close_session(session)

    # ── REFERRAL TOOLS (F4) ─────────────────────────────

    # Rate limit do auto-cadastro — F4.5: store TTL compartilhado
    # (Redis quando RATE_LIMIT_MODE=redis — persiste entre reinícios e
    # compartilha entre workers; fallback in-memory fail-open por worker).
    # R1 (verificado): o IP não é extraído do webhook do WhatsApp — a conexão
    # vem do serviço WhatsApp Node, não do cliente final — então o limite
    # efetivo é por telefone. O parâmetro `ip` permanece para o futuro
    # endpoint web público (§5), onde o limite por IP voltará a valer.
    _SIGNUP_RATE_WINDOW = 3600  # 1 hora

    def _check_signup_rate(self, phone: str, ip: str = "") -> Optional[str]:
        """Retorna erro se rate limit excedido, senão None.

        Limites: 3 tentativas/telefone/hora; 5 tentativas/IP/hora quando
        o IP estiver disponível (hoje não é, no contexto WhatsApp).
        """
        store = get_whatsapp_limit_store()
        allowed, _ = store.allow(f"signup:phone:{phone}", 3, self._SIGNUP_RATE_WINDOW)
        if not allowed:
            return "RATE_LIMITED_PHONE"
        if ip:
            allowed, _ = store.allow(f"signup:ip:{ip}", 5, self._SIGNUP_RATE_WINDOW)
            if not allowed:
                return "RATE_LIMITED_IP"
        return None

    def register_referral(self, args: Dict[str, Any]) -> ToolResult:
        """Registra novo cliente via token de convite de indicação.

        IA do WhatsApp pode chamar por design (auto-cadastro público via token).
        Não expor em outras IAs.
        """
        session = self._get_session()
        try:
            from app.application.coupon.referral_service import ReferralService, ReferralError

            token = (args.get("invite_token") or "").strip()
            name = (args.get("name") or "").strip()
            phone = (args.get("phone") or "").strip()
            address = {
                "rua": (args.get("rua") or "").strip(),
                "numero": (args.get("numero") or "").strip(),
                "bairro": (args.get("bairro") or "").strip(),
            }

            if not token or not name or not phone:
                return ToolResult(
                    success=False,
                    error="invite_token, name e phone são obrigatórios",
                )

            # Rate limit (3/telefone/hora, 5/IP/hora)
            rate_error = self._check_signup_rate(phone, args.get("ip", ""))
            if rate_error:
                return ToolResult(
                    success=False,
                    error="Muitas tentativas de cadastro. Tente novamente mais tarde.",
                )

            tenant_id = args.get("tenant_id", "default")
            svc = ReferralService(session, tenant_id)
            result = svc.complete_signup(token, name, phone, address)

            referred = result.get("referred_client")
            referrer = result.get("referrer_client")
            coupons = result.get("coupons", {})
            idempotent = result.get("idempotent_replay", False)

            rc = coupons.get("referred") or {}
            rfc = coupons.get("referrer") or {}

            if idempotent:
                display = "Cadastro já realizado anteriormente com este token."
            elif rc:
                display = (
                    f"Cadastro realizado! Você ganhou um cupom de "
                    f"R$ {rc.get('value', 0):.2f} (código: {rc.get('code', '?')}). "
                    f"Seu indicador também ganhou um cupom!"
                )
            else:
                display = "Cadastro realizado com sucesso!"

            return ToolResult(
                success=True,
                data={
                    "referred_codigo": referred.codigo if referred else None,
                    "referrer_codigo": referrer.codigo if referrer else None,
                    "referred_coupon": rc.get("code") if rc else None,
                    "referrer_coupon": rfc.get("code") if rfc else None,
                    "idempotent": idempotent,
                },
                display_message=display,
            )
        except ReferralError as e:
            return ToolResult(success=False, error=e.message)
        except Exception as e:
            session.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            self._close_session(session)

    def list_client_coupons(self, args: Dict[str, Any]) -> ToolResult:
        """Lista cupons ativos do cliente (não usados, não expirados)."""
        session = self._get_session()
        try:
            from app.application.coupon.referral_service import ReferralService

            client_codigo = (args.get("customer_codigo") or "").strip()
            if not client_codigo:
                return ToolResult(success=False, error="customer_codigo obrigatório")

            tenant_id = args.get("tenant_id", "default")
            svc = ReferralService(session, tenant_id)
            result = svc.client_coupons(client_codigo)
            active = result.get("active", [])

            return ToolResult(
                success=True,
                data={
                    "count": len(active),
                    "coupons": active,
                },
                display_message=(
                    f"Você tem {len(active)} cupom(s) disponível(is)." if active else "Nenhum cupom disponível."
                ),
            )
        except Exception as e:
            session.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            self._close_session(session)
