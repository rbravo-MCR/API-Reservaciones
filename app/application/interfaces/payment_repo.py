from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


@dataclass
class PaymentRecord:
    id: int
    reservation_code: str
    provider: str
    status: str
    amount: Decimal
    currency_code: str
    stripe_payment_intent_id: str | None = None
    stripe_charge_id: str | None = None
    stripe_event_id: str | None = None


class PaymentRepo:
    async def create_pending(
        self,
        reservation_code: str,
        amount: Decimal,
        currency_code: str,
        stripe_payment_intent_id: str | None,
    ) -> PaymentRecord:
        raise NotImplementedError

    async def mark_captured(
        self,
        payment_id: int,
        stripe_event_id: str,
        stripe_charge_id: str | None = None,
    ) -> PaymentRecord:
        raise NotImplementedError

    async def mark_failed(
        self,
        payment_id: int,
        stripe_event_id: str,
    ) -> PaymentRecord:
        raise NotImplementedError

    async def find_by_stripe_event(
        self,
        provider: str,
        stripe_event_id: str,
    ) -> PaymentRecord | None:
        raise NotImplementedError

    async def find_by_payment_intent(
        self,
        stripe_payment_intent_id: str,
    ) -> PaymentRecord | None:
        raise NotImplementedError

    async def list_by_reservation(
        self,
        reservation_code: str,
    ) -> Sequence[PaymentRecord]:
        raise NotImplementedError
