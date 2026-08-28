"""
Communication API — Customer Notification System

POST /api/v1/communication/send     → Send notification
GET  /api/v1/communication/history  → Communication history
GET  /api/v1/communication/templates → List templates
PATCH /api/v1/communication/templates/{event} → Update template
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

from app.domain.communication.templates import (
    CommunicationService, CommunicationEvent, CommunicationChannel,
    get_communication_service, DEFAULT_TEMPLATES,
)
from app.presentation.dependencies import get_tenant_context, require_admin
from app.domain.security.models import TenantContext

router = APIRouter(prefix="/communication", tags=["communication"])


# ── Schemas ──────────────────────────────────────────────

class SendNotificationRequest(BaseModel):
    delivery_id: str
    event: str  # CommunicationEvent value
    context: Dict[str, str] = {}  # Template variables
    channel: str = "WHATSAPP"
    force: bool = False  # Skip cooldown check


class NotificationResponse(BaseModel):
    communication_id: str
    status: str
    message: str
    channel: str


class TemplateUpdateRequest(BaseModel):
    body: Optional[str] = None
    enabled: Optional[bool] = None
    cooldown_minutes: Optional[int] = None


# ── Endpoints ────────────────────────────────────────────

@router.post("/send", response_model=NotificationResponse)
async def send_notification(
    req: SendNotificationRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Send a customer notification based on delivery event."""
    service = get_communication_service()

    try:
        event = CommunicationEvent(req.event)
    except ValueError:
        raise HTTPException(400, f"Invalid event: {req.event}")

    try:
        channel = CommunicationChannel(req.channel)
    except ValueError:
        raise HTTPException(400, f"Invalid channel: {req.channel}")

    # Check cooldown (unless forced)
    if not req.force and not service.should_send(ctx.tenant_id, req.delivery_id, event):
        raise HTTPException(
            429,
            detail="Cooldown active. Use force=true to override.",
        )

    # Render message
    message = service.render_message(ctx.tenant_id, event, req.context)

    # Record communication
    record = service.record_communication(
        tenant_id=ctx.tenant_id,
        delivery_id=req.delivery_id,
        event=event,
        channel=channel,
        message=message,
        status="QUEUED",
    )

    return NotificationResponse(
        communication_id=record["communication_id"],
        status="QUEUED",
        message=message,
        channel=channel.value,
    )


@router.get("/history")
async def get_communication_history(
    delivery_id: Optional[str] = None,
    limit: int = 50,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get communication history for tenant."""
    service = get_communication_service()
    return service.get_history(ctx.tenant_id, delivery_id, limit)


@router.get("/templates")
async def list_templates(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List all available communication templates."""
    return {
        "templates": {
            e.value: t.to_dict() for e, t in DEFAULT_TEMPLATES.items()
        }
    }


@router.patch("/templates/{event}")
async def update_template(
    event: str,
    req: TemplateUpdateRequest,
    ctx: TenantContext = Depends(require_admin),
):
    """Update a communication template (admin only)."""
    service = get_communication_service()

    try:
        event_type = CommunicationEvent(event)
    except ValueError:
        raise HTTPException(400, f"Invalid event: {event}")

    policy = service.get_policy(ctx.tenant_id)

    # Get existing template (custom or default)
    if event_type in policy.custom_templates:
        template = policy.custom_templates[event_type]
    else:
        from app.domain.communication.templates import MessageTemplate
        default = DEFAULT_TEMPLATES.get(event_type, MessageTemplate(event=event_type))
        template = MessageTemplate(
            event=default.event,
            channel=default.channel,
            subject=default.subject,
            body=default.body,
            variables=default.variables,
            enabled=default.enabled,
            cooldown_minutes=default.cooldown_minutes,
        )

    # Apply updates
    if req.body is not None:
        template.body = req.body
    if req.enabled is not None:
        template.enabled = req.enabled
    if req.cooldown_minutes is not None:
        template.cooldown_minutes = req.cooldown_minutes

    policy.custom_templates[event_type] = template

    return {"success": True, "template": template.to_dict()}
