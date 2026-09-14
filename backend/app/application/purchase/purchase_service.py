"""PurchaseNoteService — Notas de compra internas (Item 2, sem SEFAZ).

Regras centrais:
- note_number sequencial POR TENANT (SELECT COALESCE(MAX) + 1 dentro da
  transação; UNIQUE (tenant_id, note_number) protege de corrida).
- Confirmação: status DRAFT → CONFIRMED em UMA transação — valida itens,
  credita estoque via add_stock_atomic (ENTRY idempotente por nota) e
  grava audit. Se um item falhar, nada é aplicado (rollback total).
- Edições/cancelamento só em DRAFT; CONFIRMED é imutável (devolução
  pós-confirmação será nota de devolução — futuro).
- Toda mutação grava auth_audit_log (antes/depois em JSON).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.infrastructure.repositories.purchase_note_model import PurchaseNoteItemModel, PurchaseNoteModel

logger = logging.getLogger(__name__)

REFERENCE_TYPE = "purchase_note"


class PurchaseNoteError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _audit(
    db: Session,
    action: str,
    resource_id: str,
    actor_id: Optional[str],
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Audit trail (best-effort — nunca derruba a operação de negócio).

    Segue a convenção P0 3.3: snapshot da mutação em before_json/after_json
    (sem segredos); details carrega contexto extra (ex.: itens).
    """
    try:
        from app.infrastructure.repositories.auth_model import AuthAuditModel

        db.add(
            AuthAuditModel(
                id=str(uuid.uuid4()),
                actor_id=actor_id or "",
                actor_type="USER",
                tenant_id="default",
                action=action,
                resource="purchase_note",
                resource_id=resource_id,
                result="SUCCESS",
                timestamp=datetime.utcnow(),
                ip_address="",
                user_agent="",
                platform="desktop",
                before_json=before,
                after_json=after,
                details=details,
            )
        )
        db.flush()
    except Exception:  # pragma: no cover
        db.rollback()
        logger.warning("purchase_note.audit_failed", extra={"resource_id": resource_id})


