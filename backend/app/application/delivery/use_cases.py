"""
Delivery Use Cases — FASE 14

Application layer for delivery operations.
Uses domain entities + repositories. No direct DB access.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from app.domain.delivery.delivery import (
    Delivery,
    DeliveryStatus,
    DeliveryFailureReason,
    DeliveryProof,
    ProofType,
    AddressSnapshot,
)
from app.domain.delivery.route import Route
from app.domain.delivery.routing import RoutingProvider, MockRoutingProvider
from app.domain.delivery.repository import (
    DeliveryRepository,
    DriverRepository,
    VehicleRepository,
    RouteRepository,
)


class CreateDeliveryUseCase:
    """Create a delivery for an order."""

    def __init__(self, delivery_repo: DeliveryRepository, routing_provider: Optional[RoutingProvider] = None):
        self._repo = delivery_repo
        self._routing = routing_provider or MockRoutingProvider()

    def execute(
        self,
        tenant_id: str,
        order_id: str,
        customer_codigo: str,
        customer_name: str,
        address: Optional[Dict] = None,
        scheduled_at: Optional[datetime] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        # Check if delivery already exists for this order
        existing = self._repo.find_by_order_id(order_id, tenant_id)
        if existing:
            return {"success": False, "error": "Delivery already exists for this order"}

        addr = AddressSnapshot(**(address or {}))
        delivery = Delivery(
            order_id=order_id,
            tenant_id=tenant_id,
            customer_codigo=customer_codigo,
            customer_name=customer_name,
            address=addr,
            scheduled_at=scheduled_at,
            notes=notes,
        )
        delivery.timeline = [delivery.timeline[0]] if delivery.timeline else []
        saved = self._repo.save(delivery)
        return {"success": True, "delivery": saved.to_dict()}


class AssignDeliveryUseCase:
    """Assign a driver to a delivery."""

    def __init__(
        self,
        delivery_repo: DeliveryRepository,
        driver_repo: DriverRepository,
        vehicle_repo: Optional[VehicleRepository] = None,
    ):
        self._delivery_repo = delivery_repo
        self._driver_repo = driver_repo
        self._vehicle_repo = vehicle_repo

    def execute(
        self, tenant_id: str, delivery_id: str, driver_id: str, vehicle_id: Optional[str] = None
    ) -> Dict[str, Any]:
        delivery = self._delivery_repo.find_by_id(delivery_id, tenant_id)
        if not delivery:
            return {"success": False, "error": "Delivery not found"}
        if not delivery.can_transition(DeliveryStatus.ASSIGNED):
            return {"success": False, "error": f"Cannot assign in status {delivery.status.value}"}

        driver = self._driver_repo.find_by_id(driver_id, tenant_id)
        if not driver:
            return {"success": False, "error": "Driver not found"}
        if not driver.is_available:
            return {"success": False, "error": f"Driver is {driver.status.value}"}

        # Vehicle check
        if vehicle_id and self._vehicle_repo:
            vehicle = self._vehicle_repo.find_by_id(vehicle_id, tenant_id)
            if not vehicle or not vehicle.is_available:
                return {"success": False, "error": "Vehicle not available"}

        # Assign
        if not delivery.assign(driver_id, vehicle_id):
            return {"success": False, "error": "Assignment failed"}

        driver.set_busy()
        self._driver_repo.save(driver)
        self._delivery_repo.save(delivery)
        return {"success": True, "delivery": delivery.to_dict()}


class DispatchDeliveryUseCase:
    """Dispatch a delivery."""

    def __init__(self, delivery_repo: DeliveryRepository):
        self._repo = delivery_repo

    def execute(self, tenant_id: str, delivery_id: str) -> Dict[str, Any]:
        delivery = self._repo.find_by_id(delivery_id, tenant_id)
        if not delivery:
            return {"success": False, "error": "Delivery not found"}
        if not delivery.dispatch():
            return {"success": False, "error": f"Cannot dispatch in status {delivery.status.value}"}
        self._repo.save(delivery)
        return {"success": True, "delivery": delivery.to_dict()}


class UpdateDeliveryStatusUseCase:
    """Update delivery status (arrive, complete, fail)."""

    def __init__(self, delivery_repo: DeliveryRepository, driver_repo: Optional[DriverRepository] = None):
        self._delivery_repo = delivery_repo
        self._driver_repo = driver_repo

    def execute(
        self,
        tenant_id: str,
        delivery_id: str,
        new_status: str,
        failure_reason: Optional[str] = None,
        failure_notes: str = "",
        proof_type: Optional[str] = None,
        actor_type: str = "DRIVER",
    ) -> Dict[str, Any]:
        delivery = self._delivery_repo.find_by_id(delivery_id, tenant_id)
        if not delivery:
            return {"success": False, "error": "Delivery not found"}

        if new_status == "EN_ROUTE":
            ok = delivery.start_route()
        elif new_status == "ARRIVED":
            ok = delivery.arrive()
        elif new_status == "DELIVERED":
            proof = None
            if proof_type:
                proof = DeliveryProof(
                    delivery_id=delivery_id,
                    proof_type=ProofType(proof_type),
                )
            ok = delivery.complete(proof)
        elif new_status == "FAILED":
            reason = DeliveryFailureReason.OTHER
            if failure_reason:
                try:
                    reason = DeliveryFailureReason(failure_reason)
                except ValueError:
                    pass
            ok = delivery.fail(reason, failure_notes)
        elif new_status == "CANCELLED":
            ok = delivery.cancel(actor_type)
        else:
            return {"success": False, "error": f"Unknown status: {new_status}"}

        if not ok:
            return {"success": False, "error": f"Cannot transition to {new_status}"}

        self._delivery_repo.save(delivery)

        # Release driver if terminal
        if delivery.status in {DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED, DeliveryStatus.FAILED}:
            if delivery.driver_id and self._driver_repo:
                driver = self._driver_repo.find_by_id(delivery.driver_id, tenant_id)
                if driver:
                    driver.set_available()
                    self._driver_repo.save(driver)

        return {"success": True, "delivery": delivery.to_dict()}


class CreateRouteUseCase:
    """Create a route with stops."""

    def __init__(self, route_repo: RouteRepository, delivery_repo: DeliveryRepository):
        self._route_repo = route_repo
        self._delivery_repo = delivery_repo

    def execute(
        self, tenant_id: str, driver_id: str, vehicle_id: Optional[str] = None, stops: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        route = Route(tenant_id=tenant_id, driver_id=driver_id, vehicle_id=vehicle_id)
        if stops:
            for i, stop_data in enumerate(stops):
                delivery_id = stop_data.get("delivery_id", "")
                delivery = self._delivery_repo.find_by_id(delivery_id, tenant_id)
                addr_snapshot = ""
                if delivery:
                    addr_snapshot = delivery.address.full_address()
                route.add_stop(
                    delivery_id=delivery_id,
                    sequence=stop_data.get("sequence", i + 1),
                    customer_name=stop_data.get("customer_name", delivery.customer_name if delivery else ""),
                    customer_phone=stop_data.get("customer_phone", ""),
                    address_snapshot=addr_snapshot or stop_data.get("address", ""),
                )
        saved = self._route_repo.save(route)
        return {"success": True, "route": saved.to_dict()}


class DispatchRouteUseCase:
    """Dispatch a route."""

    def __init__(self, route_repo: RouteRepository, delivery_repo: DeliveryRepository):
        self._route_repo = route_repo
        self._delivery_repo = delivery_repo

    def execute(self, tenant_id: str, route_id: str) -> Dict[str, Any]:
        route = self._route_repo.find_by_id(route_id, tenant_id)
        if not route:
            return {"success": False, "error": "Route not found"}
        if not route.dispatch():
            return {"success": False, "error": f"Cannot dispatch route in status {route.status.value}"}
        # Dispatch all deliveries in route
        for stop in route.stops:
            delivery = self._delivery_repo.find_by_id(stop.delivery_id, tenant_id)
            if delivery and delivery.can_transition(DeliveryStatus.DISPATCHED):
                delivery.dispatch()
                self._delivery_repo.save(delivery)
        self._route_repo.save(route)
        return {"success": True, "route": route.to_dict()}


class GetDeliveryUseCase:
    """Get delivery details."""

    def __init__(self, delivery_repo: DeliveryRepository):
        self._repo = delivery_repo

    def execute(self, tenant_id: str, delivery_id: str, customer_codigo: Optional[str] = None) -> Dict[str, Any]:
        delivery = self._repo.find_by_id(delivery_id, tenant_id)
        if not delivery:
            return {"success": False, "error": "Delivery not found"}
        # Customer ownership check
        if customer_codigo and delivery.customer_codigo != customer_codigo:
            return {"success": False, "error": "Access denied"}
        return {"success": True, "delivery": delivery.to_dict()}


class ListDeliveriesUseCase:
    """List deliveries with filters."""

    def __init__(self, delivery_repo: DeliveryRepository):
        self._repo = delivery_repo

    def execute(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        driver_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        delivery_status = None
        if status:
            try:
                delivery_status = DeliveryStatus(status)
            except ValueError:
                pass
        if driver_id:
            deliveries = self._repo.list_by_driver(driver_id, tenant_id)
        else:
            deliveries = self._repo.list_by_tenant(tenant_id, delivery_status, limit, offset)
        return {
            "success": True,
            "deliveries": [d.to_dict() for d in deliveries],
            "count": len(deliveries),
        }


# ── Legacy Use Cases (Phase 5/6 backward compat) ───────


class CreateDriverUseCase:
    """Legacy: Create a new DeliveryDriver (entregador)."""

    def __init__(self, repository):
        self.repository = repository

    def execute(self, data: dict):
        from app.domain.delivery.entity import DeliveryDriver
        from datetime import datetime

        codigo = self.repository.proximo_codigo()
        driver = DeliveryDriver(
            codigo=codigo,
            nome=data["nome"],
            telefone=data["telefone"],
            placa=data.get("placa"),
            ativo=True,
            created_at=datetime.utcnow(),
        )
        result = self.repository.criar(driver)
        # Save credentials if provided
        username = data.get("username")
        password_hash = data.get("password_hash")
        if username and password_hash:
            self.repository.set_credentials(result.codigo, username, password_hash)
        return result


def generate_temp_password() -> str:
    """Senha temporária legível para ditado: 3 grupos de 4 (sem ambíguos)."""
    import secrets

    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    groups = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)]
    return "-".join(groups)


class DriverRoleMissingError(Exception):
    """O tenant não tem o papel DRIVER — sem ele a credencial não resolve."""


class DriverUsernameTakenError(Exception):
    """Username já em uso (a unicidade é global, não por tenant)."""


class CreateDriverWithCredentialUseCase:
    """Cadastro canônico do entregador: entidade **e** credencial de login.

    Vive na camada de aplicação, e não na rota, porque dois entrypoints
    precisam do mesmo efeito e não podem divergir: `POST /admin/drivers`
    (canônico) e `POST /delivery/drivers` (alias). Antes cada um fazia a sua
    versão — o alias criava só a entidade, sem login, e o entregador cadastrado
    por ele não conseguia abrir o app (o login é `/auth/login`).

    Cria na MESMA transação:
    - `DeliveryDriverModel` — o cadastro, com `codigo` sequencial de 6 dígitos;
    - `AuthUserModel(role=DRIVER, driver_id=codigo, must_change_password=True)`;
    - a membership do tenant — sem ela o login cairia em OPERATOR.

    A senha temporária só existe no retorno: nunca em log, audit ou listagem.
    O audit é gravado aqui, **uma vez por criação**.

    TODO (Fase 2): envio da senha temporária por SMS/WhatsApp entra aqui;
    hoje ela só aparece nesta resposta e alguém precisa repassá-la.
    """

    def __init__(self, db, tenant_id: str, actor_id: str = ""):
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def _next_codigo(self) -> str:
        """Próximo código do tenant, pelo maior valor numérico (6 dígitos).

        Mesma convenção do `SQLAlchemyDeliveryDriverRepository.proximo_codigo`,
        inline para permanecer na mesma transação do cadastro. Ordenar por `id`
        devolveria um código já usado quando o maior não é o último criado
        (importação, seed, testes).
        """
        from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

        highest = 0
        rows = self.db.query(DeliveryDriverModel.codigo).filter(DeliveryDriverModel.tenant_id == self.tenant_id).all()
        for (codigo,) in rows:
            if codigo is None:
                continue
            try:
                highest = max(highest, int(str(codigo)))
            except (TypeError, ValueError):
                continue
        return f"{highest + 1:06d}"

    def execute(
        self,
        nome: str,
        telefone: str,
        document: Optional[str] = None,
        vehicle_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        import uuid as _uuid

        from app.domain.security.models import hash_password
        from app.infrastructure.repositories.auth_model import (
            AuthMembershipModel,
            AuthRoleModel,
            AuthUserModel,
        )
        from app.infrastructure.repositories.auth_repository import SQLAlchemyAuditRepository
        from app.infrastructure.repositories.delivery_model import DeliveryDriverModel

        role = self.db.query(AuthRoleModel).filter(AuthRoleModel.name == "DRIVER").first()
        if role is None:
            raise DriverRoleMissingError("Role DRIVER not found")

        codigo = self._next_codigo()
        username = username or f"drv_{codigo}"
        if self.db.query(AuthUserModel).filter(AuthUserModel.username == username).first():
            raise DriverUsernameTakenError(username)

        temp_password = generate_temp_password()
        driver = DeliveryDriverModel(
            tenant_id=self.tenant_id,
            codigo=codigo,
            nome=nome,
            telefone=telefone,
            document=document,
            vehicle_id=vehicle_id,
            ativo=True,
            status="AVAILABLE",
        )
        user_id = str(_uuid.uuid4())
        user = AuthUserModel(
            id=user_id,
            username=username,
            email="",
            display_name=nome,
            password_hash=hash_password(temp_password),
            status="ACTIVE",
            role_id=role.id,
            driver_id=codigo,
            must_change_password=True,
            created_by=self.actor_id,
        )
        membership = AuthMembershipModel(
            id=str(_uuid.uuid4()),
            user_id=user_id,
            tenant_id=self.tenant_id,
            role_id=role.id,
        )
        self.db.add(driver)
        self.db.add(user)
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(driver)
        self.db.refresh(user)

        payload = {
            "driver_id": driver.codigo,
            "name": driver.nome,
            "phone": driver.telefone,
            "document": driver.document,
            "active": bool(driver.ativo),
            "status": driver.status,
            "username": user.username,
            "credential_status": user.status,
            "must_change_password": bool(user.must_change_password),
        }
        SQLAlchemyAuditRepository(self.db).create(
            actor_id=self.actor_id,
            tenant_id=self.tenant_id,
            action="USER_CREATED",
            resource="driver",
            resource_id=codigo,
            before_json=None,
            after_json=payload,
            platform="desktop",
        )
        return {
            "driver_id": codigo,
            "username": username,
            "temporary_password": temp_password,
            "driver": payload,
        }


class UpdateDriverUseCase:
    """Legacy: update the editable fields of an existing DeliveryDriver."""

    def __init__(self, repository):
        self.repository = repository

    def execute(self, codigo: str, data: dict):
        """Atualiza só o que veio no corpo e devolve o retrato novo.

        `codigo` não é editável — é a identidade gravada em `delivery_records`,
        `driver_locations` e no histórico de posições. O schema já rejeita o
        campo com 422.

        `document`/`vehicle_id`/`status` existem no model e **não** na entidade:
        gravar aqui evita o padrão "aceita campo e descarta em silêncio".
        """
        entity = self.repository.buscar_por_codigo(codigo)
        if not entity:
            return None

        if any(k in data for k in ("nome", "telefone", "placa")):
            self.repository.update_profile(
                codigo,
                nome=data.get("nome") or entity.nome,
                telefone=data.get("telefone") or entity.telefone,
                placa=data.get("placa", entity.placa),
            )
        if "document" in data or "vehicle_id" in data:
            self.repository.set_vehicle_and_document(codigo, data.get("document"), data.get("vehicle_id"))
        if data.get("status"):
            self.repository.set_status(codigo, data["status"])

        return self.repository.snapshot(codigo)


class DriverInRouteError(Exception):
    """Exclusão bloqueada: o entregador tem entrega em rota."""

    def __init__(self, statuses):
        self.statuses = list(statuses)
        super().__init__("Entregador com entrega em rota: " + ", ".join(self.statuses))


class DeleteDriverUseCase:
    """Legacy: soft delete do entregador — cadastro, credencial e rastreio.

    Não apaga a linha: `delivery_records`, `driver_locations` e o histórico de
    posições guardam o `codigo`. Desliga o cadastro (`ativo`) e o estado
    operacional (`status`), revoga as sessões do `User` vinculado (o entregador
    não loga mais) e incrementa o `tracking_epoch`, que entra na assinatura dos
    links públicos — os emitidos antes viram 410.

    Entrega em rota bloqueia: excluir deixaria entrega órfã apontando para um
    entregador desligado.
    """

    IN_ROUTE = ("ASSIGNED", "DISPATCHED", "EN_ROUTE")

    def __init__(self, db, tenant_id: str, actor_id: str = ""):
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def execute(self, codigo: str):
        from datetime import datetime

        from app.infrastructure.repositories.auth_model import AuthUserModel
        from app.infrastructure.repositories.auth_repository import (
            SQLAlchemyAuditRepository,
            SQLAlchemySessionRepository,
        )
        from app.infrastructure.repositories.delivery_model import DeliveryDriverModel
        from app.infrastructure.repositories.delivery_persistence_repository import (
            SQLAlchemyDeliveryPersistenceRepository,
        )
        from app.infrastructure.repositories.delivery_repository import SQLAlchemyDeliveryDriverRepository

        driver = (
            self.db.query(DeliveryDriverModel)
            .filter(
                DeliveryDriverModel.tenant_id == self.tenant_id,
                DeliveryDriverModel.codigo == codigo,
            )
            .first()
        )
        if not driver:
            return None

        deliveries = SQLAlchemyDeliveryPersistenceRepository(self.db, self.tenant_id).list_deliveries(
            driver_id=codigo, limit=200
        )
        em_rota = sorted({d.status for d in deliveries if d.status in self.IN_ROUTE})
        if em_rota:
            raise DriverInRouteError(em_rota)

        user = self.db.query(AuthUserModel).filter(AuthUserModel.driver_id == codigo).first()
        before = {
            "driver_id": codigo,
            "active": bool(driver.ativo),
            "status": driver.status,
            "username": user.username if user else None,
        }

        driver.ativo = False
        driver.status = "DISABLED"
        driver.updated_at = datetime.utcnow()
        revoked = 0
        if user:
            user.status = "DISABLED"
            user.updated_at = datetime.utcnow()
            revoked = SQLAlchemySessionRepository(self.db).revoke_all_for_user(user.id)
        self.db.commit()

        epoch = SQLAlchemyDeliveryDriverRepository(self.db, tenant_id=self.tenant_id).bump_tracking_epoch(codigo)

        SQLAlchemyAuditRepository(self.db).create(
            actor_id=self.actor_id,
            tenant_id=self.tenant_id,
            action="USER_DISABLED",
            resource="driver",
            resource_id=codigo,
            before_json=before,
            after_json={
                "driver_id": codigo,
                "active": False,
                "status": "DISABLED",
                "revoked_sessions": revoked,
                "tracking_epoch": epoch,
                "username": user.username if user else None,
            },
            platform="desktop",
        )

        return {"driver_id": codigo, "revoked_sessions": revoked, "tracking_epoch": epoch}


class GetDriverUseCase:
    """Legacy: Get DeliveryDriver by codigo."""

    def __init__(self, repository):
        self.repository = repository

    def execute(self, codigo: str):
        return self.repository.buscar_por_codigo(codigo)


class ListDriversUseCase:
    """Legacy: List all active DeliveryDrivers."""

    def __init__(self, repository):
        self.repository = repository

    def execute(self):
        return self.repository.listar_todos()


class DisableDriverUseCase:
    """Legacy: Disable a DeliveryDriver."""

    def __init__(self, repository):
        self.repository = repository

    def execute(self, codigo: str):
        return self.repository.desativar(codigo)
