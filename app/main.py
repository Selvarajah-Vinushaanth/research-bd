# ============================================
# AI Research Assistant - FastAPI Application Entry Point
# ============================================

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.database.prisma_client import prisma_connect, prisma_disconnect
from app.middleware.rate_limiter import setup_rate_limiter
from app.middleware.security import SecurityHeadersMiddleware

# --- Structured Logging ---
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer() if settings.is_production else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


# --- Lifespan (startup / shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Manage application lifecycle: startup and shutdown events."""
    logger.info("application_starting", version=settings.APP_VERSION, env=settings.APP_ENV)

    # Connect to database
    await prisma_connect()
    logger.info("database_connected")

    # Initialize AI models lazily (they load on first use)
    logger.info("ai_models_ready", note="Models will load on first request")

    yield

    # Shutdown
    await prisma_disconnect()
    logger.info("application_stopped")


# --- Application Factory ---
def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="AI-powered research assistant for academic paper analysis, semantic search, and knowledge extraction.",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # --- Middleware Stack (order matters: last added = first executed) ---

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )

    # GZip compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Rate limiter
    setup_rate_limiter(app)

    # Prometheus metrics
    if settings.is_production:
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # Sentry
    if settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
            environment=settings.APP_ENV,
        )

    # --- Request Logging Middleware ---
    @app.middleware("http")
    async def log_requests(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", "")
        start_time = time.perf_counter()

        response = await call_next(request)

        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}"
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration=round(process_time, 4),
            request_id=request_id,
        )
        return response

    # --- Register Routers ---
    from app.api.auth_routes import router as auth_router
    from app.api.paper_routes import router as paper_router
    from app.api.chat_routes import router as chat_router
    from app.api.research_routes import router as research_router
    from app.api.notes_routes import router as notes_router
    from app.api.collection_routes import router as collection_router
    from app.api.advanced_routes import router as advanced_router
    from app.api.health_routes import router as health_router

    app.include_router(health_router, tags=["Health"])
    app.include_router(auth_router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["Authentication"])
    app.include_router(paper_router, prefix=f"{settings.API_V1_PREFIX}/papers", tags=["Papers"])
    app.include_router(chat_router, prefix=f"{settings.API_V1_PREFIX}/chat", tags=["Chat"])
    app.include_router(research_router, prefix=f"{settings.API_V1_PREFIX}/research", tags=["Research"])
    app.include_router(notes_router, prefix=f"{settings.API_V1_PREFIX}/notes", tags=["Notes"])
    app.include_router(collection_router, prefix=f"{settings.API_V1_PREFIX}/collections", tags=["Collections"])
    app.include_router(advanced_router, prefix=f"{settings.API_V1_PREFIX}/advanced", tags=["Advanced"])

    return app


# --- Create app instance ---
app = create_app()


# --- Root endpoint ---
@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }
