
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _base_payload():
    return {
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


def test_create_reservation_success():
    payload = _base_payload()
    headers = {"Idempotency-Key": "k1"}

    res = client.post("/reservations", json=payload, headers=headers)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "PENDING"
    assert body["payment_status"] == "UNPAID"
    assert body["public_price_total"] == "350.00"
    assert body["currency_code"] == "USD"


def test_create_reservation_idempotent_replay():
    payload = _base_payload()
    headers = {"Idempotency-Key": "k2"}

    first = client.post("/reservations", json=payload, headers=headers)
    assert first.status_code == 201
    replay = client.post("/reservations", json=payload, headers=headers)
    assert replay.status_code == 201
    assert first.json() == replay.json()


def test_create_reservation_idempotent_conflict_on_different_payload():
    payload = _base_payload()
    headers = {"Idempotency-Key": "k3"}
    first = client.post("/reservations", json=payload, headers=headers)
    assert first.status_code == 201

    modified = payload.copy()
    modified["public_price_total"] = "351.00"
    conflict = client.post("/reservations", json=modified, headers=headers)
    assert conflict.status_code == 409
    assert "Idempotency conflict" in conflict.json()["detail"]


def test_create_reservation_requires_idempotency_key():
    res = client.post("/reservations", json=_base_payload())
    assert res.status_code == 400
    assert "Idempotency-Key" in res.json()["detail"]
