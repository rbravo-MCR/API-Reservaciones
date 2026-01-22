"""Implementaciones in-memory para testing."""

from app.infrastructure.in_memory.contact_repo import InMemoryContactRepo
from app.infrastructure.in_memory.driver_repo import InMemoryDriverRepo
from app.infrastructure.in_memory.idempotency_repo import InMemoryIdempotencyRepo
from app.infrastructure.in_memory.outbox_repo import InMemoryOutboxRepo
from app.infrastructure.in_memory.payment_repo import InMemoryPaymentRepo
from app.infrastructure.in_memory.receipt_query import InMemoryReceiptQuery
from app.infrastructure.in_memory.reservation_repo import InMemoryReservationRepo
from app.infrastructure.in_memory.stripe_gateway import StubStripeGateway as InMemoryStripeGateway
from app.infrastructure.in_memory.supplier_gateway import StubSupplierGateway as InMemorySupplierGateway
from app.infrastructure.in_memory.supplier_request_repo import InMemorySupplierRequestRepo
from app.infrastructure.in_memory.transaction_manager import NoopTransactionManager as InMemoryTransactionManager

__all__ = [
    # Repositories
    "InMemoryIdempotencyRepo",
    "InMemoryReservationRepo",
    "InMemoryContactRepo",
    "InMemoryDriverRepo",
    "InMemoryPaymentRepo",
    "InMemoryOutboxRepo",
    "InMemorySupplierRequestRepo",
    "InMemoryReceiptQuery",
    # Gateways
    "InMemoryStripeGateway",
    "InMemorySupplierGateway",
    # Infrastructure
    "InMemoryTransactionManager",
]
