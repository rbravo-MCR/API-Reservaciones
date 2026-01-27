import hashlib
import json
from typing import Any, Callable

from fastapi import HTTPException, status

from app.api.schemas.reservations import (
    CreateReservationRequest,
    CreateReservationResponse,
)
from app.application.interfaces.idempotency_repo import (
    IdempotencyRecord,
    IdempotencyRepo,
)
from app.application.interfaces.reservation_repo import (
    ContactInput,
    DriverInput,
    ReservationInput,
    ReservationRepo,
)
from app.application.interfaces.transaction_manager import TransactionManager
from app.domain.constants import (
    PAYMENT_STATUS_UNPAID,
    RESERVATION_STATUS_PENDING,
)


def _hash_request(payload: dict[str, Any]) -> str:
    normalized = json.dumps(
        payload, sort_keys=True, default=str, separators=(",", ":")
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


class CreateReservationIntentUseCase:
    def __init__(
        self,
        reservation_repo: ReservationRepo,
        idempotency_repo: IdempotencyRepo,
        transaction_manager: TransactionManager,
        code_generator: Callable[[], str],
    ) -> None:
        self._reservation_repo = reservation_repo
        self._idempotency_repo = idempotency_repo
        self._transaction_manager = transaction_manager
        self._code_generator = code_generator

    async def execute(
        self,
        request: CreateReservationRequest,
        idem_key: str,
    ) -> CreateReservationResponse:
        scope = "RESERVATION_CREATE"
        request_hash = _hash_request(request.model_dump())

        async with self._transaction_manager.start():
            existing = await self._idempotency_repo.get(
                scope=scope, idem_key=idem_key
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Idempotency conflict: different payload "
                            "for same key"
                        ),
                    )
                return CreateReservationResponse.model_validate(
                    existing.response_json
                )

            reservation_code = self._code_generator()

            contacts = [
                ContactInput(
                    contact_type=contact.contact_type.value,
                    full_name=contact.full_name,
                    email=contact.email,
                    phone=contact.phone,
                )
                for contact in request.contacts
            ]
            drivers = [
                DriverInput(
                    is_primary_driver=driver.is_primary_driver,
                    first_name=driver.first_name,
                    last_name=driver.last_name,
                    email=driver.email,
                    phone=driver.phone,
                    date_of_birth=(
                        str(driver.date_of_birth)
                        if driver.date_of_birth
                        else None
                    ),
                    driver_license_number=driver.driver_license_number,
                )
                for driver in request.drivers
            ]
            reservation = ReservationInput(
                reservation_id=None,
                reservation_code=reservation_code,
                supplier_id=request.supplier_id,
                country_code=request.country_code,
                pickup_office_id=request.pickup_office_id,
                dropoff_office_id=request.dropoff_office_id,
                pickup_office_code=request.pickup_office_code,
                dropoff_office_code=request.dropoff_office_code,
                car_category_id=request.car_category_id,
                supplier_car_product_id=request.supplier_car_product_id,
                acriss_code=request.acriss_code,
                pickup_datetime=request.pickup_datetime.isoformat(),
                dropoff_datetime=request.dropoff_datetime.isoformat(),
                rental_days=request.rental_days,
                currency_code=request.currency_code,
                public_price_total=request.public_price_total,
                supplier_cost_total=request.supplier_cost_total,
                taxes_total=request.taxes_total,
                fees_total=request.fees_total,
                discount_total=request.discount_total,
                commission_total=request.commission_total,
                cashback_earned_amount=request.cashback_earned_amount,
                booking_device=request.booking_device.value,
                sales_channel_id=request.sales_channel_id,
                traffic_source_id=request.traffic_source_id,
                marketing_campaign_id=request.marketing_campaign_id,
                affiliate_id=request.affiliate_id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
                utm_term=request.utm_term,
                utm_content=request.utm_content,
                customer_ip=request.customer_ip,
                customer_user_agent=request.customer_user_agent,
                status=RESERVATION_STATUS_PENDING,
                payment_status=PAYMENT_STATUS_UNPAID,
                lock_version=0,
            )

            response = CreateReservationResponse(
                reservation_code=reservation_code,
                status=reservation.status,
                payment_status=reservation.payment_status,
                public_price_total=reservation.public_price_total,
                currency_code=reservation.currency_code,
            )

            await self._reservation_repo.create_reservation(
                reservation=reservation,
                contacts=contacts,
                drivers=drivers,
            )
            await self._idempotency_repo.save(
                IdempotencyRecord(
                    scope=scope,
                    idem_key=idem_key,
                    request_hash=request_hash,
                    response_json=json.loads(response.model_dump_json()),
                    http_status=status.HTTP_201_CREATED,
                    reference_reservation_code=reservation_code,
                )
            )

        return response
