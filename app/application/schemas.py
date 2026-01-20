from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class CustomerData(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone: str

class CreateReservationRequest(BaseModel):
    quote_id: str
    customer: CustomerData
    supplier_id: int
    pickup_office_id: int
    dropoff_office_id: int
    car_category_id: int
    sales_channel_id: int
    pickup_datetime: datetime
    dropoff_datetime: datetime
    
    # Simplified for this slice, assuming amount comes from quote or is calculated
    total_amount: Decimal = Field(..., gt=0)
    currency: str = "USD"

class CreateReservationResponse(BaseModel):
    reservation_code: str
    status: str
    payment_client_secret: str | None
    total_amount: Decimal
    currency: str
    expires_at: datetime | None = None

class ReservationReceiptResponse(BaseModel):
    reservation_code: str
    status: str
    customer_email: str
    customer_name: str
    pickup_datetime: datetime
    dropoff_datetime: datetime
    total_amount: Decimal
    currency: str
    payment_id: str | None = None
    payment_status: str | None = None
    supplier_confirmation_code: str | None = None
