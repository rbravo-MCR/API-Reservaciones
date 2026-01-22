import logging

from app.infrastructure.db.models import OutboxStatus
from app.infrastructure.db.repository import ReservationRepository
from app.infrastructure.gateways.factory import SupplierGatewayFactory

logger = logging.getLogger(__name__)


class ProcessOutboxUseCase:
    def __init__(self, repository: ReservationRepository, factory: SupplierGatewayFactory):
        self.repository = repository
        self.factory = factory

    async def execute(self) -> int:
        """
        Processes pending outbox events.
        Returns the number of processed events.
        """
        events = await self.repository.get_pending_outbox_events(limit=10)
        processed_count = 0
        
        for event in events:
            try:
                if event.type == "CONFIRM_SUPPLIER":
                    reservation_code = event.payload.get("reservation_code")
                    if not reservation_code:
                        raise ValueError("Missing reservation_code in payload")
                    
                    # Fetch Reservation to get details and supplier_id
                    reservation = await self.repository.get_by_code(reservation_code)
                    if not reservation:
                        msg = f"Reservation {reservation_code} not found"
                        raise ValueError(msg)

                    # Get correct adapter from factory
                    adapter = self.factory.get_adapter(str(reservation.supplier_id))
                    
                    # Call Supplier
                    supplier_code = await adapter.confirm_booking(
                        reservation_code=reservation_code,
                        details={
                            "pickup_office_code": "MIA", # Simplified for now
                            "pickup_datetime": reservation.pickup_datetime.isoformat(),
                            "dropoff_datetime": reservation.dropoff_datetime.isoformat(),
                            "customer_email": "qa@example.com", # Should be in reservation
                            "first_name": "QA",
                            "last_name": "Tester"
                        }
                    )
                    
                    # Update Reservation with Supplier Code
                    await self.repository.update_reservation_supplier_code(
                        reservation_code=reservation_code,
                        supplier_code=supplier_code
                    )
                
                # Mark Event as Processed
                event.status = OutboxStatus.PROCESSED
                # event.processed_at was removed from model to match DB schema
                processed_count += 1
                
            except Exception as e:
                logger.error(
                    "Error processing outbox event",
                    exc_info=e,
                    extra={
                        "event_id": event.id,
                        "event_type": event.type,
                        "retry_count": event.retry_count
                    }
                )
                event.retry_count += 1
                
                # Fallback Strategy (ADR-003):
                # If it's a transient failure (or even permanent for now), we ensure the user
                # feels "Confirmed" while we retry in background.
                if event.type == "CONFIRM_SUPPLIER":
                    # We need to fetch the reservation to check/update status
                    # Note: Ideally we should use a specific method in repository 
                    # to avoid N+1 if many events,
                    # but for this slice it's acceptable.
                    reservation_code = event.payload.get("reservation_code")
                    if reservation_code:
                        # We use a new method or existing logic. 
                        await self.repository.mark_as_confirmed_internal(reservation_code)

                # Simple retry logic: if > 3 retries, mark FAILED
                if event.retry_count >= 3:
                    event.status = OutboxStatus.FAILED
        
        return processed_count
