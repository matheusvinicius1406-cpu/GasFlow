"""
Delivery Report Metrics — F9: agregados para os gráficos da ReportsPage.

Spec (§3.9):
- Entregas por período (diário), por entregador e por região (bairro)
- Tempo médio de entrega: atribuição → DELIVERED (minutos)
- Comparativo de performance entre entregadores
- Sempre filtrado por tenant; janela de dias parametrizável (7/30/90,
  default 30) alinhada ao resto do sistema.

Estratégia: agregação em SQL (func.count/func.avg) direto sobre
delivery_records — mesmo padrão do heatmap da F8, sem postgis e sem
carregar entidades para memória. `func.julianday` é SQLite (banco alvo do
desktop); MySQL/Postgres têm equivalente, mas o app roda SQLite.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import setup_logging
from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord

logger = setup_logging("INFO")

VALID_DAYS = (7, 30, 90)


def _since(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


def _base_query(db: Session, tenant_id: str, days: int):
    """Janela base: criadas nos últimos N dias (independe do status)."""
    return db.query(DeliveryRecord).filter(
        DeliveryRecord.tenant_id == tenant_id,
        DeliveryRecord.created_at >= _since(days),
    )


def deliveries_by_day(db: Session, tenant_id: str, days: int = 30) -> List[Dict[str, Any]]:
    """Série diária: criadas, entregues e falhas por dia."""
    rows = (
        _base_query(db, tenant_id, days)
        .with_entities(
            func.date(DeliveryRecord.created_at).label("day"),
            func.count(DeliveryRecord.id),
        )
        .group_by(func.date(DeliveryRecord.created_at))
        .all()
    )
    delivered = (
        _base_query(db, tenant_id, days)
        .filter(DeliveryRecord.status == "DELIVERED")
        .with_entities(
            func.date(DeliveryRecord.delivered_at).label("day"),
            func.count(DeliveryRecord.id),
        )
        .group_by(func.date(DeliveryRecord.delivered_at))
        .all()
    )
    failed = (
        _base_query(db, tenant_id, days)
        .filter(DeliveryRecord.status == "FAILED")
        .with_entities(
            func.date(DeliveryRecord.failed_at).label("day"),
            func.count(DeliveryRecord.id),
        )
        .group_by(func.date(DeliveryRecord.failed_at))
        .all()
    )

    by_day: Dict[str, Dict[str, int]] = {}
    for day, count in rows:
        by_day.setdefault(str(day), {"created": 0, "delivered": 0, "failed": 0})["created"] = int(count)
    for day, count in delivered:
        if day:
            by_day.setdefault(str(day), {"created": 0, "delivered": 0, "failed": 0})["delivered"] = int(count)
    for day, count in failed:
        if day:
            by_day.setdefault(str(day), {"created": 0, "delivered": 0, "failed": 0})["failed"] = int(count)

    return [{"day": day, **counts} for day, counts in sorted(by_day.items())]


def deliveries_by_driver(db: Session, tenant_id: str, days: int = 30) -> List[Dict[str, Any]]:
    """Por entregador: atribuídas, entregues, falhas e tempo médio (min)."""
    rows = (
        _base_query(db, tenant_id, days)
        .filter(DeliveryRecord.driver_id.isnot(None))
        .with_entities(
            DeliveryRecord.driver_id,
            func.count(DeliveryRecord.id),
        )
        .group_by(DeliveryRecord.driver_id)
        .all()
    )
    # Status em consultas separadas (portátil — evita SUM(CASE) por dialect):
    counts: Dict[str, Dict[str, Any]] = {}
    for driver_id, total in rows:
        counts[driver_id] = {"assigned": int(total), "delivered": 0, "failed": 0, "avg_minutes": None}
    for status_key in ("DELIVERED", "FAILED"):
        rows_status = (
            _base_query(db, tenant_id, days)
            .filter(DeliveryRecord.driver_id.isnot(None), DeliveryRecord.status == status_key)
            .with_entities(DeliveryRecord.driver_id, func.count(DeliveryRecord.id))
            .group_by(DeliveryRecord.driver_id)
            .all()
        )
        for driver_id, count in rows_status:
            counts.setdefault(driver_id, {"assigned": 0, "delivered": 0, "failed": 0, "avg_minutes": None})[
                status_key.lower()
            ] = int(count)

    # Tempo médio atribuição → DELIVERED (só entregues com assigned_at/delivered_at)
    avg_rows = (
        _base_query(db, tenant_id, days)
        .filter(
            DeliveryRecord.driver_id.isnot(None),
            DeliveryRecord.status == "DELIVERED",
            DeliveryRecord.assigned_at.isnot(None),
            DeliveryRecord.delivered_at.isnot(None),
        )
        .with_entities(
            DeliveryRecord.driver_id,
            func.avg(func.julianday(DeliveryRecord.delivered_at) - func.julianday(DeliveryRecord.assigned_at)),
        )
        .group_by(DeliveryRecord.driver_id)
        .all()
    )
    for driver_id, avg_days in avg_rows:
        if avg_days is not None:
            counts.setdefault(driver_id, {"assigned": 0, "delivered": 0, "failed": 0, "avg_minutes": None})[
                "avg_minutes"
            ] = round(float(avg_days) * 24 * 60, 1)

    return [
        {"driver_id": driver_id, **stats}
        for driver_id, stats in sorted(counts.items(), key=lambda kv: -kv[1]["delivered"])
    ]


def deliveries_by_neighborhood(db: Session, tenant_id: str, days: int = 30) -> List[Dict[str, Any]]:
    """Por bairro (região): total entregue — espelha a agregação da F8."""
    rows = (
        _base_query(db, tenant_id, days)
        .filter(DeliveryRecord.status == "DELIVERED")
        .with_entities(
            func.coalesce(DeliveryRecord.address_neighborhood, "(sem bairro)"),
            func.count(DeliveryRecord.id),
        )
        .group_by(func.coalesce(DeliveryRecord.address_neighborhood, "(sem bairro)"))
        .all()
    )
    return [
        {"neighborhood": neighborhood, "count": int(count)}
        for neighborhood, count in sorted(rows, key=lambda r: -int(r[1]))
    ]


def delivery_report(db: Session, tenant_id: str, days: int = 30) -> Dict[str, Any]:
    """Payload completo para os gráficos da ReportsPage (F9)."""
    return {
        "days": days,
        "generated_at": datetime.utcnow().isoformat(),
        "by_day": deliveries_by_day(db, tenant_id, days),
        "by_driver": deliveries_by_driver(db, tenant_id, days),
        "by_neighborhood": deliveries_by_neighborhood(db, tenant_id, days),
    }
