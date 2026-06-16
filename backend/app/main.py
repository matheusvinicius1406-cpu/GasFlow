from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.init_db import init_db
from app.api.health import router as health_router
from app.api.clients import router as client_router
from app.api.orders import router as orders_router
from app.api.products import router as products_router
from app.api.delivery import router as delivery_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
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
        "status": "online"
    }


app.include_router(health_router)
app.include_router(client_router)
app.include_router(orders_router)
app.include_router(products_router)
app.include_router(delivery_router)