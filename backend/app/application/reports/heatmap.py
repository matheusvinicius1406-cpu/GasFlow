"""
Delivery Heatmap — F8: densidade de entregas por bairro.

Spec (§3.8, decisões E1–E3):
- Agregação por bairro em SQL (group by address_neighborhood), sem postgis.
- Período padrão de 30 dias, filtrável (7/30/90).
- Cache de 5 minutos (TTL simples em memória por tenant/período —
  suficiente para visualização; invalidação por TTL apenas).
- Só visualização (E3): nada de posicionamento de entregador aqui.

Contagem considera entregas DELIVERED no período (delivered_at dentro da
janela) — o fato físico. Entregas sem bairro informado aparecem como
"(sem bairro)" para não sumirem do mapa.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import setup_logging
from app.infrastructure.repositories.delivery_persistence_model import DeliveryRecord

logger = setup_logging("INFO")

VALID_PERIODS = {7, 30, 90}
_CACHE: Dict[Tuple[str, int], Tuple[datetime, List[Dict[str, Any]]]] = {}
CACHE_TTL_SECONDS = 300  # 5 min (spec)


def delivery_heatmap(db: Session, tenant_id: str, days: int = 30) -> Dict[str, Any]:
    """Agrega entregas DELIVERED por bairro nos últimos `days` dias.

    Response:
        period_days, generated_at, total, neighborhoods: [
            {neighborhood, count, avg_latency_minutes, center: {lat, lng}|None}
        ]
    """
    days = days if days in VALID_PERIODS else 30

    # ── Cache 5min (por tenant+período) ──────────────────
    key = (tenant_id, days)
    now = datetime.utcnow()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]).total_seconds() < CACHE_TTL_SECONDS:
        return {
            "period_days": days,
            "generated_at": cached[0].isoformat(),
            "cached": True,
            "total": sum(n["count"] for n in cached[1]),
            "neighborhoods": cached[1],
        }

    since = now - timedelta(days=days)

    rows = (
        db.query(
            DeliveryRecord.address_neighborhood,
            func.count(DeliveryRecord.id),
            func.min(DeliveryRecord.address_lat),
            func.max(DeliveryRecord.address_lat),
            func.min(DeliveryRecord.address_lng),
            func.max(DeliveryRecord.address_lng),
        )
        .filter(
            DeliveryRecord.tenant_id == tenant_id,
            DeliveryRecord.status == "DELIVERED",
            DeliveryRecord.delivered_at >= since,
        )
        .group_by(DeliveryRecord.address_neighborhood)
        .all()
    )

    neighborhoods: List[Dict[str, Any]] = []
    total = 0
    for neighborhood, count, min_lat, max_lat, min_lng, max_lng in rows:
        name = (neighborhood or "").strip() or "(sem bairro)"
        count = int(count)
        total += count
        center = None
        # Centroide aproximado do bounding box (grátis, sem postgis).
        if min_lat is not None and max_lat is not None and min_lng is not None and max_lng is not None:
            center = {
                "lat": round((float(min_lat) + float(max_lat)) / 2, 6),
                "lng": round((float(min_lng) + float(max_lng)) / 2, 6),
            }
        neighborhoods.append(
            {
                "neighborhood": name,
                "count": count,
                "center": center,
            }
        )

    # Maior densidade primeiro (a UI usa para escalar cor/raio).
    neighborhoods.sort(key=lambda n: n["count"], reverse=True)

    result_payload = neighborhoods
    _CACHE[key] = (now, result_payload)

    return {
        "period_days": days,
        "generated_at": now.isoformat(),
        "cached": False,
        "total": total,
        "neighborhoods": result_payload,
    }


def invalidate_heatmap_cache(tenant_id: Optional[str] = None) -> None:
    """Invalida o cache (todas as chaves do tenant, ou todas)."""
    if tenant_id is None:
        _CACHE.clear()
        return
    for key in [k for k in _CACHE if k[0] == tenant_id]:
        _CACHE.pop(key, None)
