import logging

from fastapi import HTTPException, status

from app.api.schemas.reservations import StripeWebhookEnvelope
from app.application.interfaces.outbox_repo import OutboxRepo
from app.application.interfaces.payment_repo import PaymentRepo
from app.application.interfaces.reservation_repo import ReservationRepo
from app.application.interfaces.stripe_gateway import StripeGateway
from app.domain.constants import PAYMENT_STATUS_PAID, PAYMENT_STATUS_UNPAID


class HandleStripeWebhookUseCase:
    def __init__(
        self,
        payment_repo: PaymentRepo,
        reservation_repo: ReservationRepo,
        outbox_repo: OutboxRepo,
        stripe_gateway: StripeGateway,
        stripe_webhook_secret: str | None,
    ) -> None:
        self._payment_repo = payment_repo
        self._reservation_repo = reservation_repo
        self._outbox_repo = outbox_repo
        self._stripe_gateway = stripe_gateway
        self._stripe_webhook_secret = stripe_webhook_secret
        self._logger = logging.getLogger(__name__)

    async def execute(self, raw_body: bytes, signature: str | None) -> None:
        if not raw_body:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Empty webhook body"
            )
        try:
            event_dict = await self._stripe_gateway.parse_webhook_event(
                payload=raw_body,
                signature_header=signature,
                webhook_secret=self._stripe_webhook_secret,
            )
            event = StripeWebhookEnvelope.model_validate(event_dict)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        if not event.type or not event.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event payload"
            )

        stripe_event_id = event.id
        intent_id = self._extract_intent_id(event)
        payment = await self._payment_repo.find_by_payment_intent(intent_id) if intent_id else None

        # Idempotent by stripe_event_id
        if stripe_event_id:
            existing_by_event = await self._payment_repo.find_by_stripe_event(
                provider="stripe", stripe_event_id=stripe_event_id
            )
            if existing_by_event:
                return

        if not payment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
        reservation = await self._reservation_repo.get_by_code(payment.reservation_code)
        expected_lock_version = reservation.lock_version if reservation else None

        if event.type == "payment_intent.succeeded":
            await self._payment_repo.mark_captured(
                payment_id=payment.id,
                stripe_event_id=stripe_event_id or "",
                stripe_charge_id=self._extract_charge_id(event),
            )
            await self._reservation_repo.update_payment_status(
                reservation_code=payment.reservation_code,
                payment_status=PAYMENT_STATUS_PAID,
                expected_lock_version=expected_lock_version,
            )
            await self._outbox_repo.enqueue(
                event_type="BOOK_SUPPLIER",
                aggregate_type="reservation",
                aggregate_code=payment.reservation_code,
                payload={"reservation_code": payment.reservation_code},
            )
            self._logger.info(
                "Stripe webhook processed: payment succeeded",
                extra={
                    "stripe_event_id": stripe_event_id,
                    "payment_intent_id": intent_id,
                    "reservation_code": payment.reservation_code,
                },
            )
        elif event.type == "payment_intent.payment_failed":
            await self._payment_repo.mark_failed(
                payment_id=payment.id,
                stripe_event_id=stripe_event_id or "",
            )
            await self._reservation_repo.update_payment_status(
                reservation_code=payment.reservation_code,
                payment_status=PAYMENT_STATUS_UNPAID,
                expected_lock_version=expected_lock_version,
            )
            self._logger.warning(
                "Stripe webhook processed: payment failed",
                extra={
                    "stripe_event_id": stripe_event_id,
                    "payment_intent_id": intent_id,
                    "reservation_code": payment.reservation_code,
                },
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unhandled event type"
            )

    def _extract_intent_id(self, event: StripeWebhookEnvelope) -> str | None:
        data_obj = event.data.get("object", {}) if isinstance(event.data, dict) else {}
        return data_obj.get("id") or data_obj.get("payment_intent")

    def _extract_charge_id(self, event: StripeWebhookEnvelope) -> str | None:
        data_obj = event.data.get("object", {}) if isinstance(event.data, dict) else {}
        if data_obj.get("charges") and data_obj["charges"].get("data"):
            charge = data_obj["charges"]["data"][0]
            return charge.get("id")
        return data_obj.get("latest_charge")
