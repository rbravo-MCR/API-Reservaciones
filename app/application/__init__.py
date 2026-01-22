"""
Capa de Aplicación - Sistema de Reservaciones.

Esta capa contiene los casos de uso, DTOs e interfaces (puertos).
Orquesta la lógica de negocio y define los contratos con la infraestructura.

Estructura:
- use_cases/: Casos de uso del sistema
- dtos/: Data Transfer Objects
- interfaces/: Puertos (contratos para adaptadores)
- schemas.py: Schemas Pydantic para validación de API
"""

from app.application.dtos import (
    ContactDTO,
    CreateReservationDTO,
    DriverDTO,
    PaymentDTO,
    PaymentIntentDTO,
    PaymentStatusDTO,
    ReservationDTO,
    ReservationReceiptDTO,
    ReservationSummaryDTO,
)
from app.application.interfaces import (
    Clock,
    ContactRecord,
    ContactRepo,
    DriverRecord,
    DriverRepo,
    FakeClock,
    FakeUUIDGenerator,
    IdempotencyRepo,
    OutboxRepo,
    PaymentRecord,
    PaymentRepo,
    RealUUIDGenerator,
    ReceiptQuery,
    ReservationInput,
    ReservationRepo,
    StripeGateway,
    SupplierGateway,
    SupplierRequestRepo,
    SystemClock,
    TransactionManager,
    UUIDGenerator,
)

__all__ = [
    # DTOs
    "ContactDTO",
    "CreateReservationDTO",
    "DriverDTO",
    "PaymentDTO",
    "PaymentIntentDTO",
    "PaymentStatusDTO",
    "ReservationDTO",
    "ReservationReceiptDTO",
    "ReservationSummaryDTO",
    # Interfaces - Repositories
    "IdempotencyRepo",
    "ReservationRepo",
    "ReservationInput",
    "ContactRepo",
    "ContactRecord",
    "DriverRepo",
    "DriverRecord",
    "PaymentRepo",
    "PaymentRecord",
    "OutboxRepo",
    "SupplierRequestRepo",
    "ReceiptQuery",
    # Interfaces - Gateways
    "StripeGateway",
    "SupplierGateway",
    # Interfaces - Infrastructure
    "TransactionManager",
    # Interfaces - Utilities
    "Clock",
    "SystemClock",
    "FakeClock",
    "UUIDGenerator",
    "RealUUIDGenerator",
    "FakeUUIDGenerator",
]
