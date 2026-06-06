from fastapi import FastAPI

from app.database.init_db import init_db
from app.api.health import router as health_router
from app.api.clients import router as client_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version
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