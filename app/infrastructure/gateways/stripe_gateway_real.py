import json

import stripe

from app.application.interfaces.stripe_gateway import StripeGateway, StripePaymentResult
from app.config import get_settings


class StripeGatewayReal(StripeGateway):
    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        stripe.api_key = api_key or settings.stripe_api_key

    async def confirm_payment(
        self,
        amount,
        currency: str,
        payment_method_id: str,
        idempotency_key: str,
    ) -> StripePaymentResult:
        # stripe does not have async client; run sync call (acceptable for now)
        intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),
            currency=currency.lower(),
            payment_method=payment_method_id,
            confirm=True,
            automatic_payment_methods={"enabled": True},
        )
        charge_id = intent.charges.data[0].id if intent.charges.data else intent.latest_charge
        return StripePaymentResult(
            status=intent.status,
            payment_intent_id=intent.id,
            charge_id=charge_id,
            event_id="",
        )

    async def parse_webhook_event(
        self,
        payload: bytes,
        signature_header: str | None,
        webhook_secret: str | None,
    ) -> dict:
        if webhook_secret:
            if not signature_header:
                raise ValueError("Missing Stripe-Signature header")
            try:
                event = stripe.Webhook.construct_event(
                    payload=payload.decode(),
                    sig_header=signature_header,
                    secret=webhook_secret,
                )
            except stripe.error.SignatureVerificationError as exc:
                raise ValueError("Invalid Stripe signature") from exc
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Invalid Stripe webhook payload") from exc
        else:
            try:
                event = stripe.Event.construct_from(
                    json.loads(payload.decode() or "{}"), stripe.api_key
                )
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Invalid webhook payload") from exc

        return event.to_dict() if hasattr(event, "to_dict") else dict(event)
