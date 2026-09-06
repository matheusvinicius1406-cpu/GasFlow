"""
WhatsApp Cloud API Webhook — Meta oficial.

Endpoints:
- GET  /whatsapp/cloud-api/webhook  — verificação de subscribe (hub.challenge)
- POST /whatsapp/cloud-api/webhook  — eventos de status e mensagens recebidas

Segurança: assinatura X-Hub-Signature-256 validada com WHATSAPP_CLOUD_API_APP_SECRET.
Env:
- WHATSAPP_CLOUD_API_APP_SECRET (obrigatório para aceitar POSTs — fail-closed)
- WHATSAPP_CLOUD_API_VERIFY_TOKEN (para o handshake GET)
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
    for m in messages:
        logger.info(
            "whatsapp.cloud_api.incoming",
            extra={"message_id": m.get("message_id"), "from": m.get("from")},
        )

    # Meta exige 200 rápido; processamento pesado deve ir para fila.
    return {"ok": True, "statuses": len(statuses), "messages": len(messages)}


def JSON_503():
    from fastapi.responses import JSONResponse

    return JSONResponse({"ok": False, "error": "webhook_not_configured"}, status_code=503)
