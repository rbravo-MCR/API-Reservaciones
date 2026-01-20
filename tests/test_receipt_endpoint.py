from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_pay_and_confirm():
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
    res_create = client.post("/reservations", json=create_payload, headers={"Idempotency-Key": "rcpt1"})
    code = res_create.json()["reservation_code"]
    client.post(
        f"/reservations/{code}/pay",
        json={"payment_method_id": "pm_123"},
        headers={"Idempotency-Key": "rcpt1-pay"},
    )
    client.post(f"/workers/outbox/book-supplier/{code}", params={"idem_key": "rcpt1-sup"})
    return code


def test_receipt_happy_path():
    code = _create_pay_and_confirm()
    res = client.get(f"/reservations/{code}/receipt")
    assert res.status_code == 200
    body = res.json()
    assert body["reservation_code"] == code
    assert body["status"] == "CONFIRMED"
    assert body["supplier_reservation_code"]
    assert body["pricing"]["public_price_total"] == "350.00"
    assert body["payment"]["payment_status"] == "PAID"


def test_receipt_conflict_if_not_confirmed():
    # create only
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
    res_create = client.post("/reservations", json=create_payload, headers={"Idempotency-Key": "rcpt2"})
    code = res_create.json()["reservation_code"]
    res = client.get(f"/reservations/{code}/receipt")
    assert res.status_code == 409
