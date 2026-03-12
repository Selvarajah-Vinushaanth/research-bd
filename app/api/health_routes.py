# ============================================
# API Routes - Health Check
# ============================================

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.database.prisma_client import get_db

router = APIRouter()


@router.get("/health")
async def health_check():
    """System health check endpoint."""
    db = get_db()
    db_status = "connected" if db.is_connected() else "disconnected"

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "database": db_status,
        "services": {
            "database": db_status,
            "embedding_model": "ready",
            "summarizer_model": "ready",
            "qa_model": "ready",
        },
    }


@router.get("/health/ready")
async def readiness_check():
    """Kubernetes readiness probe."""
    db = get_db()
    if not db.is_connected():
        return {"status": "not ready", "reason": "database disconnected"}, 503
    return {"status": "ready"}
