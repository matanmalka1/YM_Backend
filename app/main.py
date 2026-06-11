from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.core.env_validator import EnvValidator
from app.core.openapi import build_openapi
from app.core.exception_handlers import setup_exception_handlers
from app.core.logging_config import get_logger, setup_logging
from app.core.sentry import configure_sentry
from app.lifespan import lifespan
from app.middleware.rate_limiting import setup_rate_limiting
from app.middleware.request_id import RequestIDMiddleware
from app.router_registry import register_routers

EnvValidator.validate()

setup_logging(level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
configure_sentry(settings)
logger = get_logger(__name__)
if settings.APP_ENV == "development":
    logger.info("CORS allowed origins: %s", settings.CORS_ALLOWED_ORIGINS)

_is_production = settings.APP_ENV == "production"
app = FastAPI(
    title="Binder & Billing CRM",
    version="1.0.0",
    lifespan=lifespan,
    openapi_url=None if _is_production else "/openapi.json",
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
)


class RootResponse(BaseModel):
    service: Literal["binder-billing-crm"]
    status: Literal["running"]


class AppInfoResponse(BaseModel):
    app: Literal["Binder Billing CRM"]
    env: Literal["development", "test", "staging", "production"]


@app.get("/", response_model=RootResponse)
def root():
    return {"service": "binder-billing-crm", "status": "running"}


@app.get("/info", response_model=AppInfoResponse)
def info():
    return {"app": "Binder Billing CRM", "env": settings.APP_ENV}


setup_exception_handlers(app)
setup_rate_limiting(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)

register_routers(app)


def custom_openapi():
    return build_openapi(app)


app.openapi = custom_openapi

if settings.APP_ENV in ("development", "test"):
    import os

    from fastapi.staticfiles import StaticFiles

    os.makedirs("./storage", exist_ok=True)
    app.mount("/local-storage", StaticFiles(directory="./storage"), name="local-storage")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
