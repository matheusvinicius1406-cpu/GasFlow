"""
Assignment Service — Transactional delivery assignment.

Ensures atomic operation:
1. Validate delivery can be assigned
2. Validate driver is available
3. Validate vehicle capacity
4. Reserve vehicle load
5. Assign delivery to driver
6. Update driver status
7. Publish domain event
8. Enfileira zap do entregador (F3, idempotente — falha não desfaz)
9. Commit transaction

If any step fails: ROLLBACK entire operation.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository
from app.infrastructure.repositories.whatsapp_automation_repository import (
    SQLAlchemyAutomationRepository,
)
from app.infrastructure.repositories.vehicle_repository import VehicleRepository
from app.domain.events.event_bus import publish_delivery_event, publish_driver_event, EventType


logger = logging.getLogger("gasflow.assignment")


class AssignmentService:
    """
    Transactional delivery assignment service.

    All operations happen within a single database session/transaction.
    If any step fails, the entire operation is rolled back.
    """

    def __init__(self, db: Session):
        self.db = db
        self.driver_repo = SQLAlchemyDeliveryDriverRepository(db, tenant_id="default")
        self.vehicle_repo = VehicleRepository(db, tenant_id="default")

    def assign(
        self,
        tenant_id: str,
        delivery_id: str,
        driver_codigo: str,
        vehicle_id: Optional[int] = None,
        order_items: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        Assign a delivery to a driver with vehicle capacity validation.

        Args:
            tenant_id: Tenant context
            delivery_id: Delivery to assign
            driver_codigo: Driver codigo (from database)
            vehicle_id: Optional vehicle to use
            order_items: Optional {product_codigo: quantity} for capacity check

        Returns:
            Dict with success, delivery, driver info

        Raises:
            ValueError if any validation fails (transaction rolls back)
        """
        try:
            # 1. Find driver
            driver = self.driver_repo.find_by_id_as_model(driver_codigo)
            if not driver:
                raise ValueError("DRIVER_NOT_FOUND")
            if driver.tenant_id != tenant_id:
                raise ValueError("TENANT_MISMATCH")
            if not driver.ativo:
                raise ValueError("DRIVER_INACTIVE")
            if driver.status not in ("AVAILABLE",):
                raise ValueError(f"DRIVER_NOT_AVAILABLE: status={driver.status}")

            # 2. Validate vehicle capacity if items provided
            if vehicle_id and order_items:
                for product_codigo, quantity in order_items.items():
                    if not self.vehicle_repo.can_carry(vehicle_id, product_codigo, quantity):
                        raise ValueError(f"INSUFFICIENT_CAPACITY: {product_codigo} needs {quantity}")

            # 3. Reserve vehicle load if vehicle and items provided
            if vehicle_id and order_items:
                for product_codigo, quantity in order_items.items():
                    ok = self.vehicle_repo.reserve_load(vehicle_id, product_codigo, quantity)
                    if not ok:
                        raise ValueError(f"RESERVE_FAILED: {product_codigo} {quantity}")

            # 4. Update driver status to BUSY
            driver.status = "BUSY"
            if vehicle_id:
                driver.vehicle_id = str(vehicle_id)

            # 5. Commit transaction
            self.db.commit()

            # 6. Publish events (after commit succeeds)
            publish_delivery_event(
                EventType.DELIVERY_ASSIGNED,
                delivery_id,
                tenant_id,
                driver_id=driver_codigo,
                data={"vehicle_id": vehicle_id, "order_items": order_items or {}},
            )
            publish_driver_event(
                EventType.DRIVER_UNAVAILABLE, driver_codigo, tenant_id, data={"reason": "delivery_assigned"}
            )

            # 7. Zap do entregador (F3): enfileira notificação no executor de
            # automações existente (idempotente por delivery+driver). Falha
            # aqui NUNCA desfaz a atribuição — só registra o erro.
            try:
                self._notify_driver(delivery_id, tenant_id, driver, driver_codigo)
            except Exception:  # pragma: no cover — defesa extra; _notify_driver já engole
                logger.exception("driver_notification_error", extra={"delivery_id": delivery_id})

            return {
                "success": True,
                "driver_codigo": driver_codigo,
                "vehicle_id": vehicle_id,
                "status": "ASSIGNED",
            }

        except ValueError:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise

    def _notify_driver(self, delivery_id: str, tenant_id: str, driver, driver_codigo: str) -> None:
        """
        Enfileira o zap do entregador na atribuição (F3).

        Falhas de infraestrutura (settings/DB/executor) NUNCA derrubam a
        atribuição — logam e seguem. Sem telefone cadastrado, pula cedo.
        """
        from app.infrastructure.database.init_db import engine
        from sqlalchemy.orm import Session as _Session
        from app.application.delivery.driver_notification import DriverAssignmentNotifier
        from app.application.settings.settings_service import SettingsService

        phone = (driver.telefone or "").strip() if driver.telefone else ""
        if not phone:
            logger.warning(
                "driver_notification_skipped_no_phone",
                extra={"delivery_id": delivery_id, "driver": driver_codigo},
            )
            return

        session = _Session(bind=engine)
        try:
            template = None
            try:
                template = SettingsService(session).get_value("driver.assignment_notification_template", None)
            except Exception:
                template = None  # sem settings, usa o template default
            notifier = DriverAssignmentNotifier(SQLAlchemyAutomationRepository(session, tenant_id))
            notifier.notify_assignment(
                delivery_id=delivery_id,
                driver_codigo=driver_codigo,
                payload={
                    "driver_name": driver.nome or "",
                    "customer_phone": phone,
                },
                template=template if isinstance(template, str) and "{{" in template else None,
            )
        except Exception:
            logger.exception("driver_notification_error", extra={"delivery_id": delivery_id, "driver": driver_codigo})
        finally:
            session.close()

    def release(
        self,
        tenant_id: str,
        delivery_id: str,
        driver_codigo: str,
        vehicle_id: Optional[int] = None,
        order_items: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        Release a delivery assignment (cancellation/reassignment).
        Rolls back vehicle load reservation.
        """
        try:
            # Release vehicle load
            if vehicle_id and order_items:
                for product_codigo, quantity in order_items.items():
                    self.vehicle_repo.release_reserved(vehicle_id, product_codigo, quantity)

            # Update driver status back to AVAILABLE
            driver = self.driver_repo.find_by_id_as_model(driver_codigo)
            if driver:
                driver.status = "AVAILABLE"
                driver.vehicle_id = None

            self.db.commit()

            # Publish events
            publish_delivery_event(
                EventType.DELIVERY_CANCELLED,
                delivery_id,
                tenant_id,
                driver_id=driver_codigo,
                data={"vehicle_id": vehicle_id},
            )
            publish_driver_event(
                EventType.DRIVER_AVAILABLE, driver_codigo, tenant_id, data={"reason": "delivery_released"}
            )

            return {"success": True, "status": "RELEASED"}

        except Exception:
            self.db.rollback()
            raise
