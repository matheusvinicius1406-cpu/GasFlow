"""
GasFlow Relay — camada de nuvem do App do Entregador (MVP).

Papel: ponte entre o mobile (fora do WiFi do depósito) e o desktop.

    Desktop ──WS outbound──▶ /relay/ws?tenant={id}&token={secret}
    Mobile  ──HTTPS POST──▶  /driver/location  ──▶ roteia via WS p/ desktop
    Mobile  ──HTTPS GET───▶  /driver/last     ──▶ cache da última posição

O relay é stateless além do registro de desktops em memória: as regras de
negócio (autenticação real, work hours, persistência) ficam no backend do
depósito. Autenticação simples por token compartilhado (env RELAY_TOKEN) —
o mesmo secret configurado no desktop. HTTPS é obrigatório (Fly encerra TLS).

Código local apenas — o deploy no Fly.io fica para o dono do projeto
(fly deploy + secrets), conforme decidido na sessão.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field

app = FastAPI(title="GasFlow Relay", version="0.1.0")

RELAY_TOKEN = os.getenv("RELAY_TOKEN", "")


# ── Registry de desktops conectados ──────────────────────────


class DesktopRegistry:
    """tenant_id → WebSocket ativo. 1 desktop por tenant (MVP)."""

    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}

    def register(self, tenant_id: str, ws: WebSocket) -> bool:
        """Registra desktop; False se o tenant já tem conexão ativa."""
        if tenant_id in self._connections:
            existing = self._connections[tenant_id]
            if existing.client_state.name == "CONNECTED":
                return False
        self._connections[tenant_id] = ws
        return True

    def unregister(self, tenant_id: str, ws: WebSocket) -> None:
        if self._connections.get(tenant_id) is ws:
            del self._connections[tenant_id]

    def is_online(self, tenant_id: str) -> bool:
        ws = self._connections.get(tenant_id)
        return ws is not None and ws.client_state.name == "CONNECTED"

    async def send_to_desktop(self, tenant_id: str, payload: Dict[str, Any]) -> bool:
        """Envia evento ao desktop; False se offline/erro (caller faz cache)."""
        ws = self._connections.get(tenant_id)
        if not ws or ws.client_state.name != "CONNECTED":
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            self.unregister(tenant_id, ws)
            return False


registry = DesktopRegistry()

# Cache da última posição por tenant (o desktop busca ao reconectar)
_last_position: Dict[str, Dict[str, Any]] = {}


# ── Auth simples ─────────────────────────────────────────────


def _check_token(token: str) -> None:
    if not RELAY_TOKEN:
        raise HTTPException(503, detail="Relay sem RELAY_TOKEN configurado")
    if not token or token != RELAY_TOKEN:
        raise HTTPException(401, detail="Invalid relay token")


# ── Schemas ──────────────────────────────────────────────────


class LocationPing(BaseModel):
    lat: float
    lng: float
    speed: Optional[float] = None
    heading: Optional[float] = None
    accuracy: Optional[float] = None
    recorded_at: Optional[datetime] = None


class LocationBatch(BaseModel):
    driver_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64)
    positions: List[LocationPing] = Field(min_length=1, max_length=100)


# ── Endpoints ────────────────────────────────────────────────


@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "desktops_online": [t for t in registry._connections if registry.is_online(t)],
    }


@app.websocket("/relay/ws")
async def relay_ws(
    ws: WebSocket, tenant: str = Query(default=""), token: str = Query(default="")
):
    """Desktop conecta aqui (outbound) e recebe eventos de localização."""
    _check_token(token)
    if not tenant:
        await ws.close(code=4400)
        return
    await ws.accept()
    if not registry.register(tenant, ws):
        await ws.close(code=4409)  # já existe desktop p/ este tenant
        return
    try:
        # Entrega a última posição em cache ao reconectar (se houver)
        if tenant in _last_position:
            await ws.send_json(
                {"type": "driver:location", "payload": _last_position[tenant]}
            )
        while True:
            # Desktop mantém a conexão; mensagens do desktop (ex.: ack/ping)
            # são aceitas e ignoradas no MVP.
            await ws.receive_text()
    except WebSocketDisconnect:
        registry.unregister(tenant, ws)
    except Exception:
        registry.unregister(tenant, ws)


@app.post("/driver/location")
async def driver_location(
    batch: LocationBatch, x_relay_token: str = Header(default="")
):
    """Mobile envia posições; roteia ao desktop via WS ou cacheia."""
    _check_token(x_relay_token)
    delivered = False
    last_payload: Optional[Dict[str, Any]] = None
    for pos in batch.positions:
        payload = {
            "driver_id": batch.driver_id,
            "lat": pos.lat,
            "lng": pos.lng,
            "speed": pos.speed,
            "heading": pos.heading,
            "accuracy": pos.accuracy,
            "recorded_at": (pos.recorded_at or datetime.now(timezone.utc)).isoformat(),
        }
        last_payload = payload
        delivered = (
            await registry.send_to_desktop(
                batch.tenant_id, {"type": "driver:location", "payload": payload}
            )
            or delivered
        )
    if last_payload is not None:
        _last_position[batch.tenant_id] = last_payload
    return {"accepted": len(batch.positions), "delivered_to_desktop": delivered}


@app.get("/driver/last")
def driver_last(
    tenant: str = Query(default=""), x_relay_token: str = Header(default="")
):
    """Última posição conhecida (desktop pede ao reconectar)."""
    _check_token(x_relay_token)
    return _last_position.get(tenant)
