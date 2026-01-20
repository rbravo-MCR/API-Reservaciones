from decimal import Decimal
from typing import Sequence

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.payment_repo import PaymentRecord, PaymentRepo
from app.infrastructure.db.tables import payments, reservations


class PaymentRepoSQL(PaymentRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_reservation(self, reservation_code: str) -> tuple[int, str] | None:
        stmt = select(reservations.c.id, reservations.c.reservation_code).where(
            reservations.c.reservation_code == reservation_code
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if not row:
            return None
        return row[0], row[1]

    async def create_pending(
        self,
        reservation_code: str,
        amount: Decimal,
        currency_code: str,
        stripe_payment_intent_id: str | None,
    ) -> PaymentRecord:
        reservation_row = await self._get_reservation(reservation_code)
        if not reservation_row:
            raise ValueError("Reservation not found")
        reservation_id, res_code = reservation_row
        stmt = insert(payments).values(
            reservation_id=reservation_id,
            reservation_code=res_code,
            provider="stripe",
            status="PENDING",
            amount=amount,
            currency_code=currency_code,
            stripe_payment_intent_id=stripe_payment_intent_id,
        )
        result = await self._session.execute(stmt)
        payment_id = result.inserted_primary_key[0]
        return PaymentRecord(
            id=payment_id,
            reservation_code=res_code,
            provider="stripe",
            status="PENDING",
            amount=amount,
            currency_code=currency_code,
            stripe_payment_intent_id=stripe_payment_intent_id,
        )

    async def mark_captured(
        self,
        payment_id: int,
        stripe_event_id: str,
        stripe_charge_id: str | None = None,
    ) -> PaymentRecord:
        stmt = (
            update(payments)
            .where(payments.c.id == payment_id)
            .values(
                status="CAPTURED",
                stripe_event_id=stripe_event_id,
                stripe_charge_id=stripe_charge_id,
            )
        )
        await self._session.execute(stmt)
        return await self._fetch_payment(payment_id)

    async def mark_failed(
        self,
        payment_id: int,
        stripe_event_id: str,
    ) -> PaymentRecord:
        stmt = (
            update(payments)
            .where(payments.c.id == payment_id)
            .values(status="FAILED", stripe_event_id=stripe_event_id)
        )
        await self._session.execute(stmt)
        return await self._fetch_payment(payment_id)

    async def find_by_stripe_event(
        self,
        provider: str,
        stripe_event_id: str,
    ) -> PaymentRecord | None:
        stmt = select(payments).where(
            payments.c.stripe_event_id == stripe_event_id, payments.c.provider == provider
        )
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        return self._map_payment(row) if row else None

    async def find_by_payment_intent(
        self,
        stripe_payment_intent_id: str,
    ) -> PaymentRecord | None:
        stmt = select(payments).where(
            payments.c.stripe_payment_intent_id == stripe_payment_intent_id
        )
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        return self._map_payment(row) if row else None

    async def list_by_reservation(
        self,
        reservation_code: str,
    ) -> Sequence[PaymentRecord]:
        stmt = (
            select(payments)
            .where(payments.c.reservation_code == reservation_code)
            .order_by(payments.c.id)
        )
        result = await self._session.execute(stmt)
        rows = result.mappings().all()
        return [self._map_payment(row) for row in rows]

    async def _fetch_payment(self, payment_id: int) -> PaymentRecord:
        stmt = select(payments).where(payments.c.id == payment_id)
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if not row:
            raise ValueError("Payment not found")
        return self._map_payment(row)

    def _map_payment(self, row) -> PaymentRecord:
        return PaymentRecord(
            id=row["id"],
            reservation_code=row.get("reservation_code"),
            provider=row["provider"],
            status=row["status"],
            amount=row["amount"],
            currency_code=row["currency_code"],
            stripe_payment_intent_id=row.get("stripe_payment_intent_id"),
            stripe_charge_id=row.get("stripe_charge_id"),
            stripe_event_id=row.get("stripe_event_id"),
        )
