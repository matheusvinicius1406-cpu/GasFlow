"""
DriverStockService — F7: controle de estoque carregado pelo entregador.

Regras do spec (§3.3.1):
- Carga (LOADING): entregador declara N cheios, operador confirma. Soma
  full_tanks_loaded; NÃO debita a base (empréstimo temporário — conta
  dupla com deliver_stock_atomic é bug).
- Entrega (DELIVERY): full_tanks_loaded decrementa quando a entrega vira
  DELIVERED. O débito da base é responsabilidade exclusiva do
  deliver_stock_atomic (chamado por _apply_delivery_stock_effect).
- Avaria (DAMAGE): motivo obrigatório; debita o carregado do entregador E
  o estoque da base (o cilindro avariado sai dos dois lugares), com audit.
- Vazios (RETURN): cliente devolve na entrega; o entregador acumula
  empty_tanks_returned e devolve na base no fim do turno.
- Reconciliação (RECONCILE): carga − entregas − avarias = cheios restantes
  + vazios devolvidos. Divergência > tolerância (driver.stock.tolerance,
  default 2) → alerta + bloqueio de novas cargas até reconciliação manual.

A entrega decrementa o entregador via `apply_delivery_debit`, chamado
pelo mesmo _apply_delivery_stock_effect que debita a base — mesma
transação/commit, consistência garantida por teste.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import setup_logging
from app.infrastructure.repositories.driver_stock_model import DriverStockModel, DriverStockEventModel

logger = setup_logging("INFO")


class DriverStockError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class DriverStockService:
    """Estoques do entregador: carga, avaria, entrega, devolução, reconciliação."""

    def __init__(self, db: Session, tenant_id: str = "default"):
        self.db = db
        self.tenant_id = tenant_id

    # ── Helpers ───────────────────────────────────────────

    def _get_or_create(self, driver_id: str, product_codigo: str) -> DriverStockModel:
        row = (
            self.db.query(DriverStockModel)
            .filter(
                DriverStockModel.tenant_id == self.tenant_id,
                DriverStockModel.driver_id == driver_id,
                DriverStockModel.product_codigo == product_codigo,
            )
            .first()
        )
        if not row:
            row = DriverStockModel(
                tenant_id=self.tenant_id,
                driver_id=driver_id,
                product_codigo=product_codigo,
                full_tanks_loaded=0,
                empty_tanks_returned=0,
            )
            self.db.add(row)
            self.db.flush()
        return row

    def _record_event(
        self,
        driver_id: str,
        product_codigo: str,
        event_type: str,
        quantity: int,
        row: DriverStockModel,
        reason: Optional[str] = None,
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None,
        details: Optional[Dict] = None,
    ) -> None:
        self.db.add(
            DriverStockEventModel(
                tenant_id=self.tenant_id,
                driver_id=driver_id,
                product_codigo=product_codigo,
                event_type=event_type,
                quantity=quantity,
                reason=reason,
                reference_type=reference_type,
                reference_id=reference_id,
                details=details,
                balance_after_loaded=row.full_tanks_loaded,
                balance_after_empty=row.empty_tanks_returned,
            )
        )
        self.db.flush()

    def _get_tolerance(self) -> int:
        try:
            from app.application.settings.settings_service import SettingsService

            value = SettingsService(Session(bind=self.db.get_bind())).get_value("driver.stock.tolerance", 2)
            return max(int(value), 0)
        except Exception:
            return 2

    # ── Carga (empréstimo) ────────────────────────────────

    def load_tanks(self, driver_id: str, product_codigo: str, quantity: int, actor_id: str = "") -> Dict[str, Any]:
        """Operador registra N cheios carregados pelo entregador (C1: manual).

        Bloqueada quando o entregador está com divergência pendente
        (blocked=True). NÃO debita a base.
        """
        if quantity <= 0:
            raise DriverStockError("Quantidade deve ser positiva")
        row = self._get_or_create(driver_id, product_codigo)
        if row.blocked:
            raise DriverStockError(
                f"Entregador bloqueado para novas cargas: {row.blocked_reason or 'reconciliação pendente'}"
            )
        row.full_tanks_loaded += quantity
        row.updated_at = datetime.utcnow()
        self._record_event(driver_id, product_codigo, "LOADING", quantity, row)
        self.db.commit()
        return {"driver_id": driver_id, "product_codigo": product_codigo, "full_tanks_loaded": row.full_tanks_loaded}

    # ── Entrega (débito do entregador) ────────────────────

    def apply_delivery_debit(self, driver_id: str, quantities: Dict[str, int], delivery_id: str) -> None:
        """Decrementa full_tanks_loaded por produto na entrega DELIVERED.

        Idempotente: se já existe evento DELIVERY para (driver, delivery,
        produto), não reaplica. Best-effort por produto — falha de um
        produto não bloqueia os demais nem a entrega (o fato físico é o
        débito da base, já garantido pelo deliver_stock_atomic).
        """
        for product_codigo, qty in quantities.items():
            if qty <= 0:
                continue
            row = self._get_or_create(driver_id, product_codigo)
            # Idempotência por evento
            existing = (
                self.db.query(DriverStockEventModel)
                .filter(
                    DriverStockEventModel.tenant_id == self.tenant_id,
                    DriverStockEventModel.driver_id == driver_id,
                    DriverStockEventModel.product_codigo == product_codigo,
                    DriverStockEventModel.event_type == "DELIVERY",
                    DriverStockEventModel.reference_id == delivery_id,
                )
                .first()
            )
            if existing:
                continue
            # Clamp em 0: divergência fica visível na reconciliação, não
            # inventa estoque negativo.
            row.full_tanks_loaded = max(0, row.full_tanks_loaded - qty)
            row.empty_tanks_returned += qty  # cliente devolve os vazios na entrega
            row.updated_at = datetime.utcnow()
            self._record_event(
                driver_id,
                product_codigo,
                "DELIVERY",
                qty,
                row,
                reference_type="DELIVERY",
                reference_id=delivery_id,
            )
        self.db.commit()

    def reverse_delivery_debit(self, driver_id: str, quantities: Dict[str, int], delivery_id: str) -> None:
        """Reverte o débito do entregador quando a entrega é cancelada
        após DELIVERED (espelho do reverse_delivery_stock_atomic da base).
        Idempotente por evento RETURN com reference_id da entrega.
        """
        for product_codigo, qty in quantities.items():
            if qty <= 0:
                continue
            existing = (
                self.db.query(DriverStockEventModel)
                .filter(
                    DriverStockEventModel.tenant_id == self.tenant_id,
                    DriverStockEventModel.driver_id == driver_id,
                    DriverStockEventModel.product_codigo == product_codigo,
                    DriverStockEventModel.event_type == "RETURN",
                    DriverStockEventModel.reference_id == delivery_id,
                )
                .first()
            )
            if existing:
                continue
            row = self._get_or_create(driver_id, product_codigo)
            row.full_tanks_loaded += qty
            row.empty_tanks_returned = max(0, row.empty_tanks_returned - qty)
            row.updated_at = datetime.utcnow()
            self._record_event(
                driver_id,
                product_codigo,
                "RETURN",
                qty,
                row,
                reference_type="DELIVERY",
                reference_id=delivery_id,
            )
        self.db.commit()

    # ── Avaria ────────────────────────────────────────────

    def register_damage(
        self, driver_id: str, product_codigo: str, quantity: int, reason: str, actor_id: str = ""
    ) -> Dict[str, Any]:
        """Avaria: motivo OBRIGATÓRIO; debita o carregado do entregador e
        o estoque da base (o cilindro quebrou na rota — sai dos dois).
        """
        if quantity <= 0:
            raise DriverStockError("Quantidade deve ser positiva")
        if not reason or not reason.strip():
            raise DriverStockError("Motivo da avaria é obrigatório")

        row = self._get_or_create(driver_id, product_codigo)
        if row.full_tanks_loaded < quantity:
            raise DriverStockError(f"Carregado insuficiente: {row.full_tanks_loaded}, avaria de {quantity}")
        row.full_tanks_loaded -= quantity
        row.updated_at = datetime.utcnow()
        self._record_event(driver_id, product_codigo, "DAMAGE", quantity, row, reason=reason.strip())
        self.db.commit()

        # Débito na base (best-effort após commit do entregador; motivo
        # diferenciado para trilha de auditoria da base).
        base_error = None
        try:
            from app.infrastructure.repositories.inventory_repository import SQLAlchemyInventoryRepository

            repo = SQLAlchemyInventoryRepository(self.db, self.tenant_id)
            repo.deliver_stock_atomic(
                product_codigo=product_codigo,
                quantity=quantity,
                reason=f"Avaria na rota — entregador {driver_id}: {reason.strip()}",
                reference_type="DRIVER_DAMAGE",
                reference_id=f"{driver_id}:{self._last_event_id(driver_id, product_codigo)}",
            )
        except Exception as exc:
            base_error = str(exc)
            logger.error(
                "avaria: falha ao debitar a base (driver=%s product=%s): %s",
                driver_id,
                product_codigo,
                exc,
            )

        return {
            "driver_id": driver_id,
            "product_codigo": product_codigo,
            "full_tanks_loaded": row.full_tanks_loaded,
            "base_debited": base_error is None,
            "base_error": base_error,
        }

    def _last_event_id(self, driver_id: str, product_codigo: str) -> Optional[int]:
        ev = (
            self.db.query(DriverStockEventModel)
            .filter(
                DriverStockEventModel.tenant_id == self.tenant_id,
                DriverStockEventModel.driver_id == driver_id,
                DriverStockEventModel.product_codigo == product_codigo,
            )
            .order_by(DriverStockEventModel.id.desc())
            .first()
        )
        return ev.id if ev else None

    # ── Saldos / elegibilidade ────────────────────────────

    def get_stock(self, driver_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.db.query(DriverStockModel)
            .filter(DriverStockModel.tenant_id == self.tenant_id, DriverStockModel.driver_id == driver_id)
            .all()
        )
        return [
            {
                "product_codigo": r.product_codigo,
                "full_tanks_loaded": r.full_tanks_loaded,
                "empty_tanks_returned": r.empty_tanks_returned,
                "blocked": r.blocked,
                "blocked_reason": r.blocked_reason,
            }
            for r in rows
        ]

    def eligible_capacity(self, driver_id: str) -> Dict[str, int]:
        """Mapa product_codigo → cheios disponíveis (para o despacho)."""
        rows = (
            self.db.query(DriverStockModel)
            .filter(
                DriverStockModel.tenant_id == self.tenant_id,
                DriverStockModel.driver_id == driver_id,
                DriverStockModel.blocked == False,  # noqa: E712 — bloqueado não é elegível
            )
            .all()
        )
        return {r.product_codigo: r.full_tanks_loaded for r in rows if r.full_tanks_loaded > 0}

    # ── Reconciliação ─────────────────────────────────────

    def reconcile(
        self, driver_id: str, counts: Dict[str, int], empty_returned: Dict[str, int], actor_id: str = ""
    ) -> Dict[str, Any]:
        """Fim de turno: para cada produto, compara o ESPERADO com o INFORMADO.

        Esperado (do sistema): cheios restantes = carga − entregas − avarias;
        vazios devolvidos = entregas. Operador informa a contagem física
        (`counts`) e os vazios devolvidos à base (`empty_returned`).
        Divergência > tolerância → bloqueia novas cargas até nova
        reconciliação que zere a divergência.
        """
        tolerance = self._get_tolerance()
        rows = (
            self.db.query(DriverStockModel)
            .filter(DriverStockModel.tenant_id == self.tenant_id, DriverStockModel.driver_id == driver_id)
            .all()
        )
        results = []
        any_blocked = False

        for row in rows:
            pc = row.product_codigo
            informed = int(counts.get(pc, 0))
            expected = row.full_tanks_loaded  # carga − entregas − avarias já aplicadas
            divergence = informed - expected

            empty_expected = row.empty_tanks_returned
            empty_informed = int(empty_returned.get(pc, 0))
            empty_divergence = empty_informed - empty_expected

            blocked = abs(divergence) > tolerance or abs(empty_divergence) > tolerance
            if blocked:
                any_blocked = True
                row.blocked = True
                row.blocked_reason = (
                    f"Reconciliação {datetime.utcnow().isoformat(timespec='minutes')}: "
                    f"cheios {informed}/{expected} (tol {tolerance}), vazios {empty_informed}/{empty_expected}"
                )

            self._record_event(
                driver_id,
                pc,
                "RECONCILE",
                informed,
                row,
                reason=row.blocked_reason if blocked else None,
                details={
                    "expected_full": expected,
                    "informed_full": informed,
                    "divergence_full": divergence,
                    "expected_empty": empty_expected,
                    "informed_empty": empty_informed,
                    "divergence_empty": empty_divergence,
                    "tolerance": tolerance,
                    "blocked": blocked,
                    "actor_id": actor_id,
                },
            )

            # Informado vira o novo saldo (reconciliação manual confirma a
            # contagem física) e os vazios retornam à contagem do entregador.
            if not blocked:
                row.full_tanks_loaded = informed
                row.empty_tanks_returned = max(0, empty_expected - empty_informed)
                row.blocked = False
                row.blocked_reason = None

            results.append(
                {
                    "product_codigo": pc,
                    "expected_full": expected,
                    "informed_full": informed,
                    "divergence_full": divergence,
                    "expected_empty": empty_expected,
                    "informed_empty": empty_informed,
                    "divergence_empty": empty_divergence,
                    "blocked": blocked,
                }
            )

        self.db.commit()
        return {"driver_id": driver_id, "tolerance": tolerance, "results": results, "any_blocked": any_blocked}

    def unblock(self, driver_id: str, product_codigo: Optional[str] = None, actor_id: str = "") -> Dict[str, Any]:
        """Desbloqueia após reconciliação manual fora do fluxo (operador decide)."""
        q = self.db.query(DriverStockModel).filter(
            DriverStockModel.tenant_id == self.tenant_id,
            DriverStockModel.driver_id == driver_id,
            DriverStockModel.blocked == True,  # noqa: E712
        )
        if product_codigo:
            q = q.filter(DriverStockModel.product_codigo == product_codigo)
        rows = q.all()
        for row in rows:
            row.blocked = False
            row.blocked_reason = None
        self.db.commit()
        return {"unblocked": len(rows)}
