"""
Purchase Notes API — Notas de compra internas (Item 2, sem SEFAZ).

Endpoints (todos com require_permission — a permissão é validada no
backend, nunca só no frontend):
    POST /purchase-notes              — cria DRAFT        (purchase.create)
    GET  /purchase-notes              — lista com filtros (purchase.read)
    GET  /purchase-notes/{id}         — detalhe           (purchase.read)
    PATCH /purchase-notes/{id}        — edita DRAFT       (purchase.update)
    POST /purchase-notes/{id}/confirm — confirma + estoque(purchase.confirm)
    POST /purchase-notes/{id}/cancel  — cancela DRAFT     (purchase.cancel)
    GET  /purchase-notes/{id}/pdf     — HTML p/ PDF       (purchase.read)
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.application.purchase.purchase_service import PurchaseNoteError, PurchaseNoteService
from app.infrastructure.database.dependencies import get_db
from app.presentation.dependencies import require_permission
from app.domain.security.models import TenantContext

router = APIRouter(prefix="/purchase-notes", tags=["Purchase Notes"])


def _svc(
    db: Session = Depends(get_db), ctx: TenantContext = Depends(require_permission("purchase.read"))
) -> PurchaseNoteService:
    return PurchaseNoteService(db, ctx.tenant_id)


class PurchaseNoteItemIn(BaseModel):
    product_codigo: str = Field(min_length=1, max_length=50)
    product_name: Optional[str] = None
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0, description="Preço unitário em reais")


class PurchaseNoteCreate(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=200)
    supplier_cnpj: Optional[str] = Field(default=None, max_length=18)
    issue_date: Optional[date] = None
    observations: Optional[str] = None
    items: List[PurchaseNoteItemIn] = Field(min_length=1)


class PurchaseNoteUpdate(BaseModel):
    supplier_name: Optional[str] = Field(default=None, max_length=200)
    supplier_cnpj: Optional[str] = Field(default=None, max_length=18)
    issue_date: Optional[date] = None
    observations: Optional[str] = None
    items: Optional[List[PurchaseNoteItemIn]] = None


@router.post("")
def create_note(
    body: PurchaseNoteCreate,
    ctx: TenantContext = Depends(require_permission("purchase.create")),
    svc: PurchaseNoteService = Depends(_svc),
):
    try:
        return svc.create_note(body.model_dump(), created_by=ctx.user_id)
    except PurchaseNoteError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("")
def list_notes(
    status: Optional[str] = Query(default=None),
    supplier: Optional[str] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    limit: int = Query(default=200, le=500),
    svc: PurchaseNoteService = Depends(_svc),
):
    return {"notes": svc.list_notes(status, supplier, start_date, end_date, limit)}


@router.get("/{note_id}")
def get_note(note_id: str, svc: PurchaseNoteService = Depends(_svc)):
    note = svc.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Nota não encontrada")
    return note


@router.patch("/{note_id}")
def update_note(
    note_id: str,
    body: PurchaseNoteUpdate,
    ctx: TenantContext = Depends(require_permission("purchase.update")),
    svc: PurchaseNoteService = Depends(_svc),
):
    try:
        return svc.update_note(note_id, body.model_dump(exclude_none=True), actor_id=ctx.user_id)
    except PurchaseNoteError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post("/{note_id}/confirm")
def confirm_note(
    note_id: str,
    ctx: TenantContext = Depends(require_permission("purchase.confirm")),
    svc: PurchaseNoteService = Depends(_svc),
):
    try:
        return svc.confirm_note(note_id, actor_id=ctx.user_id)
    except PurchaseNoteError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post("/{note_id}/cancel")
def cancel_note(
    note_id: str,
    ctx: TenantContext = Depends(require_permission("purchase.cancel")),
    svc: PurchaseNoteService = Depends(_svc),
):
    try:
        return svc.cancel_note(note_id, actor_id=ctx.user_id)
    except PurchaseNoteError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("/{note_id}/pdf")
def note_pdf(
    note_id: str,
    svc: PurchaseNoteService = Depends(_svc),
    ctx: TenantContext = Depends(require_permission("purchase.read")),
):
    """HTML renderizável — o Electron imprime via printToPDF (purchase:export-pdf)."""
    try:
        html = svc.render_pdf_html(note_id)
    except PurchaseNoteError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e
    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=html, media_type="text/html")