class PurchaseNoteService:
    def __init__(self, db: Session, tenant_id: str = "default"):
        self.db = db
        self.tenant_id = tenant_id

    # ── Helpers ──────────────────────────────────────────────

    def _query(self):
        return self.db.query(PurchaseNoteModel).filter(PurchaseNoteModel.tenant_id == self.tenant_id)

    def _to_dict(self, model: PurchaseNoteModel, with_items: bool = True) -> dict:
        data = {
            "id": model.id,
            "note_number": model.note_number,
            "supplier_name": model.supplier_name,
            "supplier_cnpj": model.supplier_cnpj,
            "issue_date": model.issue_date.isoformat() if model.issue_date else None,
            "total_cents": int(model.total_cents or 0),
            "total": round(int(model.total_cents or 0) / 100, 2),
            "observations": model.observations,
            "status": model.status,
            "created_by": model.created_by,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "confirmed_at": model.confirmed_at.isoformat() if model.confirmed_at else None,
            "cancelled_at": model.cancelled_at.isoformat() if model.cancelled_at else None,
        }
        if with_items:
            items = (
                self.db.query(PurchaseNoteItemModel).filter(PurchaseNoteItemModel.purchase_note_id == model.id).all()
            )
            data["items"] = [
                {
                    "id": i.id,
                    "product_codigo": i.product_codigo,
                    "product_name": i.product_name,
                    "quantity": i.quantity,
                    "unit_price_cents": int(i.unit_price_cents or 0),
                    "unit_price": round(int(i.unit_price_cents or 0) / 100, 2),
                    "subtotal_cents": int(i.subtotal_cents or 0),
                    "subtotal": round(int(i.subtotal_cents or 0) / 100, 2),
                }
                for i in items
            ]
        return data

    def _get_model(self, note_id: str) -> Optional[PurchaseNoteModel]:
        return self._query().filter(PurchaseNoteModel.id == note_id).first()

    # ── Comandos ─────────────────────────────────────────────

    def create_note(self, data: dict, created_by: Optional[str] = None) -> dict:
        """Cria nota DRAFT com itens. Estoque NÃO muda aqui."""
        items_data = data.get("items") or []
        if not items_data:
            raise PurchaseNoteError("Nota deve ter pelo menos um item")

        note_id = str(uuid.uuid4())
        model = PurchaseNoteModel(
            id=note_id,
            tenant_id=self.tenant_id,
            note_number=0,  # placeholder — sequência gerada abaixo
            supplier_name=(data.get("supplier_name") or "").strip(),
            supplier_cnpj=data.get("supplier_cnpj"),
            issue_date=data.get("issue_date") or date.today(),
            total_cents=0,
            observations=data.get("observations"),
            status="DRAFT",
            created_by=created_by,
            created_at=datetime.utcnow(),
        )
        if not model.supplier_name:
            raise PurchaseNoteError("supplier_name é obrigatório")

        total = 0
        self.db.add(model)
        self.db.flush()  # parent primeiro — FK de purchase_note_items exige

        for item in items_data:
            quantity = int(item.get("quantity", 0))
            unit_price_cents = int(round(float(item.get("unit_price", 0)) * 100))
            if quantity <= 0:
                raise PurchaseNoteError("Quantidade deve ser maior que 0")
            product_codigo = (item.get("product_codigo") or "").strip()
            if not product_codigo:
                raise PurchaseNoteError("product_codigo é obrigatório em todos os itens")
            subtotal = quantity * unit_price_cents
            total += subtotal
            self.db.add(
                PurchaseNoteItemModel(
                    purchase_note_id=note_id,
                    product_codigo=product_codigo,
                    product_name=item.get("product_name") or product_codigo,
                    quantity=quantity,
                    unit_price_cents=unit_price_cents,
                    subtotal_cents=subtotal,
                )
            )
        model.total_cents = total  # type: ignore[assignment]

        # Sequência por tenant dentro da transação; UNIQUE cobre corrida.
        max_number = (
            self._query()
            .with_entities(PurchaseNoteModel.note_number)
            .order_by(PurchaseNoteModel.note_number.desc())
            .first()
        )
        model.note_number = (int(max_number[0]) if max_number and max_number[0] else 0) + 1  # type: ignore[assignment]

        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise PurchaseNoteError("Falha ao criar nota (concorrência de numeração?)", 409) from exc
        self.db.refresh(model)

        _audit(
            self.db,
            "purchase_note.created",
            note_id,
            created_by,
            after={"status": "DRAFT", "note_number": model.note_number, "total_cents": total},
        )
        self.db.commit()
        return self._to_dict(model)

    def update_note(self, note_id: str, data: dict, actor_id: Optional[str] = None) -> dict:
        """Edita nota DRAFT (fornecedor, data, observações e itens)."""
        model = self._get_model(note_id)
        if not model:
            raise PurchaseNoteError("Nota não encontrada", 404)
        if model.status != "DRAFT":
            raise PurchaseNoteError(f"Só notas DRAFT podem ser editadas (status atual: {model.status})", 400)

        before = {"supplier_name": model.supplier_name, "total_cents": int(model.total_cents or 0)}

        if "supplier_name" in data and (data["supplier_name"] or "").strip():
            model.supplier_name = data["supplier_name"].strip()
        if "supplier_cnpj" in data:
            model.supplier_cnpj = data["supplier_cnpj"]
        if "issue_date" in data and data["issue_date"]:
            model.issue_date = data["issue_date"]
        if "observations" in data:
            model.observations = data["observations"]

        if "items" in data and data["items"] is not None:
            items_data = data["items"]
            if not items_data:
                raise PurchaseNoteError("Nota deve ter pelo menos um item")
            self.db.query(PurchaseNoteItemModel).filter(PurchaseNoteItemModel.purchase_note_id == note_id).delete()
            total = 0
            for item in items_data:
                quantity = int(item.get("quantity", 0))
                unit_price_cents = int(round(float(item.get("unit_price", 0)) * 100))
                if quantity <= 0:
                    raise PurchaseNoteError("Quantidade deve ser maior que 0")
                product_codigo = (item.get("product_codigo") or "").strip()
                if not product_codigo:
                    raise PurchaseNoteError("product_codigo é obrigatório em todos os itens")
                subtotal = quantity * unit_price_cents
                total += subtotal
                self.db.add(
                    PurchaseNoteItemModel(
                        purchase_note_id=note_id,
                        product_codigo=product_codigo,
                        product_name=item.get("product_name") or product_codigo,
                        quantity=quantity,
                        unit_price_cents=unit_price_cents,
                        subtotal_cents=subtotal,
                    )
                )
            model.total_cents = total  # type: ignore[assignment]

        self.db.commit()
        self.db.refresh(model)
        _audit(
            self.db,
            "purchase_note.updated",
            note_id,
            actor_id,
            before=before,
            after={"supplier_name": model.supplier_name, "total_cents": int(model.total_cents or 0)},
        )
        self.db.commit()
        return self._to_dict(model)

    def confirm_note(self, note_id: str, actor_id: Optional[str] = None) -> dict:
        """Confirma a nota: DRAFT → CONFIRMED + ENTRADA de estoque atômica.

        Tudo em UMA transação: se qualquer item falhar (produto sem
        inventário etc.), rollback total — nada é aplicado.
        Idempotência de estoque garantida pela constraint de movimentos
        (reference_type='purchase_note', reference_id=note_id, ENTRY).
        """
        from app.infrastructure.repositories.inventory_model import InventoryModel
        from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository

        model = self._get_model(note_id)
        if not model:
            raise PurchaseNoteError("Nota não encontrada", 404)
        if model.status != "DRAFT":
            raise PurchaseNoteError(f"Só notas DRAFT podem ser confirmadas (status atual: {model.status})", 400)

        items = self.db.query(PurchaseNoteItemModel).filter(PurchaseNoteItemModel.purchase_note_id == note_id).all()
        if not items:
            raise PurchaseNoteError("Nota sem itens — não pode ser confirmada", 400)

        before_status = model.status
        model.status = "CONFIRMED"  # type: ignore[assignment]
        model.confirmed_at = datetime.utcnow()  # type: ignore[assignment]
        self.db.flush()  # valida FK/estado antes de tocar estoque

        repo = SQLAlchemyInventoryRepository(self.db, self.tenant_id)
        try:
            for item in items:
                # Inventário precisa existir — cria zerado se não existir.
                inv = (
                    self.db.query(InventoryModel)
                    .filter(
                        InventoryModel.tenant_id == self.tenant_id,
                        InventoryModel.product_codigo == item.product_codigo,
                    )
                    .first()
                )
                if not inv:
                    raise PurchaseNoteError(f"Inventário não encontrado para produto {item.product_codigo}", 422)
                repo.add_stock_atomic(
                    product_codigo=str(item.product_codigo),
                    quantity=int(item.quantity),
                    reason=f"Compra — nota interna #{model.note_number} ({model.supplier_name})",
                    reference_type=REFERENCE_TYPE,
                    reference_id=note_id,
                )
        except PurchaseNoteError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            raise PurchaseNoteError(f"Falha na entrada de estoque: {exc}", 422) from exc

        self.db.commit()
        self.db.refresh(model)

        _audit(
            self.db,
            "purchase_note.confirmed",
            note_id,
            actor_id,
            before={"status": before_status},
            after={"status": "CONFIRMED", "total_cents": int(model.total_cents or 0)},
            details={"items": [{"product_codigo": i.product_codigo, "quantity": i.quantity} for i in items]},
        )
        self.db.commit()
        return self._to_dict(model)

    def cancel_note(self, note_id: str, actor_id: Optional[str] = None) -> dict:
        """Cancela nota DRAFT (no-op de estoque). CONFIRMED → 400."""
        model = self._get_model(note_id)
        if not model:
            raise PurchaseNoteError("Nota não encontrada", 404)
        if model.status != "DRAFT":
            raise PurchaseNoteError(
                f"Só notas DRAFT podem ser canceladas (status atual: {model.status}); "
                "devolução pós-confirmação exigirá nota de devolução",
                400,
            )

        model.status = "CANCELLED"  # type: ignore[assignment]
        model.cancelled_at = datetime.utcnow()  # type: ignore[assignment]
        self.db.commit()
        self.db.refresh(model)

        _audit(
            self.db,
            "purchase_note.cancelled",
            note_id,
            actor_id,
            before={"status": "DRAFT"},
            after={"status": "CANCELLED"},
        )
        self.db.commit()
        return self._to_dict(model)

    # ── Consultas ────────────────────────────────────────────

    def get_note(self, note_id: str) -> Optional[dict]:
        model = self._get_model(note_id)
        return self._to_dict(model) if model else None

    def list_notes(
        self,
        status: Optional[str] = None,
        supplier: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 200,
    ) -> List[dict]:
        q = self._query()
        if status:
            q = q.filter(PurchaseNoteModel.status == status.upper())
        if supplier:
            q = q.filter(PurchaseNoteModel.supplier_name.ilike(f"%{supplier}%"))
        if start_date:
            q = q.filter(PurchaseNoteModel.issue_date >= start_date)
        if end_date:
            q = q.filter(PurchaseNoteModel.issue_date <= end_date)
        models = q.order_by(PurchaseNoteModel.note_number.desc()).limit(min(limit, 500)).all()
        return [self._to_dict(m, with_items=False) for m in models]

    def render_pdf_html(self, note_id: str, depot_name: str = "GasFlow", depot_cnpj: str = "") -> str:
        """HTML da nota para o PDF (impresso via Electron printToPDF)."""
        data = self.get_note(note_id)
        if not data:
            raise PurchaseNoteError("Nota não encontrada", 404)

        rows = "".join(
            f"<tr><td>{i['product_codigo']}</td><td>{i['product_name']}</td>"
            f"<td class='num'>{i['quantity']}</td>"
            f"<td class='num'>R$ {i['unit_price']:.2f}</td>"
            f"<td class='num'>R$ {i['subtotal']:.2f}</td></tr>"
            for i in data["items"]
        )
        cnpj_line = f"<p><strong>CNPJ:</strong> {data['supplier_cnpj']}</p>" if data.get("supplier_cnpj") else ""
        obs = f"<p><strong>Observações:</strong> {data['observations']}</p>" if data.get("observations") else ""
        return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Nota de compra #{data["note_number"]}</title>
<style>
 body {{ font-family: Arial, Helvetica, sans-serif; margin: 24px; color: #111; }}
 h1 {{ font-size: 20px; margin: 0 0 4px; }}
 .sub {{ color: #555; font-size: 12px; margin-bottom: 16px; }}
 table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
 th, td {{ border: 1px solid #ddd; padding: 6px 8px; font-size: 13px; text-align: left; }}
 th {{ background: #f4f4f4; }}
 .num {{ text-align: right; }}
 .total {{ font-size: 15px; font-weight: bold; text-align: right; margin-top: 8px; }}
</style></head><body>
<h1>{depot_name} — Nota de compra interna #{data["note_number"]}</h1>
<div class="sub">Documento interno — não é NF-e e não possui valor fiscal (SEFAZ)</div>
<h2 style="font-size:15px">Fornecedor</h2>
<p><strong>Nome:</strong> {data["supplier_name"]}</p>
{cnpj_line}
<p><strong>Data da compra:</strong> {data["issue_date"]}</p>
<table>
<thead><tr><th>Produto</th><th>Descrição</th><th class="num">Qtd</th><th class="num">Preço unit.</th><th class="num">Subtotal</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p class="total">Total: R$ {data["total"]:.2f}</p>
{obs}
</body></html>"""
