"""
GasFlow — Sistema operacional para depósitos de gás e água.

Arquitetura: Domain-Driven Design (DDD)
- Domain: Entidades e interfaces de repositório
- Application: Casos de uso (Use Cases)
- Infrastructure: Implementações SQLAlchemy
- Presentation: API Routes e Schemas
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.infrastructure.database.init_db import init_db
from app.presentation.api.health import router as health_router
from app.presentation.api.clients import router as client_router
from app.presentation.api.orders import router as orders_router
from app.presentation.api.products import router as products_router
from app.presentation.api.delivery import router as delivery_router
from app.presentation.api.whatsapp import router as whatsapp_router
from app.presentation.api.inventory import router as inventory_router
from app.presentation.api.finance import router as finance_router
from app.presentation.api.ai import router as ai_router
from app.presentation.api.whatsapp_gateway import router as whatsapp_gateway_router
from app.presentation.api.audio import router as audio_router
from app.presentation.api.automation import router as automation_router
from app.presentation.api.auth import router as auth_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Sistema operacional para depósitos de gás e água — API + WhatsApp Automation"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "online",
        "architecture": "Domain-Driven Design (DDD)",
        "services": {
            "api": "http://localhost:8000",
            "whatsapp": "http://localhost:3001",
            "docs": "http://localhost:8000/docs",
            "whatsapp_connect": "http://localhost:3001/connect"
        }
    }


app.include_router(health_router)
app.include_router(client_router)
app.include_router(orders_router)
app.include_router(products_router)
app.include_router(delivery_router)
app.include_router(whatsapp_router)
app.include_router(inventory_router)
app.include_router(finance_router)
app.include_router(ai_router)
app.include_router(whatsapp_gateway_router)
app.include_router(audio_router)
app.include_router(automation_router)
app.include_router(auth_router)
