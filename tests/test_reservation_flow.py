import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402


async def test_reservation_end_to_end():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        
        # --- 1. Validar datos de entrada (Input Validation) ---
        print("\n1. Validando datos de entrada...")
        invalid_payload = {
            "supplier_id": 1,
            "country_code": "MX",
            "pickup_office_id": 1,
            "dropoff_office_id": 1,
            "car_category_id": 1,
            "pickup_datetime": (
                datetime.now(timezone.utc) - timedelta(days=1)
            ).isoformat(),  # Past date
            "dropoff_datetime": datetime.now(timezone.utc).isoformat(),
            "rental_days": 0,  # Invalid days
            "currency_code": "USD",
            "public_price_total": "100.00",
            "supplier_cost_total": "80.00",
            "booking_device": "DESKTOP",
            "sales_channel_id": 1,
            "customer_ip": "127.0.0.1",
            "customer_user_agent": "Pytest",
            "contacts": [], # Missing contacts
            "drivers": [] # Missing drivers
        }
        resp = await ac.post(
            "/api/v1/reservations",
            json=invalid_payload,
            headers={"Idempotency-Key": "invalid-1"},
        )
        assert resp.status_code == 422
        print("✅ Validación de entrada falló correctamente (422 Unprocessable Entity)")

        # --- 2. Validar el Proceso de reserva (Reservation Intent) ---
        print("\n2. Validando proceso de reserva (Creación de Intento)...")
        pickup_dt = datetime.now(timezone.utc) + timedelta(days=5)
        dropoff_dt = pickup_dt + timedelta(days=3)
        
        valid_payload = {
            "supplier_id": 1,
            "country_code": "MX",
            "pickup_office_id": 1,
            "dropoff_office_id": 1,
            "car_category_id": 1,
            "acriss_code": "ECMN",
            "pickup_datetime": pickup_dt.isoformat(),
            "dropoff_datetime": dropoff_dt.isoformat(),
            "rental_days": 3,
            "currency_code": "USD",
            "public_price_total": "150.00",
            "supplier_cost_total": "100.00",
            "booking_device": "DESKTOP",
            "sales_channel_id": 1,
            "customer_ip": "127.0.0.1",
            "customer_user_agent": "Pytest",
            "contacts": [
                {
                    "contact_type": "BOOKER",
                    "full_name": "Juan Perez",
                    "email": "juan@example.com",
                    "phone": "123456",
                }
            ],
            "drivers": [
                {
                    "is_primary_driver": True,
                    "first_name": "Juan",
                    "last_name": "Perez",
                    "email": "juan@example.com",
                    "phone": "123456",
                    "date_of_birth": "1990-01-01",
                    "driver_license_number": "ABC12345"
                }
            ]
        }
        idem_key = f"e2e-{random.randint(1000, 9999)}"
        resp = await ac.post(
            "/api/v1/reservations", json=valid_payload, headers={"Idempotency-Key": idem_key}
        )
        assert resp.status_code == 201
        data = resp.json()
        reservation_code = data["reservation_code"]
        assert reservation_code.startswith("RES-")
        assert data["status"] == "PENDING"
        print(f"✅ Reserva creada exitosamente: {reservation_code}")

        # --- 2.5. Pagar la reserva (Pay Reservation) ---
        print("\n2.5. Pagando la reserva...")
        pay_payload = {
            "payment_method_id": "pm_card_visa",
            "billing_email": "juan@example.com",
            "billing_name": "Juan Perez"
        }
        pay_idem_key = f"pay-{random.randint(1000, 9999)}"
        resp = await ac.post(
            f"/api/v1/reservations/{reservation_code}/pay",
            json=pay_payload,
            headers={"Idempotency-Key": pay_idem_key},
        )
        if resp.status_code != 200:
            print(f"❌ Pago falló: {resp.text}")
        assert resp.status_code == 200
        payment_data = resp.json()
        print("✅ Pago procesado exitosamente")
        
        # Extract payment intent id for webhook
        # The PayReservationUseCase returns payment summary with stripe_payment_intent_id
        real_payment_intent_id = payment_data["payment"]["stripe_payment_intent_id"]

        # --- 3. Validar cobro (Payment Validation via Webhook) ---
        print("\n3. Validando cobro (Stripe Webhook)...")
        # payment_id variable was used in previous code, let's use the real one
        payment_id = real_payment_intent_id
        webhook_payload = {
            "id": f"evt_{random.randint(1000, 9999)}",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": payment_id,
                    "metadata": {"reservation_code": reservation_code}
                }
            }
        }
        resp = await ac.post("/api/v1/webhooks/stripe", json=webhook_payload)
        if resp.status_code != 200:
            print(f"❌ Webhook failed with status {resp.status_code}: {resp.text}")
        assert resp.status_code == 200
        print("✅ Webhook de pago procesado exitosamente")

        # --- 4. Respuesta al usuario final (Receipt) ---
        print("\n4. Validando respuesta al usuario final (Recibo)...")
        
        # First, we need to simulate the worker confirming the reservation
        # In a real scenario, the worker runs asynchronously. Here we trigger it manually.
        worker_resp = await ac.post(
            f"/api/v1/workers/outbox/book-supplier/{reservation_code}?idem_key=worker-{idem_key}"
        )
        assert worker_resp.status_code == 200
        assert worker_resp.json()["status"] == "CONFIRMED"
        print("✅ Proveedor confirmó la reserva (Simulado por Worker)")

        # Now get the receipt
        resp = await ac.get(f"/api/v1/reservations/{reservation_code}/receipt")
        assert resp.status_code == 200
        receipt = resp.json()
        assert receipt["reservation_code"] == reservation_code
        assert receipt["status"] == "CONFIRMED"
        assert receipt["payment"]["payment_status"] == "PAID"
        assert receipt["supplier_reservation_code"] is not None
        print("✅ Recibo generado correctamente para el usuario final")
        print(f"   Código de Confirmación del Proveedor: {receipt['supplier_reservation_code']}")

if __name__ == "__main__":
    asyncio.run(test_reservation_end_to_end())
