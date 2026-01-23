import asyncio
import json
import sys
import uuid
from decimal import Decimal
from datetime import datetime

# Añadir el root al path para poder importar la app
import os
sys.path.append(os.getcwd())

from app.api.dependencies import get_use_cases, get_settings
from app.api.deps import AsyncSessionLocal
from app.api.schemas.reservations import CreateReservationRequest, PayReservationRequest, BookingDevice
from app.domain.entities.reservation import ReservationStatus
from sqlalchemy import text

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError

async def show_evidence():
    settings = get_settings()
    print(f"--- CONFIGURACIÓN ---")
    print(f"Database: {settings.database_url}")
    print(f"Use In-Memory: {settings.use_in_memory}")
    print("-" * 50)

    # Generar ID único para esta prueba
    test_id = f"EVID-{uuid.uuid4().hex[:6].upper()}"
    res_code = None

    # 1. Crear Reserva
    print(f"\n[PASO 1] Frontend envía POST /api/v1/reservations")
    async with AsyncSessionLocal() as session:
        use_cases = get_use_cases(settings=settings, session=session)
        idem_key_create = f"idem-create-{test_id}"
        
        payload = {
            "supplier_id": 1,
            "country_code": "MX",
            "pickup_office_id": 1,
            "dropoff_office_id": 1,
            "car_category_id": 1,
            "acriss_code": "ECMN",
            "pickup_datetime": "2026-03-01T10:00:00",
            "dropoff_datetime": "2026-03-05T10:00:00",
            "rental_days": 4,
            "currency_code": "USD",
            "public_price_total": Decimal("150.00"),
            "supplier_cost_total": Decimal("100.00"),
            "taxes_total": Decimal("20.00"),
            "fees_total": Decimal("10.00"),
            "booking_device": BookingDevice.DESKTOP,
            "sales_channel_id": 1,
            "customer_ip": "127.0.0.1",
            "customer_user_agent": "Mozilla/5.0",
            "contacts": [{"contact_type": "BOOKER", "full_name": "Demo User", "email": "demo@example.com"}],
            "drivers": [{"is_primary_driver": True, "first_name": "Demo", "last_name": "Tester", "email": "demo@example.com"}]
        }
        
        request_obj = CreateReservationRequest(**payload)
        response_create = await use_cases["create_reservation"].execute(request_obj, idem_key=idem_key_create)
        res_code = response_create.reservation_code
        
        # COMMIT explícito para asegurar persistencia fuera del use case si fuera necesario
        await session.commit()
        
        print(f"\n<<< RESPUESTA AL FRONTEND (JSON):")
        print(json.dumps(response_create.model_dump(), indent=2, default=decimal_default))

    # 2. Pagar
    print(f"\n[PASO 2] Frontend envía POST /api/v1/reservations/{res_code}/pay")
    async with AsyncSessionLocal() as session:
        use_cases = get_use_cases(settings=settings, session=session)
        idem_key_pay = f"idem-pay-{test_id}"
        
        pay_payload = {
            "payment_method_id": "pm_card_visa",
            "billing_email": "demo@example.com",
            "billing_name": "Demo Tester"
        }
        
        pay_request_obj = PayReservationRequest(**pay_payload)
        response_pay = await use_cases["pay_reservation"].execute(
            reservation_code=res_code,
            request=pay_request_obj,
            idem_key=idem_key_pay
        )
        
        await session.commit()
        
        print(f"\n<<< RESPUESTA AL FRONTEND (JSON):")
        print(json.dumps(response_pay.model_dump(), indent=2, default=decimal_default))

    # 3. Verificación Final
    print(f"\n[PASO 3] Verificación final de persistencia...")
    async with AsyncSessionLocal() as session:
        res = await session.execute(text(
            "SELECT reservation_code, status, payment_status FROM reservations WHERE reservation_code = :code"
        ), {"code": res_code})
        row = res.fetchone()
        print(f"DB FINAL STATE -> Code: {row[0]}, Status: {row[1]}, Payment: {row[2]}")
        
        pay_count = await session.execute(text("SELECT count(*) FROM payments WHERE reservation_code = :code"), {"code": res_code})
        print(f"DB PAYMENTS -> Registros: {pay_count.scalar()}")

    print(f"\n--- PRUEBA FINALIZADA Y PERSISTIDA ---")

if __name__ == "__main__":
    asyncio.run(show_evidence())