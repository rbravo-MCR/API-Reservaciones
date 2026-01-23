import hashlib
import json
import logging
from typing import Any

from fastapi import HTTPException, status

from app.api.schemas.reservations import (
    PaymentSummary,
    PayReservationRequest,
    PayReservationResponse,
    SupplierRequestSummary,
)
from app.application.interfaces.idempotency_repo import IdempotencyRecord, IdempotencyRepo
from app.application.interfaces.outbox_repo import OutboxRepo
from app.application.interfaces.payment_repo import PaymentRepo
from app.application.interfaces.reservation_repo import ReservationRepo
from app.application.interfaces.stripe_gateway import StripeGateway
from app.application.interfaces.transaction_manager import TransactionManager
from app.domain.constants import (
    PAYMENT_STATUS_PAID,
    RESERVATION_STATUS_ON_REQUEST,
)


def _hash_request(reservation_code: str, payload: dict[str, Any]) -> str:
    normalized = json.dumps(
        {"reservation_code": reservation_code, **payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


class PayReservationUseCase:
    def __init__(
        self,
        reservation_repo: ReservationRepo,
        payment_repo: PaymentRepo,
        idempotency_repo: IdempotencyRepo,
        stripe_gateway: StripeGateway,
        outbox_repo: OutboxRepo,
        transaction_manager: TransactionManager,
    ) -> None:
        self._reservation_repo = reservation_repo
        self._payment_repo = payment_repo
        self._idempotency_repo = idempotency_repo
        self._stripe_gateway = stripe_gateway
        self._outbox_repo = outbox_repo
        self._transaction_manager = transaction_manager
        self._logger = logging.getLogger(__name__)

    async def execute(
        self,
        reservation_code: str,
        request: PayReservationRequest,
        idem_key: str,
    ) -> PayReservationResponse:
        scope = "RESERVATION_PAY"
        req_hash = _hash_request(reservation_code, request.model_dump())

        async with self._transaction_manager.start():
            existing = await self._idempotency_repo.get(scope=scope, idem_key=idem_key)
            if existing:
                if existing.request_hash != req_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency conflict: different payload for same key",
                    )
                return PayReservationResponse.model_validate(existing.response_json)

            reservation = await self._reservation_repo.get_by_code(reservation_code)
            if not reservation:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found"
                )
            expected_lock_version = reservation.lock_version
            if reservation.payment_status == PAYMENT_STATUS_PAID:
                payments = await self._payment_repo.list_by_reservation(reservation_code)
                latest = payments[-1] if payments else None
                if latest:
                    response = self._build_response(reservation_code, latest)
                    return response
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Reservation already paid"
                )

            payment_result = await self._stripe_gateway.confirm_payment(
                amount=reservation.public_price_total,
                currency=reservation.currency_code,
                payment_method_id=request.payment_method_id,
                idempotency_key=idem_key,
            )

            payment = await self._payment_repo.create_pending(
                reservation_code=reservation_code,
                amount=reservation.public_price_total,
                currency_code=reservation.currency_code,
                stripe_payment_intent_id=payment_result.payment_intent_id,
            )
            captured_payment = await self._payment_repo.mark_captured(
                payment_id=payment.id,
                stripe_event_id=payment_result.event_id,
                stripe_charge_id=payment_result.charge_id,
            )
            await self._reservation_repo.update_payment_status(
                reservation_code=reservation_code,
                payment_status=PAYMENT_STATUS_PAID,
                expected_lock_version=expected_lock_version,
            )
            # Update reservation status to ON_REQUEST as well
            await self._reservation_repo.update_status(
                reservation_code=reservation_code,
                status=RESERVATION_STATUS_ON_REQUEST,
                expected_lock_version=expected_lock_version + 1,
            )
            await self._outbox_repo.enqueue(
                event_type="BOOK_SUPPLIER",
                aggregate_type="reservation",
                aggregate_code=reservation_code,
                payload={"reservation_code": reservation_code},
            )

            response = self._build_response(reservation_code, captured_payment)

            await self._idempotency_repo.save(
                IdempotencyRecord(
                    scope=scope,
                    idem_key=idem_key,
                    request_hash=req_hash,
                    response_json=json.loads(response.model_dump_json()),
                    http_status=status.HTTP_200_OK,
                    reference_reservation_code=reservation_code,
                )
            )
            self._logger.info(
                "Payment captured",
                extra={
                    "reservation_code": reservation_code,
                    "payment_intent_id": captured_payment.stripe_payment_intent_id,
                    "charge_id": captured_payment.stripe_charge_id,
                },
            )
            return response

    def _build_response(self, reservation_code: str, payment: Any) -> PayReservationResponse:
        return PayReservationResponse(
            reservation_code=reservation_code,
            status=RESERVATION_STATUS_ON_REQUEST,
            payment_status=PAYMENT_STATUS_PAID,
            payment=PaymentSummary(
                id=payment.id,
                provider="stripe",
                status=payment.status,
                stripe_payment_intent_id=payment.stripe_payment_intent_id,
                stripe_charge_id=payment.stripe_charge_id,
                amount=payment.amount,
                currency_code=payment.currency_code,
            ),
            supplier_request=SupplierRequestSummary(created=True, status="IN_PROGRESS"),
        )
