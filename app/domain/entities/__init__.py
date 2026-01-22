"""Entidades del dominio de reservaciones."""

from app.domain.entities.contact import Contact, ContactType
from app.domain.entities.driver import Driver
from app.domain.entities.outbox_event import OutboxEvent, OutboxEventType, OutboxStatus
from app.domain.entities.payment import Payment, PaymentProvider, PaymentStatus
from app.domain.entities.reservation import (
    BookingDevice,
    Reservation,
    ReservationPaymentStatus,
    ReservationStatus,
)
from app.domain.entities.supplier_request import (
    SupplierRequest,
    SupplierRequestStatus,
    SupplierRequestType,
)

__all__ = [
    # Reservation
    "Reservation",
    "ReservationStatus",
    "ReservationPaymentStatus",
    "BookingDevice",
    # Payment
    "Payment",
    "PaymentStatus",
    "PaymentProvider",
    # SupplierRequest
    "SupplierRequest",
    "SupplierRequestStatus",
    "SupplierRequestType",
    # Contact
    "Contact",
    "ContactType",
    # Driver
    "Driver",
    # OutboxEvent
    "OutboxEvent",
    "OutboxEventType",
    "OutboxStatus",
]
