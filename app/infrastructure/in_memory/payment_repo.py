from collections import defaultdict
from decimal import Decimal
from typing import Sequence

from app.application.interfaces.payment_repo import PaymentRecord, PaymentRepo


class InMemoryPaymentRepo(PaymentRepo):
    def __init__(self) -> None:
        self._by_id: dict[int, PaymentRecord] = {}
        self._by_reservation: dict[str, list[int]] = defaultdict(list)
        self._by_event: dict[str, int] = {}
        self._by_intent: dict[str, int] = {}
        self._next_id = 1

    async def create_pending(
        self,
        reservation_code: str,
        amount: Decimal,
        currency_code: str,
        stripe_payment_intent_id: str | None,
    ) -> PaymentRecord:
        record = PaymentRecord(
            id=self._next_id,
            reservation_code=reservation_code,
            provider="stripe",
            status="PENDING",
            amount=amount,
            currency_code=currency_code,
            stripe_payment_intent_id=stripe_payment_intent_id,
        )
        self._next_id += 1
        self._by_id[record.id] = record
        self._by_reservation[reservation_code].append(record.id)
        if stripe_payment_intent_id:
            self._by_intent[stripe_payment_intent_id] = record.id
        return record

    async def mark_captured(
        self,
        payment_id: int,
        stripe_event_id: str,
        stripe_charge_id: str | None = None,
    ) -> PaymentRecord:
        record = self._by_id[payment_id]
        record.status = "CAPTURED"
        record.stripe_event_id = stripe_event_id
        record.stripe_charge_id = stripe_charge_id
        if stripe_event_id:
            self._by_event[stripe_event_id] = record.id
        return record

    async def mark_failed(
        self,
        payment_id: int,
        stripe_event_id: str,
    ) -> PaymentRecord:
        record = self._by_id[payment_id]
        record.status = "FAILED"
        record.stripe_event_id = stripe_event_id
        if stripe_event_id:
            self._by_event[stripe_event_id] = record.id
        return record

    async def find_by_stripe_event(
        self,
        provider: str,
        stripe_event_id: str,
    ) -> PaymentRecord | None:
        payment_id = self._by_event.get(stripe_event_id)
        return self._by_id.get(payment_id) if payment_id else None

    async def find_by_payment_intent(
        self,
        stripe_payment_intent_id: str,
    ) -> PaymentRecord | None:
        payment_id = self._by_intent.get(stripe_payment_intent_id)
        return self._by_id.get(payment_id) if payment_id else None

    async def list_by_reservation(
        self,
        reservation_code: str,
    ) -> Sequence[PaymentRecord]:
        return [self._by_id[pid] for pid in self._by_reservation.get(reservation_code, [])]
