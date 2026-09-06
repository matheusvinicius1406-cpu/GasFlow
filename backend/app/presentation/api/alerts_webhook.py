"""
Alerts Webhook — receiver para notificações do Alertmanager.

Endpoint: POST /api/v1/webhooks/alerts
Recebe o payload padrão do Alertmanager (v4) e registra cada alerta em log
estruturado (observável por Loki/CloudWatch). Ponto único de integração para
notificações futuras (Telegram/Slack/e-mail) sem tocar no Prometheus.

Sem autenticação por token (rede interna do compose); em exposição pública,
proteger via firewall/reverse proxy.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("gasflow.alerts")

router = APIRouter(prefix="/webhooks", tags=["alerts"])


@router.post("/alerts")
async def receive_alert(request: Request) -> dict:
    """Recebe webhooks do Alertmanager e loga cada alerta ativo/resolvido."""
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
