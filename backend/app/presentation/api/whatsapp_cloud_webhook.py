"""
WhatsApp Cloud API Webhook — Meta oficial.

Endpoints:
- GET  /whatsapp/cloud-api/webhook  — verificação de subscribe (hub.challenge)
- POST /whatsapp/cloud-api/webhook  — eventos de status e mensagens recebidas

Segurança: assinatura X-Hub-Signature-256 validada com WHATSAPP_CLOUD_API_APP_SECRET.
Env:
- WHATSAPP_CLOUD_API_APP_SECRET (obrigatório para aceitar POSTs — fail-closed)
- WHATSAPP_CLOUD_API_VERIFY_TOKEN (para o handshake GET)

Fluxo de mensagens (item A do relatório): mensagens recebidas seguem o MESMO
pipeline dos outros providers (POST /whatsapp/incoming → MessageGateway):
persistência de conversa, IA e resposta. A resposta (outbound) é enviada de
volta pela Cloud API (texto livre é permitido dentro da janela de 24h do
usuário — e aqui o usuário acabou de mandar mensagem).
"""

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.infrastructure.whatsapp_provider.cloud_api_adapter import CloudApiAdapter

logger = logging.getLogger("gasflow.whatsapp.cloud_api.webhook")

router = APIRouter(prefix="/whatsapp/cloud-api", tags=["whatsapp-cloud-api"])

APP_SECRET = os.getenv("WHATSAPP_CLOUD_API_APP_SECRET", "")
VERIFY_TOKEN = os.getenv("WHATSAPP_CLOUD_API_VERIFY_TOKEN", "")


@router.get("/webhook")
async def verify_subscription(request: Request) -> PlainTextResponse:
    """Handshake de inscrição do webhook no Meta App Dashboard.

    Meta exige exatamente o challenge como texto puro e status 200;
    falhas retornam 403.
    """
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and VERIFY_TOKEN and params.get("hub.verify_token") == VERIFY_TOKEN:
        logger.info("[cloud_api.webhook] subscription verified")
        return PlainTextResponse(params.get("hub.challenge", ""), status_code=200)
    return PlainTextResponse("Forbidden", status_code=403)


@router.post("/webhook")
async def receive_event(request: Request):
    """Recebe eventos de status (sent/delivered/read/failed) e mensagens.

    Fail-closed: sem APP_SECRET configurado responde 503; assinatura
    inválida ou ausente responde 403. Corpo inválido responde 400.

    Mensagens recebidas passam pelo MessageGateway (mesmo pipeline de
    POST /whatsapp/incoming) e a resposta da IA é enviada pela própria
    Cloud API. Meta exige 200 rápido: o processamento é o mesmo já usado
    no gateway HTTP interno; a fila assíncrona continua como evolução.
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not APP_SECRET:
        logger.warning("[cloud_api.webhook] rejected: WHATSAPP_CLOUD_API_APP_SECRET not set")
        return JSON_503()

    if not signature or not CloudApiAdapter.verify_webhook_signature(APP_SECRET, body, signature):
        logger.warning("[cloud_api.webhook] invalid signature")
        return PlainTextResponse("invalid signature", status_code=403)

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return PlainTextResponse("invalid json", status_code=400)

    statuses = CloudApiAdapter.parse_status_event(payload)
    messages = CloudApiAdapter.parse_incoming_message(payload)

    # Observabilidade: persistência por evento fica a cargo do domínio
    # (mesma tabela de mensagens do gateway atual). Log estruturado por ora.
    for s in statuses:
        logger.info(
            "whatsapp.cloud_api.status",
            extra={
                "message_id": s.get("message_id"),
                "status": s.get("status"),
                "recipient": s.get("recipient"),
            },
        )

    answered = 0
    failed = 0
    for m in messages:
        logger.info(
            "whatsapp.cloud_api.incoming",
            extra={"message_id": m.get("message_id"), "from": m.get("from")},
        )
        try:
            if await _process_and_reply(m):
                answered += 1
            else:
                failed += 1
        except Exception:  # noqa: BLE001 — um erro numa mensagem não derruba o webhook
            logger.exception("whatsapp.cloud_api.process_failed")
            failed += 1

    return {"ok": True, "statuses": len(statuses), "messages": len(messages), "answered": answered, "failed": failed}


async def _process_and_reply(message: dict) -> bool:
    """Processa uma mensagem recebida pelo pipeline da IA e envia a resposta.

    Usa exatamente o mesmo MessageGateway de POST /whatsapp/incoming
    (validação → normalização → dedup → rate limit → cliente → IA) e envia
    o outbound pela Cloud API. Retorna True quando houve resposta enviada
    (ou o evento foi intencionalmente ignorado sem erro de envio).
    """
    from app.infrastructure.database.connection import SessionLocal
    from app.infrastructure.whatsapp_provider.factory import create_provider
    from app.infrastructure.whatsapp.repositories import (
        SQLAlchemyConversationRepository,
        SQLAlchemyConversationMessageRepository,
    )
    from app.infrastructure.repositories.client_repository import SQLAlchemyClientRepository
    from app.infrastructure.repositories.product_repository import SQLAlchemyProductRepository
    from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository
    from app.infrastructure.ai.factory import get_llm_provider
    from app.application.ai.engine import AIEngine
    from app.application.whatsapp.gateway import MessageGateway
    from app.presentation.api.whatsapp_gateway import _build_tool_registry

    db = SessionLocal()
    try:
        conv_repo = SQLAlchemyConversationRepository(db)
        msg_repo = SQLAlchemyConversationMessageRepository(db)
        registry = _build_tool_registry(db)
        ai_engine = AIEngine(llm_provider=get_llm_provider(), tool_registry=registry)

        gateway = MessageGateway(
            conversation_repo=conv_repo,
            message_repo=msg_repo,
            ai_engine=ai_engine,
            customer_repository=SQLAlchemyClientRepository(db),
            product_repository=SQLAlchemyProductRepository(db),
            inventory_repository=SQLAlchemyInventoryRepository(db),
        )

        result = gateway.process_incoming(
            {
                "account_id": "primary",
                "sender_phone": message.get("from", ""),
                "provider_message_id": message.get("message_id", ""),
                "text": message.get("text", ""),
                "message_type": "TEXT",
                "from_me": False,
            }
        )

        outbound = result.get("outbound")
        if not outbound or not result.get("outbound_text"):
            # skipped (dup/rate limit/from_me) ou handoff humano — nada a enviar.
            logger.info(
                "whatsapp.cloud_api.no_outbound",
                extra={"status": result.get("status"), "error": result.get("error")},
            )
            return True

        provider = create_provider("primary", "cloud_api")
        from app.domain.whatsapp_provider.models import SendOptions

        send_result = await provider.send_text(
            SendOptions(recipient=outbound.recipient_phone, text=result["outbound_text"])
        )
        if not send_result.success:
            logger.warning(
                "whatsapp.cloud_api.reply_send_failed",
                extra={"error": send_result.error, "error_code": send_result.error_code},
            )
            return False
        return True
    finally:
        db.close()


def JSON_503():
    from fastapi.responses import JSONResponse

    return JSONResponse({"ok": False, "error": "webhook_not_configured"}, status_code=503)
