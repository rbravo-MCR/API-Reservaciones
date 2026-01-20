from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import ReservationModel, ReservationStatus


class ReservationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, reservation: ReservationModel) -> ReservationModel:
        self.session.add(reservation)
        await self.session.flush() # Flush to get ID, but commit is handled by UoW or Use Case
        await self.session.refresh(reservation)
        return reservation

    async def get_by_code(self, code: str) -> ReservationModel | None:
        stmt = select(ReservationModel).where(ReservationModel.reservation_code == code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_as_paid_and_enqueue_confirmation(
        self, reservation_code: str, payment_id: str
    ) -> None:
        # 1. Get Reservation
        stmt = select(ReservationModel).where(ReservationModel.reservation_code == reservation_code)
        result = await self.session.execute(stmt)
        reservation = result.scalar_one_or_none()
        
        if not reservation:
            raise ValueError(f"Reservation {reservation_code} not found")
        
        # 2. Idempotency Check via Payment Table (Robust)
        from sqlalchemy.exc import IntegrityError

        from app.infrastructure.db.models import OutboxEventModel, OutboxStatus, PaymentModel
        
        # Try to insert payment record. If it exists (provider + tx_id), 
        # it will raise IntegrityError
        payment = PaymentModel(
            reservation_id=reservation.id,
            provider="STRIPE",
            provider_transaction_id=payment_id,
            amount=reservation.public_price_total,
            currency_code=reservation.currency_code,
            status="CAPTURED"
        )
        try:
            self.session.add(payment)
            await self.session.flush() # Force insert to check constraint
        except IntegrityError:
            # Duplicate payment -> Idempotent success
            # We assume if payment exists, the process was already triggered.
            # However, we should ensure the Outbox event was also created.
            # But for this slice, we treat it as "Already Done".
            await self.session.rollback() # Rollback the failed insert
            return

        # 3. Update Status
        reservation.status = ReservationStatus.PAID
        reservation.payment_status = "PAID"
        
        # 4. Create Outbox Event
        event = OutboxEventModel(
            event_type="CONFIRM_SUPPLIER",
            aggregate_type="RESERVATION",
            aggregate_id=reservation.id,
            payload={"reservation_code": reservation.reservation_code},
            status=OutboxStatus.PENDING
        )
        self.session.add(event)
        
        # 5. Flush/Commit is handled by the caller (Use Case / UoW)

    async def get_pending_outbox_events(self, limit: int = 10) -> list[Any]:
        # Note: We return Any because of circular import issues if we type hint 
        # OutboxEventModel strictly here without TYPE_CHECKING block. 
        # For simplicity in this slice, we use Any or import inside.
        from app.infrastructure.db.models import OutboxEventModel, OutboxStatus
        
        stmt = select(OutboxEventModel).where(
            OutboxEventModel.status == OutboxStatus.PENDING
        ).limit(limit).with_for_update(skip_locked=True)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_reservation_supplier_code(
        self, reservation_code: str, supplier_code: str
    ) -> None:
        reservation = await self.get_by_code(reservation_code)
        if reservation:
            reservation.supplier_reservation_code = supplier_code
            reservation.status = ReservationStatus.CONFIRMED

    async def mark_as_confirmed_internal(self, reservation_code: str) -> None:
        reservation = await self.get_by_code(reservation_code)
        # Only update if it's still PAID (don't overwrite if already CONFIRMED)
        if reservation and reservation.status == ReservationStatus.PAID:
            reservation.status = ReservationStatus.CONFIRMED_INTERNAL


