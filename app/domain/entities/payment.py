"""Entidad Payment - representa un pago de reservación."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.domain.value_objects.money import Money


class PaymentStatus(str, Enum):
    """Estados posibles de un pago."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class PaymentProvider(str, Enum):
    """Proveedores de pago soportados."""

    STRIPE = "STRIPE"
    PAYPAL = "PAYPAL"
    MANUAL = "MANUAL"


@dataclass
class Payment:
    """
    Entidad que representa un pago asociado a una reservación.

    Maneja la información de pagos procesados por Stripe u otros proveedores.
    """

    # Identificadores
    id: int | None = None
    reservation_id: int = 0
    reservation_code: str | None = None

    # Proveedor
    provider: PaymentProvider = PaymentProvider.STRIPE
    provider_transaction_id: str | None = None

    # Stripe específico
    stripe_payment_intent_id: str | None = None
    stripe_charge_id: str | None = None
    stripe_event_id: str | None = None

    # Monto
    amount: Decimal = Decimal("0")
    currency_code: str = "USD"

    # Estado
    status: PaymentStatus = PaymentStatus.PENDING

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None
    captured_at: datetime | None = None

    # === Propiedades ===

    @property
    def money(self) -> Money:
        """Retorna el monto como Value Object Money."""
        return Money(amount=self.amount, currency_code=self.currency_code)

    @property
    def is_successful(self) -> bool:
        """Verifica si el pago fue exitoso."""
        return self.status == PaymentStatus.CAPTURED

    @property
    def is_final(self) -> bool:
        """Verifica si el pago está en un estado final (no puede cambiar)."""
        return self.status in (
            PaymentStatus.CAPTURED,
            PaymentStatus.FAILED,
            PaymentStatus.CANCELLED,
            PaymentStatus.REFUNDED,
        )

    @property
    def can_be_captured(self) -> bool:
        """Verifica si el pago puede ser capturado."""
        return self.status in (PaymentStatus.PENDING, PaymentStatus.PROCESSING)

    # === Métodos de negocio ===

    def mark_as_processing(self) -> None:
        """Marca el pago como en proceso."""
        if self.is_final:
            raise ValueError(f"No se puede procesar un pago en estado {self.status}")
        self.status = PaymentStatus.PROCESSING

    def capture(self, captured_at: datetime, charge_id: str | None = None) -> None:
        """Marca el pago como capturado exitosamente."""
        if self.is_final:
            raise ValueError(f"No se puede capturar un pago en estado {self.status}")
        self.status = PaymentStatus.CAPTURED
        self.captured_at = captured_at
        if charge_id:
            self.stripe_charge_id = charge_id

    def fail(self) -> None:
        """Marca el pago como fallido."""
        if self.status == PaymentStatus.CAPTURED:
            raise ValueError("No se puede marcar como fallido un pago ya capturado")
        self.status = PaymentStatus.FAILED

    def refund(self) -> None:
        """Marca el pago como reembolsado."""
        if self.status != PaymentStatus.CAPTURED:
            raise ValueError("Solo se pueden reembolsar pagos capturados")
        self.status = PaymentStatus.REFUNDED

    def cancel(self) -> None:
        """Cancela el pago."""
        if self.is_final:
            raise ValueError(f"No se puede cancelar un pago en estado {self.status}")
        self.status = PaymentStatus.CANCELLED

    def set_stripe_event(self, event_id: str) -> None:
        """Registra el evento de Stripe que procesó este pago."""
        self.stripe_event_id = event_id

    @classmethod
    def create_pending(
        cls,
        reservation_id: int,
        amount: Decimal,
        currency_code: str,
        stripe_payment_intent_id: str,
        reservation_code: str | None = None,
    ) -> "Payment":
        """Factory para crear un pago pendiente."""
        return cls(
            reservation_id=reservation_id,
            reservation_code=reservation_code,
            provider=PaymentProvider.STRIPE,
            stripe_payment_intent_id=stripe_payment_intent_id,
            amount=amount,
            currency_code=currency_code,
            status=PaymentStatus.PENDING,
        )
