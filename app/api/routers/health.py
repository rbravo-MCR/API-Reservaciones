"""
Health check endpoints for monitoring and orchestration (K8s, Docker, etc.)

Provides multiple health check endpoints:
- /health: Basic liveness check (always returns 200)
- /health/db: Database connectivity check
- /health/ready: Readiness check (all dependencies healthy)
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Basic liveness probe.

    Returns 200 OK if the application is running.
    Used by K8s liveness probe to restart unhealthy pods.
    """
    return {"status": "ok", "service": "reservations-api"}


@router.get("/health/db")
async def health_check_db(session: AsyncSession = Depends(get_db_session)):
    """
    Database connectivity health check.

    Tests if the database is reachable and accepting queries.
    Returns 503 Service Unavailable if database is down.
    """
    try:
        # Simple query to verify database connectivity
        result = await session.execute(text("SELECT 1"))
        result.scalar()

        return {"status": "healthy", "component": "database"}
    except Exception as e:
        logger.error("Database health check failed", exc_info=e)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "component": "database",
                "error": "Database connection failed"
            }
        )


@router.get("/health/ready")
async def health_check_ready(session: AsyncSession = Depends(get_db_session)):
    """
    Readiness probe for K8s/orchestration.

    Checks if the application is ready to accept traffic.
    - Database connectivity
    - Application initialized

    Returns 503 if not ready to accept requests.
    Used by K8s readiness probe to control traffic routing.
    """
    health_status = {
        "status": "ready",
        "checks": {}
    }

    # Check database connectivity
    try:
        result = await session.execute(text("SELECT 1"))
        result.scalar()
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        logger.error("Readiness check: Database unhealthy", exc_info=e)
        health_status["status"] = "not_ready"
        health_status["checks"]["database"] = "unhealthy"

        return JSONResponse(
            status_code=503,
            content=health_status
        )

    # All checks passed
    return health_status


@router.get("/health/live")
async def health_check_live():
    """
    Alias for /health for Kubernetes liveness probe.

    Some orchestrators prefer /health/live naming convention.
    """
    return {"status": "ok", "service": "reservations-api"}
