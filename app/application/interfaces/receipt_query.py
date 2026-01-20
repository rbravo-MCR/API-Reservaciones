from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class ReceiptContact:
    contact_type: str
    full_name: str
    email: str
    phone: str | None


@dataclass
class ReceiptDriver:
    is_primary_driver: bool
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    date_of_birth: str | None
    driver_license_number: str | None


@dataclass
class ReceiptPayment:
    payment_status: str
    provider: str
    brand: str | None
    last4: str | None


@dataclass
class ReceiptData:
    reservation_code: str
    status: str
    supplier_reservation_code: str
    pickup_office_id: int
    pickup_office_code: str | None
    pickup_office_name: str | None
    pickup_datetime: datetime
    dropoff_office_id: int
    dropoff_office_code: str | None
    dropoff_office_name: str | None
    dropoff_datetime: datetime
    car_category_id: int
    acriss_code: str | None
    supplier_car_product_id: int | None
    contacts: list[ReceiptContact]
    drivers: list[ReceiptDriver]
    public_price_total: Decimal
    taxes_total: Decimal
    fees_total: Decimal
    discount_total: Decimal
    commission_total: Decimal
    supplier_cost_total: Decimal
    currency_code: str
    payment: ReceiptPayment
    supplier_id: int
    supplier_name: str | None
    created_at: datetime
    supplier_confirmed_at: datetime


class ReceiptQuery:
    async def get_receipt(self, reservation_code: str) -> ReceiptData | None:
        raise NotImplementedError
