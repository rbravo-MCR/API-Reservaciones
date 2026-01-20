from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.api.schemas.reservations import CreateReservationRequest, ReceiptResponse


@pytest.fixture()
def base_request_payload():
    return {
        "supplier_id": 11,
        "country_code": "MX",
        "pickup_office_id": 101,
        "dropoff_office_id": 102,
        "car_category_id": 5,
        "supplier_car_product_id": 901,
        "acriss_code": "ECMN",
        "pickup_datetime": datetime(2026, 2, 1, 10, 0, 0),
        "dropoff_datetime": datetime(2026, 2, 5, 10, 0, 0),
        "rental_days": 4,
        "currency_code": "USD",
        "public_price_total": Decimal("350.00"),
        "supplier_cost_total": Decimal("200.00"),
        "taxes_total": Decimal("50.00"),
        "fees_total": Decimal("20.00"),
        "discount_total": Decimal("0.00"),
        "commission_total": Decimal("30.00"),
        "cashback_earned_amount": Decimal("0.00"),
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
                "date_of_birth": datetime(1990, 1, 1).date(),
                "driver_license_number": "X12345",
            }
        ],
    }


def test_create_reservation_request_valid(base_request_payload):
    req = CreateReservationRequest(**base_request_payload)
    assert req.rental_days == 4
    assert req.drivers[0].is_primary_driver is True
    assert req.booking_device == "MOBILE_WEB"


def test_create_reservation_request_rejects_invalid_dates(base_request_payload):
    bad_payload = base_request_payload | {
        "dropoff_datetime": base_request_payload["pickup_datetime"] - timedelta(hours=1)
    }
    with pytest.raises(ValueError):
        CreateReservationRequest(**bad_payload)


def test_receipt_response_serialization():
    response = ReceiptResponse(
        reservation_code="RES-ABC123",
        status="CONFIRMED",
        supplier_reservation_code="SUP-789",
        pickup={
            "office_id": 101,
            "code": "MIA1",
            "name": "Miami Airport",
            "datetime": datetime.now(),
        },
        dropoff={
            "office_id": 102,
            "code": "MIA2",
            "name": "Miami Downtown",
            "datetime": datetime.now(),
        },
        vehicle={"car_category_id": 5, "acriss_code": "ECMN", "supplier_car_product_id": 901},
        contacts=[{"contact_type": "BOOKER", "full_name": "Jane Roe", "email": "jane@example.com"}],
        drivers=[{"is_primary_driver": True, "first_name": "Jane", "last_name": "Roe"}],
        pricing={
            "public_price_total": Decimal("350.00"),
            "taxes_total": Decimal("50.00"),
            "fees_total": Decimal("20.00"),
            "discount_total": Decimal("0.00"),
            "commission_total": Decimal("30.00"),
            "supplier_cost_total": Decimal("200.00"),
            "currency_code": "USD",
        },
        payment={"payment_status": "PAID", "provider": "stripe", "brand": "visa", "last4": "4242"},
        supplier={"id": 11, "name": "Supplier Inc"},
        created_at=datetime.now(),
        supplier_confirmed_at=datetime.now(),
    )

    serialized = response.model_dump()
    assert serialized["status"] == "CONFIRMED"
    assert serialized["pricing"]["currency_code"] == "USD"
