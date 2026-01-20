import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.api.deps import engine  # noqa: E402
from app.application.use_cases.process_outbox import ProcessOutboxUseCase  # noqa: E402
from app.infrastructure.db.base import Base  # noqa: E402
from app.infrastructure.db.models import (  # noqa: E402
    OutboxEventModel,
    OutboxStatus,
    ReservationModel,
    ReservationStatus,
)
from app.infrastructure.db.repository import ReservationRepository  # noqa: E402


async def test_fallback_strategy():
    # Initialize tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    
    async with SessionLocal() as session:
        # 1. Setup: Create PAID Reservation and PENDING Event
        print("Setting up test data for Fallback...")
        res = ReservationModel(
            reservation_code="FALLBACK",
            supplier_id="hertz",
            total_amount=Decimal("200.00"),
            customer_email="fallback@test.com",
            customer_data={},
            status=ReservationStatus.PAID
        )
        session.add(res)
        
        event = OutboxEventModel(
            type="CONFIRM_SUPPLIER",
            payload={"reservation_code": "FALLBACK"},
            status=OutboxStatus.PENDING
        )
        session.add(event)
        await session.commit()
        
        # 2. Run Worker with FAILING Mock
        print("Running ProcessOutboxUseCase with Failing Mock...")
        repository = ReservationRepository(session)
        
        # Mock Gateway that raises Exception
        mock_gateway = AsyncMock()
        mock_gateway.confirm_booking.side_effect = Exception("Supplier Timeout")
        
        use_case = ProcessOutboxUseCase(repository, mock_gateway)
        
        await use_case.execute()
        await session.commit()
        
        # 3. Verify Fallback
        await session.refresh(res)
        await session.refresh(event)
        
        print(f"Reservation Status: {res.status}")
        print(f"Event Status: {event.status}")
        print(f"Retry Count: {event.retry_count}")
        
        assert res.status == ReservationStatus.CONFIRMED_INTERNAL
        assert event.status == OutboxStatus.PENDING # Still pending for retry
        assert event.retry_count == 1

    print("\nSUCCESS: Fallback Strategy verified.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_fallback_strategy())
