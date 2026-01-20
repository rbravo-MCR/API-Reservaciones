import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.application.schemas import CreateReservationRequest, CreateReservationResponse
from app.infrastructure.db.models import ReservationModel, ReservationStatus
from app.infrastructure.db.repository import ReservationRepository


def generate_reservation_code(length: int = 8) -> str:
    """Generates a random alphanumeric code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

class CreateReservationUseCase:
    def __init__(self, repository: ReservationRepository):
        self.repository = repository

    async def execute(self, request: CreateReservationRequest) -> CreateReservationResponse:
        # 1. Generate unique code
        code = generate_reservation_code()
        
        # 2. Create Reservation Model (DRAFT)
        rental_days = (request.dropoff_datetime - request.pickup_datetime).days
        if rental_days < 1:
            rental_days = 1
            
        reservation = ReservationModel(
            reservation_code=code,
            supplier_id=request.supplier_id,
            pickup_office_id=request.pickup_office_id,
            dropoff_office_id=request.dropoff_office_id,
            car_category_id=request.car_category_id,
            sales_channel_id=request.sales_channel_id,
            pickup_datetime=request.pickup_datetime,
            dropoff_datetime=request.dropoff_datetime,
            rental_days=rental_days,
            public_price_total=request.total_amount,
            supplier_cost_total=request.total_amount * Decimal("0.8"), # Mock cost
            currency_code=request.currency,
            customer_email=request.customer.email,
            customer_name=f"{request.customer.first_name} {request.customer.last_name}",
            status=ReservationStatus.DRAFT
        )
        
        # 3. Persist Draft
        saved_reservation = await self.repository.create(reservation)
        
        # 4. Mock Stripe Payment Intent Creation
        # In real implementation, we would call Stripe API here
        payment_client_secret = f"pi_mock_{uuid.uuid4()}_secret_{uuid.uuid4()}"
        
        # 5. Update Status to PENDING_PAYMENT
        saved_reservation.status = ReservationStatus.PENDING_PAYMENT
        # We rely on the session commit in the controller/dependency to save this update
        
        return CreateReservationResponse(
            reservation_code=saved_reservation.reservation_code,
            status=saved_reservation.status.value,
            payment_client_secret=payment_client_secret,
            total_amount=saved_reservation.public_price_total,
            currency=saved_reservation.currency_code,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)
        )
