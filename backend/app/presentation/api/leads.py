"""
Leads API — Captura pública do site institucional.

Endpoints públicos (rate-limited pelo middleware global):
    POST /leads            — newsletter {email, source?}
    POST /demo-request     — demonstração {email, name?, phone?, message?}

Armazenados na tabela site_leads. Sem auth por design (marketing público);
validação de e-mail + limites de tamanho + honeypot contra bots simples.
"""

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.infrastructure.database.init_db import engine
from app.infrastructure.repositories.lead_model import LeadModel

router = APIRouter(tags=["Leads"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _db() -> DBSession:
    return DBSession(bind=engine)


class LeadCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    source: str = Field(default="site_institucional", max_length=64)
    website: str = Field(default="", max_length=64)  # honeypot — deve vazio


class DemoRequestCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    name: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=40)
    message: str = Field(default="", max_length=2000)
    website: str = Field(default="", max_length=64)  # honeypot


def _validate_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="E-mail inválido.")
    return email


def _reject_honeypot(website: str) -> None:
    if website:
        # Bot preencheu o campo invisível — resposta neutra, não armazena.
        raise HTTPException(status_code=400, detail="Requisição inválida.")


@router.post("/leads", status_code=201)
def create_lead(body: LeadCreate):
    _reject_honeypot(body.website)
    email = _validate_email(body.email)
    db = _db()
    try:
        lead = LeadModel(
            id=str(uuid.uuid4()),
            type="LEAD",
            email=email,
            source=body.source[:64],
            created_at=datetime.utcnow(),
        )
        db.add(lead)
        db.commit()
        return {"success": True, "message": "Inscrição registrada."}
    finally:
        db.close()


@router.post("/demo-request", status_code=201)
def create_demo_request(body: DemoRequestCreate):
    _reject_honeypot(body.website)
    email = _validate_email(body.email)
    db = _db()
    try:
        lead = LeadModel(
            id=str(uuid.uuid4()),
            type="DEMO",
            email=email,
            name=body.name[:120] or None,
            phone=body.phone[:40] or None,
            message=body.message[:2000] or None,
            source="site_institucional",
            created_at=datetime.utcnow(),
        )
        db.add(lead)
        db.commit()
        return {"success": True, "message": "Solicitação registrada. Entraremos em contato."}
    finally:
        db.close()


# ── Admin: listagem simples ──────────────────────────

from fastapi import Depends  # noqa: E402

from app.presentation.dependencies import require_admin  # noqa: E402
from app.domain.security.models import TenantContext  # noqa: E402


@router.get("/leads")
def list_leads(limit: int = 100, ctx: TenantContext = Depends(require_admin)):
    db = _db()
    try:
        rows = db.query(LeadModel).order_by(LeadModel.created_at.desc()).limit(min(limit, 500)).all()
        return {
            "leads": [
                {
                    "id": r.id,
                    "type": r.type,
                    "email": r.email,
                    "name": r.name,
                    "phone": r.phone,
                    "message": r.message,
                    "source": r.source,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        }
    finally:
        db.close()
