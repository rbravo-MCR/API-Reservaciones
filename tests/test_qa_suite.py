import asyncio
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from app.api.deps import engine  # noqa: E402
from app.application.use_cases.process_outbox import ProcessOutboxUseCase  # noqa: E402
from app.infrastructure.db.models import (  # noqa: E402
    OutboxEventModel,
    ReservationStatus,
)
from app.infrastructure.db.repository import ReservationRepository  # noqa: E402
from app.infrastructure.gateways.factory import SupplierGatewayFactory  # noqa: E402
from app.main import app  # noqa: E402

# --- Helpers ---

async def create_outbox_table():
    from app.infrastructure.db.models import PaymentModel
    async with engine.begin() as conn:
        await conn.run_sync(OutboxEventModel.metadata.create_all)
        await conn.run_sync(PaymentModel.metadata.create_all)
        print("Ensured OutboxEventModel and PaymentModel tables exist.")

async def get_valid_ids(session):
    """Fetch valid IDs from the DB to satisfy Foreign Keys."""
    ids = {}
    
    # Supplier
    res = await session.execute(text("SELECT id FROM suppliers LIMIT 1"))
    ids["supplier_id"] = res.scalar()
    
    # Office (Pickup/Dropoff)
    res = await session.execute(text("SELECT id FROM offices LIMIT 1"))
    ids["office_id"] = res.scalar()
    
    # Car Category
    res = await session.execute(text("SELECT id FROM car_categories LIMIT 1"))
    ids["car_category_id"] = res.scalar()
    
    # Sales Channel
    res = await session.execute(text("SELECT id FROM sales_channels LIMIT 1"))
    ids["sales_channel_id"] = res.scalar()
    
    # Check if any is missing
    missing = [k for k, v in ids.items() if v is None]
    if missing:
        raise ValueError(f"Missing required data in DB for tests: {missing}. Please seed the DB.")
        
    return ids

async def create_reservation(ac: AsyncClient, email: str, valid_ids: dict) -> str:
    pickup_dt = datetime.now(timezone.utc) + timedelta(days=1)
    dropoff_dt = pickup_dt + timedelta(days=3)
    
    payload = {
        "quote_id": "q1",
        "customer": {"email": email, "first_name": "QA", "last_name": "Tester", "phone": "555"},
        "supplier_id": valid_ids["supplier_id"],
        "pickup_office_id": valid_ids["office_id"],
        "dropoff_office_id": valid_ids["office_id"],
        "car_category_id": valid_ids["car_category_id"],
        "sales_channel_id": valid_ids["sales_channel_id"],
        "pickup_datetime": pickup_dt.isoformat(),
        "dropoff_datetime": dropoff_dt.isoformat(),
        "total_amount": 100.00,
        "currency": "USD"
    }
    resp = await ac.post("/api/v1/reservations", json=payload)
    if resp.status_code != 201:
        print(f"Create Failed: {resp.text}")
    assert resp.status_code == 201
    return resp.json()["reservation_code"]

async def send_webhook(ac: AsyncClient, reservation_code: str, payment_id: str = None):
    if payment_id is None:
        payment_id = f"pi_{random.randint(10000,99999)}"
    payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": payment_id,
                "metadata": {"reservation_code": reservation_code}
            }
        }
    }
    return await ac.post(
        "/api/v1/webhooks/stripe",
        content=json.dumps(payload),
        headers={"stripe-signature": "test"}
    )

# --- Tests ---

async def test_happy_path(valid_ids):
    print("\n--- TC-001: Happy Path Integration ---")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"happy_{random.randint(1000,9999)}@qa.com"
        
        # 1. Create
        code = await create_reservation(ac, email, valid_ids)
        print(f"1. Reservation Created: {code}")
        
        # 2. Webhook
        resp = await send_webhook(ac, code)
        if resp.status_code != 200:
            with open("error.log", "w") as f:
                f.write(f"Webhook Failed: {resp.text}")
        assert resp.status_code == 200
        print("2. Webhook Received (PAID)")
        
        # 3. Worker
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
        async with SessionLocal() as session:
            repo = ReservationRepository(session)
            factory = SupplierGatewayFactory({"mock": {}})
            use_case = ProcessOutboxUseCase(repo, factory)
            
            count = await use_case.execute()
            await session.commit()
            print(f"3. Worker Processed {count} events")
            
            # Verify
            res = await repo.get_by_code(code)
            assert res.status == ReservationStatus.CONFIRMED
            assert res.supplier_reservation_code is not None
            print(
                f"4. Verified Status: {res.status}, "
                f"SupplierCode: {res.supplier_reservation_code}"
            )

async def test_idempotency(valid_ids):
    print("\n--- TC-002: Webhook Idempotency ---")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"idem_{random.randint(1000,9999)}@qa.com"
        code = await create_reservation(ac, email, valid_ids)
        
        # Send Webhook Twice with SAME payment_id
        payment_id = f"pi_idem_{random.randint(1000,9999)}"
        resp1 = await send_webhook(ac, code, payment_id=payment_id)
        resp2 = await send_webhook(ac, code, payment_id=payment_id)
        
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        print("Sent Webhook twice with same ID, both 200 OK")
        
        # Check DB
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
        async with SessionLocal() as session:
            stmt = select(OutboxEventModel).order_by(OutboxEventModel.id.desc()).limit(50)
            events = (await session.execute(stmt)).scalars().all()
            target_events = [e for e in events if e.payload.get("reservation_code") == code]
            
            print(f"Outbox Events found: {len(target_events)}")
            if len(target_events) > 1:
                print("⚠️  FAIL: Idempotency not enforced! Duplicate events created.")
            else:
                print("✅ PASS: Idempotency enforced.")

async def test_concurrency(valid_ids):
    print("\n--- TC-003: Concurrency (Race Condition) ---")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"race_{random.randint(1000,9999)}@qa.com"
        code = await create_reservation(ac, email, valid_ids)
        
        # Launch 5 concurrent webhooks with SAME payment_id
        payment_id = f"pi_race_{random.randint(1000,9999)}"
        print(f"Launching 5 concurrent webhooks with ID {payment_id}...")
        tasks = [send_webhook(ac, code, payment_id=payment_id) for _ in range(5)]
        responses = await asyncio.gather(*tasks)
        
        for r in responses:
            assert r.status_code == 200
            
        # Check Results
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
        async with SessionLocal() as session:
            stmt = select(OutboxEventModel).order_by(OutboxEventModel.id.desc()).limit(50)
            events = (await session.execute(stmt)).scalars().all()
            target_events = [e for e in events if e.payload.get("reservation_code") == code]
            
            print(f"Concurrent Webhooks sent. Outbox Events created: {len(target_events)}")
            if len(target_events) > 1:
                 print("⚠️  FAIL: Race condition detected! Multiple events.")
            else:
                 print("✅ PASS: Concurrency handled safely.")

async def main():
    # Ensure Outbox Table Exists
    try:
        await create_outbox_table()
    except Exception as e:
        print(f"⚠️ Could not create outbox table: {e}")

    # Fetch Valid IDs first
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        try:
            valid_ids = await get_valid_ids(session)
            print(f"Using Valid IDs: {valid_ids}")
        except Exception as e:
            print(f"❌ Setup Failed: {e}")
            return

    await test_happy_path(valid_ids)
    await test_idempotency(valid_ids)
    await test_concurrency(valid_ids)
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
