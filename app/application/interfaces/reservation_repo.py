from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from app.domain.constants import (
    PAYMENT_STATUS_UNPAID,
    RESERVATION_STATUS_PENDING,
)


@dataclass
class ContactInput:
    contact_type: str
    full_name: str
    email: str
    phone: str | None


@dataclass
class DriverInput:
    is_primary_driver: bool
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    date_of_birth: str | None
    driver_license_number: str | None


@dataclass
class ReservationInput:
    reservation_code: str
    supplier_id: int
    country_code: str
    pickup_office_id: int
    dropoff_office_id: int
    car_category_id: int
    pickup_datetime: str
    dropoff_datetime: str
    rental_days: int
    currency_code: str
    public_price_total: Decimal
    supplier_cost_total: Decimal
    taxes_total: Decimal
    fees_total: Decimal
    discount_total: Decimal
    commission_total: Decimal
    cashback_earned_amount: Decimal
    booking_device: str
    sales_channel_id: int
    customer_ip: str
    customer_user_agent: str
    pickup_office_code: str | None = None
    dropoff_office_code: str | None = None
    supplier_car_product_id: int | None = None
    acriss_code: str | None = None
    traffic_source_id: int | None = None
    marketing_campaign_id: int | None = None
    affiliate_id: int | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_term: str | None = None
    utm_content: str | None = None
    reservation_id: int | None = None
    status: str = RESERVATION_STATUS_PENDING
    payment_status: str = PAYMENT_STATUS_UNPAID
    supplier_reservation_code: str | None = None
    supplier_confirmed_at: str | None = None
    lock_version: int = 0


class ReservationRepo:
    async def get_by_code(self, reservation_code: str) -> ReservationInput | None:
        raise NotImplementedError

    async def create_reservation(
        self,
        reservation: ReservationInput,
        contacts: Sequence[ContactInput],
        drivers: Sequence[DriverInput],
    ) -> None:
        raise NotImplementedError

    async def update_payment_status(
        self,
        reservation_code: str,
        payment_status: str,
        expected_lock_version: int | None = None,
    ) -> None:
        raise NotImplementedError

    async def update_status(
        self,
        reservation_code: str,
        status: str,
        expected_lock_version: int | None = None,
    ) -> None:
        raise NotImplementedError

    async def mark_confirmed(
        self,
        reservation_code: str,
        supplier_reservation_code: str,
        supplier_confirmed_at: str,
        expected_lock_version: int | None = None,
    ) -> None:
        raise NotImplementedError
