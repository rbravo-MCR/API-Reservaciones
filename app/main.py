import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.deps import engine
from app.api.routers.health import router as health_router
from app.api.routers.reservations import router as reservations_router
from app.api.routers.worker import router as worker_router
from app.infrastructure.db.tables import metadata

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables (for dev/demo purposes)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield
    # Cleanup
    await engine.dispose()

app = FastAPI(
    title="Reservations API",
    version="0.1.0",
    lifespan=lifespan
)


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler to prevent stack trace exposure to clients.
    All unhandled exceptions are logged internally and return a generic error message.
    """
    error_id = str(uuid.uuid4())

    # Log the full error with context for internal debugging
    logger.error(
        "Unhandled exception occurred",
        exc_info=exc,
        extra={
            "error_id": error_id,
            "path": request.url.path,
            "method": request.method,
            "client_host": request.client.host if request.client else None,
        }
    )

    # Return a generic error to the client without exposing internal details
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_id": error_id,
            "message": "An unexpected error occurred. Please contact support with the error_id if the issue persists."
        }
    )


app.include_router(health_router, tags=["Health"])
app.include_router(reservations_router, prefix="/api/v1", tags=["Reservations"])
app.include_router(worker_router, prefix="/api/v1", tags=["Worker"])
