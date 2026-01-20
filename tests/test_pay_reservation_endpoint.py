
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_reservation(code_key: str = "seed") -> str:
    payload = {
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
    res = client.post("/reservations", json=payload, headers={"Idempotency-Key": code_key})
    assert res.status_code == 201
    return res.json()["reservation_code"]


def _pay_payload():
    return {
        "payment_method_id": "pm_123",
        "billing_email": "jane@example.com",
        "billing_name": "Jane Roe",
        "save_payment_method": False,
    }


def test_pay_reservation_success():
    reservation_code = _create_reservation("pay-success")
    res = client.post(
        f"/reservations/{reservation_code}/pay",
        json=_pay_payload(),
        headers={"Idempotency-Key": "pay-k1"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["reservation_code"] == reservation_code
    assert body["payment_status"] == "PAID"
    assert body["payment"]["status"] == "CAPTURED"
    assert body["status"] == "ON_REQUEST"


def test_pay_reservation_idempotent_replay():
    reservation_code = _create_reservation("pay-replay")
    headers = {"Idempotency-Key": "pay-k2"}
    first = client.post(f"/reservations/{reservation_code}/pay", json=_pay_payload(), headers=headers)
    replay = client.post(f"/reservations/{reservation_code}/pay", json=_pay_payload(), headers=headers)
    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()


def test_pay_reservation_conflict_on_payload_change():
    reservation_code = _create_reservation("pay-conflict")
    headers = {"Idempotency-Key": "pay-k3"}
    first = client.post(f"/reservations/{reservation_code}/pay", json=_pay_payload(), headers=headers)
    assert first.status_code == 200
    changed_payload = _pay_payload() | {"billing_name": "Another"}
    conflict = client.post(
        f"/reservations/{reservation_code}/pay", json=changed_payload, headers=headers
    )
    assert conflict.status_code == 409


def test_pay_reservation_requires_idempotency_key():
    reservation_code = _create_reservation("pay-missing-header")
    res = client.post(f"/reservations/{reservation_code}/pay", json=_pay_payload())
    assert res.status_code == 400
