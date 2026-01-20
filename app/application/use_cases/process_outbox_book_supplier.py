import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.application.interfaces.outbox_repo import OutboxRepo
from app.application.interfaces.reservation_repo import ReservationRepo
from app.application.interfaces.supplier_request_repo import SupplierRequestRepo
from app.domain.constants import RESERVATION_STATUS_CONFIRMED, RESERVATION_STATUS_ON_REQUEST
from app.infrastructure.gateways.supplier_gateway_selector import SupplierGatewaySelector

MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 15


class ProcessOutboxBookSupplierUseCase:
    def __init__(
        self,
        outbox_repo: OutboxRepo,
        reservation_repo: ReservationRepo,
        supplier_gateway_selector: SupplierGatewaySelector,
        supplier_request_repo: SupplierRequestRepo,
    ) -> None:
        self._outbox_repo = outbox_repo
        self._reservation_repo = reservation_repo
        self._supplier_gateway_selector = supplier_gateway_selector
        self._supplier_request_repo = supplier_request_repo
        self._logger = logging.getLogger(__name__)

    async def execute(
        self,
        reservation_code: str,
        idem_key: str,
        worker_id: str = "worker-1",
        now: datetime | None = None,
    ) -> dict:
        now = now or datetime.now(timezone.utc)
        event = await self._outbox_repo.claim(
            aggregate_code=reservation_code,
            event_type="BOOK_SUPPLIER",
            locked_by=worker_id,
            now=now,
        )
        if not event:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No outbox event ready or already locked",
            )

        reservation = await self._reservation_repo.get_by_code(reservation_code)
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found"
            )
        expected_lock_version = reservation.lock_version
        if not getattr(reservation, "country_code", None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="country_code required"
            )

        gateway = self._supplier_gateway_selector.for_supplier(
            supplier_id=reservation.supplier_id,
            country_code=reservation.country_code,
        )
        if not gateway:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No gateway configured for supplier/country",
            )

        attempt_number = (event.attempts or 0) + 1
        supplier_req = await self._supplier_request_repo.create_in_progress(
            reservation_code=reservation_code,
            supplier_id=reservation.supplier_id,
            request_type="BOOK_CREATE",
            idem_key=idem_key,
            attempt=attempt_number,
        )

        booking_result = await gateway.book(reservation_code=reservation_code, idem_key=idem_key)
        # Try with snapshot if gateway requests it
        if (
            booking_result.status == "FAILED"
            and booking_result.error_code in {"MISSING_SNAPSHOT", "MISSING_OFFICE_CODES"}
        ):
            from dataclasses import asdict

            booking_result = await gateway.book(
                reservation_code=reservation_code,
                idem_key=idem_key,
                reservation_snapshot=asdict(reservation),
            )

        if booking_result.status == "SUCCESS":
            await self._supplier_request_repo.mark_success(
                request_id=supplier_req.id,
                response_payload=booking_result.payload,
                supplier_reservation_code=booking_result.supplier_reservation_code or "",
            )
            await self._reservation_repo.mark_confirmed(
                reservation_code=reservation_code,
                supplier_reservation_code=booking_result.supplier_reservation_code or "",
                supplier_confirmed_at=booking_result.payload.get("confirmed_at", "")
                if booking_result.payload
                else "",
                expected_lock_version=expected_lock_version,
            )
            await self._outbox_repo.mark_done(event.id)
            self._logger.info(
                "Supplier booking success",
                extra={
                    "reservation_code": reservation_code,
                    "outbox_event_id": event.id,
                    "attempt": attempt_number,
                    "supplier_reservation_code": booking_result.supplier_reservation_code,
                },
            )
            return {
                "status": RESERVATION_STATUS_CONFIRMED,
                "supplier_reservation_code": booking_result.supplier_reservation_code,
            }

        attempts = attempt_number
        backoff_seconds = min(BASE_BACKOFF_SECONDS * (2 ** (attempts - 1)), 300)
        next_attempt_at = now + timedelta(seconds=backoff_seconds)
        if attempts >= MAX_ATTEMPTS:
            await self._outbox_repo.mark_failed(
                event_id=event.id,
                attempts=attempts,
                aggregate_code=reservation_code,
                event_type="BOOK_SUPPLIER",
                error_code=booking_result.error_code,
                error_message=booking_result.error_message,
            )
        else:
            await self._outbox_repo.mark_retry(
                event_id=event.id,
                attempts=attempts,
                next_attempt_at=next_attempt_at,
                error_code=booking_result.error_code,
                error_message=booking_result.error_message,
            )
            self._logger.warning(
                "Supplier booking retry scheduled",
                extra={
                    "reservation_code": reservation_code,
                    "outbox_event_id": event.id,
                    "attempt": attempts,
                    "next_attempt_at": next_attempt_at.isoformat(),
                    "error_code": booking_result.error_code,
                },
            )
        await self._supplier_request_repo.mark_failed(
            request_id=supplier_req.id,
            error_code=booking_result.error_code,
            error_message=booking_result.error_message,
            http_status=booking_result.http_status,
            response_payload=booking_result.payload,
        )
        if attempts >= MAX_ATTEMPTS:
            self._logger.error(
                "Supplier booking failed permanently",
                extra={
                    "reservation_code": reservation_code,
                    "outbox_event_id": event.id,
                    "attempt": attempts,
                    "error_code": booking_result.error_code,
                },
            )
        return {
            "status": RESERVATION_STATUS_ON_REQUEST,
            "next_attempt_at": next_attempt_at.isoformat() if attempts < MAX_ATTEMPTS else None,
            "attempts": attempts,
        }
