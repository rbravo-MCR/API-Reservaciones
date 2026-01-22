import json
from decimal import Decimal
from uuid import uuid4

from app.application.interfaces.stripe_gateway import StripeGateway, StripePaymentResult


class StubStripeGateway(StripeGateway):
    async def confirm_payment(
        self,
        amount: Decimal,
        currency: str,
        payment_method_id: str,
        idempotency_key: str,
    ) -> StripePaymentResult:
        # Simulate immediate capture success
        intent_id = f"pi_{uuid4().hex[:14]}"
        charge_id = f"ch_{uuid4().hex[:14]}"
        return StripePaymentResult(
            status="succeeded",
            payment_intent_id=intent_id,
            charge_id=charge_id,
            event_id="",
        )

    async def parse_webhook_event(
        self,
        payload: bytes,
        signature_header: str | None,
        webhook_secret: str | None,
    ) -> dict:
        if not payload:
            raise ValueError("Empty webhook payload")
        try:
            return json.loads(payload.decode() or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid webhook payload") from exc
