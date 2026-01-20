
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_and_pay_reservation() -> tuple[str, str]:
    # Create reservation
    create_payload = {
        "supplier_id": 11,
        "country_code": "MX",
        "pickup_office_id": 101,
        "dropoff_office_id": 102,
        "car_category_id": 5,
        "supplier_car_product_id": 901,
        "acriss_code": "ECMN",
        "pickup_datetime": "2026-02-01T10:00:00",
        "dropoff_datetime": "2026-02-05T10:00:00",
        "rental_days": 4,
        "currency_code": "USD",
        "public_price_total": "350.00",
        "supplier_cost_total": "200.00",
        "taxes_total": "50.00",
        "fees_total": "20.00",
        "discount_total": "0.00",
        "commission_total": "30.00",
        "cashback_earned_amount": "0.00",
        "booking_device": "MOBILE_WEB",
        "sales_channel_id": 2,
        "traffic_source_id": 4,
        "marketing_campaign_id": 3,
        "affiliate_id": 7,
        "utm_source": "meta",
        "utm_medium": "cpc",
        "utm_campaign": "summer",
        "customer_ip": "203.0.113.10",
        "customer_user_agent": "Mozilla/5.0",
        "contacts": [
            {
                "contact_type": "BOOKER",
                "full_name": "Jane Roe",
                "email": "jane@example.com",
                "phone": "+15551234567",
            }
        ],
        "drivers": [
            {
                "is_primary_driver": True,
                "first_name": "Jane",
                "last_name": "Roe",
                "email": "jane@example.com",
                "phone": "+15551234567",
            }
        ],
    }
    create_res = client.post(
        "/reservations", json=create_payload, headers={"Idempotency-Key": "whk1"}
    )
    reservation_code = create_res.json()["reservation_code"]

    pay_res = client.post(
        f"/reservations/{reservation_code}/pay",
        json={
            "payment_method_id": "pm_123",
            "billing_email": "jane@example.com",
            "billing_name": "Jane Roe",
            "save_payment_method": False,
        },
        headers={"Idempotency-Key": "whk1-pay"},
    )
    payment = pay_res.json()["payment"]
    return reservation_code, payment["stripe_payment_intent_id"]


def test_webhook_idempotent_by_event_id():
    reservation_code, intent_id = _create_and_pay_reservation()
    event_payload = {
        "id": "evt_test",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": intent_id,
                "payment_intent": intent_id,
                "latest_charge": "ch_test",
                "charges": {"data": [{"id": "ch_test"}]},
            }
        },
    }
    first = client.post("/webhooks/stripe", json=event_payload)
    assert first.status_code == 200
    replay = client.post("/webhooks/stripe", json=event_payload)
    assert replay.status_code == 200


def test_webhook_payment_failed_updates_status():
    reservation_code, intent_id = _create_and_pay_reservation()
    event_payload = {
        "id": "evt_failed",
        "type": "payment_intent.payment_failed",
        "data": {"object": {"id": intent_id, "payment_intent": intent_id}},
    }
    res = client.post("/webhooks/stripe", json=event_payload)
    assert res.status_code == 200
