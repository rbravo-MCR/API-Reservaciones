from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import engine
from app.api.routers.reservations import router as reservations_router
from app.api.routers.worker import router as worker_router
from app.infrastructure.db.tables import metadata


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

app.include_router(reservations_router, prefix="/api/v1", tags=["Reservations"])
app.include_router(worker_router, prefix="/api/v1", tags=["Worker"])

@app.get("/health")
def health_check():
    return {"status": "ok"}
