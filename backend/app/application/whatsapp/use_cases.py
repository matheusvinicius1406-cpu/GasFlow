"""
WhatsApp Use Cases — Casos de uso do WhatsApp.

Inclui:
- Processar mensagens recebidas (bot de pedidos)
- Enviar mensagens manuais
- Gerenciar conversas
"""

import os
from datetime import datetime
from typing import Optional

from app.domain.whatsapp.entity import (
    WhatsAppConversation,
    WhatsAppMessage,
    ConversationStatus,
    MessageDirection,
)
from app.domain.whatsapp.repository import WhatsAppRepository
from app.domain.client.repository import ClientRepository
from app.domain.product.repository import ProductRepository
from app.domain.order.repository import OrderRepository

BOT_LOJA_NOME = os.getenv("BOT_LOJA_NOME", "GasFlow")
BOT_HORARIO = os.getenv("BOT_HORARIO_FUNCIONAMENTO", "08:00-18:00")


class HandleIncomingMessageUseCase:
    """
    Caso de uso: Processar mensagem recebida do WhatsApp.

    Executa o fluxo do bot de pedidos:
    1. idle → mostra menu
    2. awaiting_product → seleciona produto
    3. awaiting_quantity → define quantidade
    4. awaiting_address_confirm → confirma endereço
    5. awaiting_payment → seleciona pagamento → cria pedido
    """

    def __init__(
        self,
        whatsapp_repo: WhatsAppRepository,
        client_repo: ClientRepository,
        product_repo: ProductRepository,
        order_repo: OrderRepository,
    ):
        self.whatsapp_repo = whatsapp_repo
        self.client_repo = client_repo
        self.product_repo = product_repo
        self.order_repo = order_repo

    async def execute(self, phone_number: str, message_text: str) -> Optional[str]:
        """
        Processa a mensagem e retorna a resposta do bot (ou None).
        """
        # Busca ou cria conversa
        conv = self.whatsapp_repo.buscar_conversa_por_telefone(phone_number)
        if not conv:
            # Tenta vincular a cliente existente
            client_codigo = self.whatsapp_repo.buscar_cliente_por_telefone(phone_number)
            conv = WhatsAppConversation(
                phone_number=phone_number,
                client_codigo=client_codigo,
                status=ConversationStatus.IDLE,
            )
            conv = self.whatsapp_repo.criar_conversa(conv)

        # Salva mensagem recebida
        msg = WhatsAppMessage(
            conversation_id=conv.id,
            direction=MessageDirection.INBOUND,
            content=message_text,
        )
        self.whatsapp_repo.salvar_mensagem(msg)

        # Atualiza contexto
        conv.last_message = message_text
        conv.last_message_at = datetime.utcnow()

        text = message_text.strip().lower()

        # Processa conforme status
        response = None

        if conv.status == ConversationStatus.IDLE:
            response = await self._handle_idle(conv)
        elif conv.status == ConversationStatus.AWAITING_PRODUCT:
            response = await self._handle_product(conv, text)
        elif conv.status == ConversationStatus.AWAITING_QUANTITY:
            response = await self._handle_quantity(conv, text)
        elif conv.status == ConversationStatus.AWAITING_ADDRESS_CONFIRM:
            response = await self._handle_address(conv, text)
        elif conv.status == ConversationStatus.AWAITING_PAYMENT:
            response = await self._handle_payment(conv, text)
        else:
            conv.resetar()
            response = await self._handle_idle(conv)

        # Salva resposta
        if response:
            out_msg = WhatsAppMessage(
                conversation_id=conv.id,
                direction=MessageDirection.OUTBOUND,
                content=response,
            )
            self.whatsapp_repo.salvar_mensagem(out_msg)

        # Atualiza conversa
        self.whatsapp_repo.atualizar_conversa(conv)

        return response

    async def _handle_idle(self, conv: WhatsAppConversation) -> str:
        """Menu inicial."""
        products = self.product_repo.listar_todos()
        menu_lines = []
        for i, p in enumerate(products, 1):
            menu_lines.append(f"  {i} - {p.nome} (R$ {p.preco:.2f})")

        menu = "\n".join(menu_lines) if menu_lines else "  (Nenhum produto disponível)"

        conv.status = ConversationStatus.AWAITING_PRODUCT

        return (
            f"Olá! Bem-vindo(a) ao *{BOT_LOJA_NOME}*! 🏪\n\n"
            f"Horário: *{BOT_HORARIO}*\n\n"
            f"Escolha um produto:\n\n{menu}\n\n"
            f"Digite o *número* do produto."
        )

    async def _handle_product(self, conv: WhatsAppConversation, text: str) -> str:
        """Seleção de produto."""
        products = self.product_repo.listar_todos()

        try:
            choice = int(text)
            if 1 <= choice <= len(products):
                selected = products[choice - 1]
                conv.definir_produto(selected.codigo)

                return (
                    f"Você escolheu: *{selected.nome}* — R$ {selected.preco:.2f}\n\n"
                    f"Estoque: *{selected.estoque}* unidades\n\n"
                    f"Quantas unidades deseja?"
                )
        except ValueError:
            pass

        return "❌ Opção inválida. Digite o *número* do produto."

    async def _handle_quantity(self, conv: WhatsAppConversation, text: str) -> str:
        """Quantidade e confirmação de endereço."""
        try:
            qty = int(text)
            if qty <= 0:
                raise ValueError
        except ValueError:
            return "❌ Quantidade inválida. Digite um *número* maior que 0."

        product_codigo = conv.obter_produto_codigo()
        product = self.product_repo.buscar_por_codigo(product_codigo) if product_codigo else None

        if not product:
            conv.resetar()
            return "❌ Erro ao identificar o produto. Vamos recomeçar."

        if product.estoque < qty:
            return (
                f"❌ Estoque insuficiente.\n"
                f"Disponível: *{product.estoque}*\n"
                f"Solicitado: *{qty}*\n\n"
                f"Digite uma quantidade menor."
            )

        if not conv.client_codigo:
            conv.resetar()
            return (
                "⚠️ Você ainda não está cadastrado.\n"
                "Entre em contato com o depósito para cadastro."
            )

        conv.definir_quantidade(product.codigo, qty)
        total = product.preco * qty

        client = self.client_repo.buscar_por_codigo(conv.client_codigo)
        address = f"{client.rua}, {client.numero} - {client.bairro}" if client else "Endereço não encontrado"

        return (
            f"📦 *Resumo:*\n"
            f"Produto: {product.nome}\n"
            f"Quantidade: {qty}\n"
            f"Total: R$ {total:.2f}\n\n"
            f"📍 *{address}*\n\n"
            f"Confirmar endereço?\n"
            f"  *1* - Sim\n"
            f"  *2* - Não"
        )

    async def _handle_address(self, conv: WhatsAppConversation, text: str) -> str:
        """Confirmação de endereço."""
        if text in ("1", "sim", "s"):
            conv.confirmar_endereco()
            return (
                "✅ Endereço confirmado!\n\n"
                "💳 Forma de pagamento:\n"
                "  *1* - Dinheiro\n"
                "  *2* - PIX\n"
                "  *3* - Cartão de crédito\n"
                "  *4* - Cartão de débito\n"
                "  *5* - Fiado"
            )
        elif text in ("2", "não", "nao", "n"):
            conv.resetar()
            return "❌ Pedido cancelado. Digite *menu* para recomeçar."
        else:
            return "Digite *1* para confirmar ou *2* para cancelar."

    PAYMENT_MAP = {
        "1": "Dinheiro",
        "2": "PIX",
        "3": "Cartão de Crédito",
        "4": "Cartão de Débito",
        "5": "Fiado",
    }

    async def _handle_payment(self, conv: WhatsAppConversation, text: str) -> str:
        """Processa pagamento e cria pedido."""
        payment_method = self.PAYMENT_MAP.get(text)
        if not payment_method:
            return "❌ Opção inválida. Digite o *número* da forma de pagamento."

        product_codigo = conv.obter_produto_codigo()
        qty = conv.obter_quantidade()

        try:
            order_data = {
                "client_codigo": conv.client_codigo,
                "product": product_codigo,
                "quantity": qty,
                "payment_method": payment_method,
            }

            # Cria o pedido usando o repositório diretamente
            from app.application.order.use_cases import CreateOrderUseCase
            create_order = CreateOrderUseCase(
                order_repo=self.order_repo,
                client_repo=self.client_repo,
                product_repo=self.product_repo,
            )
            order = create_order.execute(order_data)

            product = self.product_repo.buscar_por_codigo(product_codigo)

            conv.pedido_realizado()

            return (
                f"✅ *Pedido realizado!*\n\n"
                f"📋 Código: *{order.codigo}*\n"
                f"📦 {product.nome if product else product_codigo} x{qty}\n"
                f"💰 R$ {order.value:.2f}\n"
                f"💳 {payment_method}\n\n"
                f"Obrigado! 🙏"
            )

        except Exception as e:
            conv.resetar()
            return f"❌ Erro: {str(e)}\n\nDigite *menu* para recomeçar."


class SendManualMessageUseCase:
    """Caso de uso: Enviar mensagem manual para um telefone."""

    def __init__(self, whatsapp_repo: WhatsAppRepository):
        self.whatsapp_repo = whatsapp_repo

    async def execute(self, phone_number: str, message: str) -> bool:
        """Envia uma mensagem manual."""
        # Salva na conversa
        conv = self.whatsapp_repo.buscar_conversa_por_telefone(phone_number)
        if conv:
            msg = WhatsAppMessage(
                conversation_id=conv.id,
                direction=MessageDirection.OUTBOUND,
                content=message,
            )
            self.whatsapp_repo.salvar_mensagem(msg)

        return True


class GetConversationUseCase:
    """Caso de uso: Buscar conversa de um telefone."""

    def __init__(self, whatsapp_repo: WhatsAppRepository):
        self.whatsapp_repo = whatsapp_repo

    def execute(self, phone_number: str) -> Optional[WhatsAppConversation]:
        return self.whatsapp_repo.buscar_conversa_por_telefone(phone_number)
