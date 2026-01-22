"""
Capa de Infraestructura - Sistema de Reservaciones.

Esta capa contiene las implementaciones concretas de los puertos (interfaces).
Incluye adaptadores para bases de datos, gateways externos y servicios.

Estructura:
- db/: Repositorios SQL y configuración de base de datos
- gateways/: Adaptadores para servicios externos (Stripe, Suppliers)
- in_memory/: Implementaciones in-memory para testing
- messaging/: Workers y procesadores de mensajes
- services/: Servicios de infraestructura (Clock, UUID)
"""

# Database
# from app.infrastructure.db.mysql_engine import get_async_engine, get_async_session
from app.infrastructure.db.repositories.contact_repo_sql import ContactRepoSQL
from app.infrastructure.db.repositories.driver_repo_sql import DriverRepoSQL
from app.infrastructure.db.repositories.idempotency_repo_sql import IdempotencyRepoSQL
from app.infrastructure.db.repositories.outbox_repo_sql import OutboxRepoSQL
from app.infrastructure.db.repositories.payment_repo_sql import PaymentRepoSQL
from app.infrastructure.db.repositories.reservation_repo_sql import ReservationRepoSQL
from app.infrastructure.db.repositories.supplier_request_repo_sql import SupplierRequestRepoSQL
from app.infrastructure.db.transaction_manager import SQLAlchemyTransactionManager

# Gateways
from app.infrastructure.gateways.factory import SupplierGatewayFactory
from app.infrastructure.gateways.stripe_gateway_real import StripeGatewayReal

# In-Memory (for testing)
from app.infrastructure.gateways.in_memory import (
    InMemoryContactRepo,
    InMemoryDriverRepo,
    InMemoryIdempotencyRepo,
    InMemoryOutboxRepo,
    InMemoryPaymentRepo,
    InMemoryReceiptQuery,
    InMemoryReservationRepo,
    InMemoryStripeGateway,
    InMemorySupplierGateway,
    InMemorySupplierRequestRepo,
    InMemoryTransactionManager,
)

# Messaging
from app.infrastructure.messaging.outbox_worker import OutboxWorker, OutboxWorkerFactory

# Services
from app.infrastructure.services.clock_impl import ClockImpl
from app.infrastructure.services.uuid_generator_impl import UUIDGeneratorImpl

__all__ = [
    # Database - Engine
    # "get_async_engine",  # Not exported from mysql_engine.py
    # "get_async_session",  # Not exported from mysql_engine.py
    # Database - Repositories SQL
    "IdempotencyRepoSQL",
    "ReservationRepoSQL",
    "ContactRepoSQL",
    "DriverRepoSQL",
    "PaymentRepoSQL",
    "OutboxRepoSQL",
    "SupplierRequestRepoSQL",
    "SQLAlchemyTransactionManager",
    # Gateways
    "StripeGatewayReal",
    "SupplierGatewayFactory",
    # In-Memory Implementations
    "InMemoryIdempotencyRepo",
    "InMemoryReservationRepo",
    "InMemoryContactRepo",
    "InMemoryDriverRepo",
    "InMemoryPaymentRepo",
    "InMemoryOutboxRepo",
    "InMemorySupplierRequestRepo",
    "InMemoryReceiptQuery",
    "InMemoryStripeGateway",
    "InMemorySupplierGateway",
    "InMemoryTransactionManager",
    # Messaging
    "OutboxWorker",
    "OutboxWorkerFactory",
    # Services
    "ClockImpl",
    "UUIDGeneratorImpl",
]
