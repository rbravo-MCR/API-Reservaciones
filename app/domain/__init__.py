"""
Capa de Dominio - Sistema de Reservaciones.

Esta capa contiene la lógica de negocio pura, sin dependencias de frameworks.
Incluye entidades, value objects y excepciones de dominio.

Estructura:
- entities/: Entidades del dominio (Reservation, Payment, etc.)
- value_objects/: Objetos de valor inmutables (Money, ReservationCode, etc.)
- errors.py: Excepciones específicas del dominio
- constants.py: Constantes del dominio
"""

from app.domain.constants import (
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_UNPAID,
    RESERVATION_STATUS_CONFIRMED,
    RESERVATION_STATUS_ON_REQUEST,
    RESERVATION_STATUS_PENDING,
)
from app.domain.entities import (
    BookingDevice,
    Contact,
    ContactType,
    Driver,
    OutboxEvent,
    OutboxEventType,
    OutboxStatus,
    Payment,
    PaymentProvider,
    PaymentStatus,
    Reservation,
    ReservationPaymentStatus,
    ReservationStatus,
    SupplierRequest,
    SupplierRequestStatus,
    SupplierRequestType,
)
from app.domain.errors import (
    DomainError,
    DuplicatePaymentEventError,
    IdempotencyConflictError,
    InvalidDateRangeError,
    InvalidMoneyError,
    InvalidReservationStatusError,
    OptimisticLockError,
    PaymentAlreadyProcessedError,
    PaymentNotFoundError,
    ReceiptNotReadyError,
    ReservationAlreadyExistsError,
    ReservationNotFoundError,
    SupplierBookingFailedError,
    SupplierNotFoundError,
    SupplierTimeoutError,
    ValidationError,
)
from app.domain.value_objects import DatetimeRange, Money, ReservationCode

__all__ = [
    # Constants
    "PAYMENT_STATUS_PAID",
    "PAYMENT_STATUS_UNPAID",
    "RESERVATION_STATUS_CONFIRMED",
    "RESERVATION_STATUS_ON_REQUEST",
    "RESERVATION_STATUS_PENDING",
    # Entities
    "Reservation",
    "ReservationStatus",
    "ReservationPaymentStatus",
    "BookingDevice",
    "Payment",
    "PaymentStatus",
    "PaymentProvider",
    "SupplierRequest",
    "SupplierRequestStatus",
    "SupplierRequestType",
    "Contact",
    "ContactType",
    "Driver",
    "OutboxEvent",
    "OutboxEventType",
    "OutboxStatus",
    # Value Objects
    "Money",
    "ReservationCode",
    "DatetimeRange",
    # Errors
    "DomainError",
    "ReservationNotFoundError",
    "ReservationAlreadyExistsError",
    "InvalidReservationStatusError",
    "OptimisticLockError",
    "PaymentNotFoundError",
    "PaymentAlreadyProcessedError",
    "DuplicatePaymentEventError",
    "SupplierNotFoundError",
    "SupplierBookingFailedError",
    "SupplierTimeoutError",
    "IdempotencyConflictError",
    "ValidationError",
    "InvalidDateRangeError",
    "InvalidMoneyError",
    "ReceiptNotReadyError",
]
