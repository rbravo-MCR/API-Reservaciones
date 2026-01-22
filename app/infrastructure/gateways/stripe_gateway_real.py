import json
import logging

import stripe

from app.application.interfaces.stripe_gateway import StripeGateway, StripePaymentResult
from app.config import get_settings
from app.infrastructure.circuit_breaker import CircuitBreakerError, stripe_breaker

logger = logging.getLogger(__name__)


class StripeGatewayReal(StripeGateway):
    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        stripe.api_key = api_key or settings.stripe_api_key

        # Configure timeout and retries to prevent indefinite blocking
        # Stripe SDK doesn't support async timeouts directly, so we configure
        # the underlying connection timeout
        stripe.max_network_retries = 2  # Retry failed requests up to 2 times
        stripe.default_http_client = stripe.http_client.RequestsClient(timeout=10.0)

    async def confirm_payment(
        self,
        amount,
        currency: str,
        payment_method_id: str,
        idempotency_key: str,
    ) -> StripePaymentResult:
        """
        Confirm payment with Stripe API, protected by Circuit Breaker.

        Raises:
            CircuitBreakerError: When circuit is open (too many recent failures)
            stripe.error.StripeError: When Stripe API call fails
        """
        try:
            # Wrap the Stripe API call with circuit breaker protection
            # stripe does not have async client; run sync call (acceptable for now)
            intent = stripe_breaker.call(
                stripe.PaymentIntent.create,
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
        except CircuitBreakerError as e:
            logger.error(
                "Stripe circuit breaker is open - service unavailable",
                extra={"circuit_state": str(e)}
            )
            raise
        except stripe.error.StripeError as e:
            logger.error(
                "Stripe API error",
                exc_info=e,
                extra={"payment_method_id": payment_method_id}
            )
            raise

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
