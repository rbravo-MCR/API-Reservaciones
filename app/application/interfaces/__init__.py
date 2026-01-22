"""Interfaces (Puertos) de la capa de aplicación."""

from app.application.interfaces.clock import Clock, FakeClock, SystemClock
from app.application.interfaces.contact_repo import ContactRecord, ContactRepo
from app.application.interfaces.driver_repo import DriverRecord, DriverRepo
from app.application.interfaces.idempotency_repo import IdempotencyRepo
from app.application.interfaces.outbox_repo import OutboxRepo
from app.application.interfaces.payment_repo import PaymentRecord, PaymentRepo
from app.application.interfaces.receipt_query import ReceiptQuery
from app.application.interfaces.reservation_repo import (
    ContactInput,
    DriverInput,
    ReservationInput,
    ReservationRepo,
)
from app.application.interfaces.stripe_gateway import StripeGateway
from app.application.interfaces.supplier_gateway import SupplierGateway
from app.application.interfaces.supplier_request_repo import SupplierRequestRepo
from app.application.interfaces.transaction_manager import TransactionManager
from app.application.interfaces.uuid_generator import (
    FakeUUIDGenerator,
    RealUUIDGenerator,
    UUIDGenerator,
)

__all__ = [
    # Repositories
    "IdempotencyRepo",
    "ReservationRepo",
    "ReservationInput",
    "ContactInput",
    "DriverInput",
    "ContactRepo",
    "ContactRecord",
    "DriverRepo",
    "DriverRecord",
    "PaymentRepo",
    "PaymentRecord",
    "OutboxRepo",
    "SupplierRequestRepo",
    "ReceiptQuery",
    # Gateways
    "StripeGateway",
    "SupplierGateway",
    # Infrastructure
    "TransactionManager",
    # Utilities
    "Clock",
    "SystemClock",
    "FakeClock",
    "UUIDGenerator",
    "RealUUIDGenerator",
    "FakeUUIDGenerator",
]
