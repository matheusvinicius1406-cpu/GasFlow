"""
Alerts Webhook — receiver para notificações do Alertmanager.

Endpoint: POST /api/v1/webhooks/alerts
Recebe o payload padrão do Alertmanager (v4) e registra cada alerta em log
estruturado (observável por Loki/CloudWatch). Ponto único de integração para
notificações futuras (Telegram/Slack/e-mail) sem tocar no Prometheus.

Segurança (matriz de rotas 2026-10-09): o endpoint não tinha como validar a
origem — exposto, qualquer um podia inundar o log. Agora:

* ``ALERTS_WEBHOOK_SECRET`` definido → exige o segredo em ``X-Alert-Secret``
  ou ``Authorization: Bearer <segredo>`` (comparado com ``hmac.compare_digest``);
  ausente/errado responde **401**.
* sem segredo → em **produção** responde **503** (fail-closed); fora de
  produção (dev/rede interna do compose) segue aceitando, como antes.

O Alertmanager assina via ``http_config.authorization`` (Bearer) — ver
``monitoring/alertmanager.yml``.
"""

import hmac
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger("gasflow.alerts")

router = APIRouter(prefix="/webhooks", tags=["alerts"])


def _supplied_secret(request: Request) -> str | None:
    """Segredo vindo do header dedicado ou de um Bearer token."""
    header = request.headers.get("X-Alert-Secret")
    if header:
        return header
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _verify_origin(request: Request) -> tuple[bool, int | None]:
    """Autoriza a origem do webhook.

    Devolve ``(ok, status_quando_negado)``. ``status`` é ``503`` para
    "não configurado em produção" e ``401`` para segredo ausente/errado.
    """
    secret = settings.alerts_webhook_secret
    if not secret:
        if settings.environment == "production":
            logger.warning("[alerts.webhook] rejected: ALERTS_WEBHOOK_SECRET not set")
            return False, 503
        return True, None

    supplied = _supplied_secret(request)
    if supplied and hmac.compare_digest(secret, supplied):
        return True, None
    logger.warning("[alerts.webhook] rejected: invalid or missing secret")
    return False, 401


@router.post("/alerts")
async def receive_alert(request: Request) -> dict:
    """Recebe webhooks do Alertmanager e loga cada alerta ativo/resolvido."""
    allowed, denied_status = _verify_origin(request)
    if not allowed:
        detail = "webhook_not_configured" if denied_status == 503 else "unauthorized"
        return JSONResponse({"ok": False, "error": detail}, status_code=denied_status or 401)

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    alerts = payload.get("alerts", [])
    status = payload.get("status", "unknown")
    for alert in alerts:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        logger.warning(
            "alertmanager.notification",
            extra={
                "alert_status": alert.get("status", status),
                "alertname": labels.get("alertname", "unknown"),
                "severity": labels.get("severity", "unknown"),
                "summary": annotations.get("summary", ""),
                "description": annotations.get("description", ""),
            },
        )
    logger.info(
        "alertmanager.batch",
        extra={"group_status": status, "alerts_count": len(alerts)},
    )
    return {"ok": True, "received": len(alerts)}
