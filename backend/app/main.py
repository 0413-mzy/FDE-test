import re
from contextlib import asynccontextmanager
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.api.core import router as core_router
from app.api.errors import ApiError
from app.api.health import router as health_router
from app.api.resolution import router as resolution_router
from app.commerce.ai_router import router as ai_router
from app.commerce.catalog_router import router as catalog_router
from app.commerce.data_router import router as data_router
from app.commerce.onboarding_router import router as onboarding_router
from app.commerce.platform_router import router as platform_router
from app.commerce.public_demo import install_public_demo
from app.commerce.router import demo_router
from app.commerce.router import router as commerce_router
from app.context.collector import ProviderBundle
from app.core.clock import SystemClock
from app.core.config import Settings
from app.db.connection import product_engine
from app.integrations.sandbox.client import SandboxClient
from app.integrations.sandbox.providers import (
    SandboxLogisticsProvider,
    SandboxMessageProvider,
    SandboxOrderProvider,
    SandboxWarehouseProvider,
)


def create_app(
    settings: Settings | None = None, *, session_factory=None, clock=None, provider_factory=None
) -> FastAPI:
    settings = settings or Settings()
    engine = None
    engine_lock = Lock()

    def default_sessions():
        nonlocal engine
        with engine_lock:
            if engine is None:
                if settings.database_url is None:
                    raise ValueError("Product database is not configured")
                engine = product_engine(settings.database_url.get_secret_value())
        return Session(engine)

    @asynccontextmanager
    async def lifespan(application):
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    application = FastAPI(title="Commerce Platform", version="0.0.1", lifespan=lifespan)
    application.state.settings = settings
    application.state.clock = clock or SystemClock()
    application.state.session_factory = session_factory or default_sessions

    @asynccontextmanager
    async def default_providers():
        async with SandboxClient(settings, application.state.clock) as client:
            yield ProviderBundle(
                SandboxOrderProvider(client),
                SandboxLogisticsProvider(client),
                SandboxWarehouseProvider(client),
                SandboxMessageProvider(client),
            )

    application.state.provider_factory = provider_factory or default_providers
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id", "Idempotency-Key"],
        expose_headers=["X-Request-Id", "Location", "Idempotent-Replay"],
        allow_credentials=False,
    )

    @application.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError):
        return JSONResponse(error.payload(request.state.request_id), status_code=error.status)

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        if request.url.path.startswith("/api/commerce/v1"):
            from app.commerce.errors import CommerceError

            request_id = getattr(request.state, "request_id", str(uuid4()))
            response = JSONResponse(
                CommerceError(
                    error.status_code,
                    "NOT_FOUND" if error.status_code == 404 else "INVALID_REQUEST",
                ).payload(request_id),
                status_code=error.status_code,
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Request-Id"] = request_id
            return response
        if request.url.path.startswith("/api/v1"):
            code = "RESOURCE_NOT_FOUND" if error.status_code == 404 else "INVALID_REQUEST"
            return await api_error(request, ApiError(error.status_code, code))
        return JSONResponse({"detail": error.detail}, status_code=error.status_code)

    @application.middleware("http")
    async def request_boundary(request: Request, call_next):
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)
        supplied = request.headers.get("x-request-id", "")
        request.state.request_id = (
            supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,100}", supplied) else str(uuid4())
        )
        origin = request.headers.get("origin")
        if origin is not None and origin not in settings.cors_allowed_origins:
            response = await api_error(request, ApiError(403, "FORBIDDEN"))
        else:
            try:
                response = await call_next(request)
            except Exception:
                response = await api_error(request, ApiError(500, "INTERNAL_ERROR"))
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    application.include_router(health_router)
    application.include_router(commerce_router)
    application.include_router(ai_router)
    application.include_router(onboarding_router)
    application.include_router(catalog_router)
    application.include_router(platform_router)
    application.include_router(data_router)
    if settings.app_env in {"development", "test"} or settings.commerce_public_demo:
        application.include_router(demo_router)
    if not settings.commerce_public_demo:
        application.include_router(core_router)
        application.include_router(resolution_router)
    install_public_demo(application, settings)

    def openapi():
        if application.openapi_schema is None:
            schema = get_openapi(
                title=application.title, version=application.version, routes=application.routes
            )
            schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
            }
            schema["components"]["securitySchemes"]["CommerceBearer"] = {
                "type": "http",
                "scheme": "bearer",
            }
            application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = openapi
    return application


app = create_app()
