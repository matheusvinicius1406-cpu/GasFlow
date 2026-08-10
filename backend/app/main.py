from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.clients import router as client_router
from app.api.companies import router as companies_router
from app.api.delivery import router as delivery_router
from app.api.health import router as health_router
from app.api.orders import router as orders_router
from app.api.products import router as products_router
from app.api.users import router as users_router
from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.database.init_db import init_db

configure_logging()
logger = get_logger("app")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    """Traduz exceções de domínio em respostas HTTP com o status correto."""
    logger.info("domain_error", status_code=exc.status_code, detail=exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.on_event("startup")
def on_startup():
    # Em SQLite (dev/testes) cria as tabelas; em Postgres use Alembic (`alembic upgrade head`).
    if settings.database_url.startswith("sqlite"):
        init_db()
    logger.info("app_started", name=settings.app_name, version=settings.app_version)


@app.get("/")
def root():
    return {"name": settings.app_name, "status": "online"}


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(companies_router)
app.include_router(client_router)
app.include_router(orders_router)
app.include_router(products_router)
app.include_router(delivery_router)
