from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class StripePaymentResult:
    status: str
    payment_intent_id: str
    charge_id: str
    event_id: str


class StripeGateway:
    async def confirm_payment(
        self,
        amount: Decimal,
        currency: str,
        payment_method_id: str,
        idempotency_key: str,
    ) -> StripePaymentResult:
        raise NotImplementedError

    async def parse_webhook_event(
        self,
        payload: bytes,
        signature_header: str | None,
        webhook_secret: str | None,
    ) -> dict[str, Any]:
        raise NotImplementedError
