from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, condecimal, constr, field_validator

Money = condecimal(max_digits=12, decimal_places=2)


class BookingDevice(str, Enum):
    DESKTOP = "DESKTOP"
    MOBILE_WEB = "MOBILE_WEB"
    IOS_APP = "IOS_APP"
    ANDROID_APP = "ANDROID_APP"
    CALL_CENTER = "CALL_CENTER"


class ContactType(str, Enum):
    BOOKER = "BOOKER"
    EMERGENCY = "EMERGENCY"


class Contact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_type: ContactType = Field(default=ContactType.BOOKER)
    full_name: str
    email: EmailStr
    phone: str | None = None


class Driver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_primary_driver: bool = True
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    driver_license_number: str | None = None


class CreateReservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: int
    country_code: constr(strip_whitespace=True, min_length=2, max_length=3)
    pickup_office_id: int
    dropoff_office_id: int
    pickup_office_code: str | None = None
    dropoff_office_code: str | None = None
    car_category_id: int
    supplier_car_product_id: int | None = None
    acriss_code: constr(strip_whitespace=True, min_length=1, max_length=10) | None = None
    pickup_datetime: datetime
    dropoff_datetime: datetime
    rental_days: int
    currency_code: constr(strip_whitespace=True, min_length=3, max_length=3)
    public_price_total: Money
    supplier_cost_total: Money
    taxes_total: Money = Field(default=Decimal("0"))
    fees_total: Money = Field(default=Decimal("0"))
    discount_total: Money = Field(default=Decimal("0"))
    commission_total: Money = Field(default=Decimal("0"))
    cashback_earned_amount: Money = Field(default=Decimal("0"))
    booking_device: BookingDevice
    sales_channel_id: int
    traffic_source_id: int | None = None
    marketing_campaign_id: int | None = None
    affiliate_id: int | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_term: str | None = None
    utm_content: str | None = None
    customer_ip: str
    customer_user_agent: str
    contacts: list[Contact]
    drivers: list[Driver]

    @field_validator("rental_days")
    @classmethod
    def validate_rental_days(cls, value: int) -> int:
        if value < 1:
            raise ValueError("rental_days must be >= 1")
        return value

    @field_validator("dropoff_datetime")
    @classmethod
    def validate_dates(cls, value: datetime, info: Any) -> datetime:
        pickup = info.data.get("pickup_datetime")
        if pickup and value <= pickup:
            raise ValueError("dropoff_datetime must be after pickup_datetime")
        return value

    @field_validator("drivers")
    @classmethod
    def validate_drivers(cls, value: list[Driver]) -> list[Driver]:
        if not value:
            raise ValueError("At least one driver is required")
        primaries = [driver for driver in value if driver.is_primary_driver]
        if not primaries:
            raise ValueError("A primary driver is required")
        if len(primaries) > 1:
            raise ValueError("Only one primary driver is allowed")
        return value


class CreateReservationResponse(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: lambda v: format(v, ".2f")})

    reservation_code: str
    status: str
    payment_status: str
    public_price_total: Money
    currency_code: constr(strip_whitespace=True, min_length=3, max_length=3)


class PayReservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_method_id: str
    billing_email: EmailStr | None = None
    billing_name: str | None = None
    save_payment_method: bool = False


class PaymentSummary(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: lambda v: format(v, ".2f")})

    id: int | None = None
    provider: str = "stripe"
    status: str
    stripe_payment_intent_id: str | None = None
    stripe_charge_id: str | None = None
    amount: Money
    currency_code: constr(strip_whitespace=True, min_length=3, max_length=3)


class SupplierRequestSummary(BaseModel):
    created: bool | None = None
    status: str | None = None


class PayReservationResponse(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: lambda v: format(v, ".2f")})

    reservation_code: str
    status: str
    payment_status: str
    payment: PaymentSummary
    supplier_request: SupplierRequestSummary | None = None


class StripeWebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    livemode: bool | None = None
    created: int | None = None


class OfficeSnapshot(BaseModel):
    office_id: int
    code: str | None = None
    name: str | None = None
    datetime: datetime


class VehicleSnapshot(BaseModel):
    car_category_id: int
    acriss_code: str | None = None
    supplier_car_product_id: int | None = None


class PricingSnapshot(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: lambda v: format(v, ".2f")})

    public_price_total: Money
    taxes_total: Money
    fees_total: Money
    discount_total: Money
    commission_total: Money
    supplier_cost_total: Money
    currency_code: constr(strip_whitespace=True, min_length=3, max_length=3)


class ReceiptPayment(BaseModel):
    payment_status: str
    provider: str
    brand: str | None = None
    last4: str | None = None


class SupplierSnapshot(BaseModel):
    id: int
    name: str | None = None


class ReceiptResponse(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: lambda v: format(v, ".2f")})

    reservation_code: str
    status: str
    supplier_reservation_code: str
    pickup: OfficeSnapshot
    dropoff: OfficeSnapshot
    vehicle: VehicleSnapshot
    contacts: list[Contact]
    drivers: list[Driver]
    pricing: PricingSnapshot
    payment: ReceiptPayment
    supplier: SupplierSnapshot
    created_at: datetime
    supplier_confirmed_at: datetime
