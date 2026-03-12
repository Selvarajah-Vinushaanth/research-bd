# ============================================
# Database - Prisma Client Manager
# ============================================

from __future__ import annotations

import structlog
from prisma import Prisma

logger = structlog.get_logger()

# Global Prisma client instance
db = Prisma()


async def prisma_connect() -> None:
    """Connect to the database via Prisma."""
    try:
        await db.connect()
        logger.info("prisma_connected", status="success")
    except Exception as e:
        logger.error("prisma_connection_failed", error=str(e))
        raise


async def prisma_disconnect() -> None:
    """Disconnect from the database."""
    try:
        if db.is_connected():
            await db.disconnect()
            logger.info("prisma_disconnected", status="success")
    except Exception as e:
        logger.error("prisma_disconnect_failed", error=str(e))


def get_db() -> Prisma:
    """Get the Prisma client instance."""
    return db
