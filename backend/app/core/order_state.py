"""Máquina de estados do status do pedido."""

from app.models.order import OrderStatus

# Transições válidas: de -> conjunto de destinos permitidos.
ORDER_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PENDING.value: {OrderStatus.CONFIRMED.value, OrderStatus.CANCELLED.value},
    OrderStatus.CONFIRMED.value: {OrderStatus.PREPARING.value, OrderStatus.CANCELLED.value},
    OrderStatus.PREPARING.value: {OrderStatus.DELIVERING.value, OrderStatus.CANCELLED.value},
    OrderStatus.DELIVERING.value: {OrderStatus.DELIVERED.value, OrderStatus.CANCELLED.value},
    OrderStatus.DELIVERED.value: set(),  # terminal
    OrderStatus.CANCELLED.value: set(),  # terminal
}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ORDER_TRANSITIONS.get(from_status, set())
