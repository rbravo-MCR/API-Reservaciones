import json

from app.infrastructure.db.repository import ReservationRepository


class HandleStripeWebhookUseCase:
    def __init__(self, repository: ReservationRepository):
        self.repository = repository

    async def execute(self, payload: bytes, sig_header: str) -> bool:
        """
        Handles the Stripe webhook event.
        Returns True if processed, False if ignored.
        """
        # 1. Verify Signature (Mocked for this slice)
        # In real app: stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON payload") from None

        event_type = event.get("type")
        
        if event_type == "payment_intent.succeeded":
            data = event.get("data", {}).get("object", {})
            
            # Try to get reservation_code from metadata
            metadata = data.get("metadata", {})
            reservation_code = metadata.get("reservation_code")
            payment_id = data.get("id")
            
            if not reservation_code:
                # Fallback: In a real app we might search by payment_intent_id 
                # if metadata is missing
                # For now, we assume it's always there or we log an error
                print("WARNING: reservation_code missing in payment_intent metadata")
                return False

            # 2. Atomic Update: Mark Paid + Enqueue Confirmation
            await self.repository.mark_as_paid_and_enqueue_confirmation(
                reservation_code=reservation_code,
                payment_id=payment_id
            )
            return True
            
        elif event_type == "payment_intent.payment_failed":
            # Handle failure (update status to PAYMENT_FAILED)
            # Not implemented in this slice as per plan
            return True
            
        return False
