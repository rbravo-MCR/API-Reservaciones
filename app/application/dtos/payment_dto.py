"""DTOs para pagos."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class PaymentDTO:
    """DTO completo de un pago."""

    # Identificadores
    id: int | None = None
    reservation_id: int | None = None
    reservation_code: str | None = None

    # Proveedor
    provider: str = "STRIPE"
    provider_transaction_id: str | None = None

    # Stripe específico
    stripe_payment_intent_id: str | None = None
    stripe_charge_id: str | None = None
    stripe_event_id: str | None = None

    # Monto
    amount: Decimal = Decimal("0")
    currency_code: str = "USD"

    # Estado
    status: str = "PENDING"

    # Timestamps
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None
    captured_at: datetime | str | None = None

    @property
    def amount_in_cents(self) -> int:
        """Retorna el monto en centavos (para Stripe)."""
        return int(self.amount * 100)

    @property
    def is_successful(self) -> bool:
        """Verifica si el pago fue exitoso."""
        return self.status == "CAPTURED"

    @property
    def is_pending(self) -> bool:
        """Verifica si el pago está pendiente."""
        return self.status in ("PENDING", "PROCESSING")


@dataclass
class PaymentIntentDTO:
    """DTO para crear un Payment Intent en Stripe."""

    # Reservación
    reservation_code: str
    reservation_id: int | None = None

    # Monto
    amount: Decimal = Decimal("0")
    currency_code: str = "USD"

    # Cliente
    customer_email: str = ""
    customer_name: str = ""

    # Metadata
    description: str | None = None
    metadata: dict | None = None

    # Resultado de Stripe
    stripe_payment_intent_id: str | None = None
    client_secret: str | None = None

    @property
    def amount_in_cents(self) -> int:
        """Retorna el monto en centavos (para Stripe)."""
        return int(self.amount * 100)

    @classmethod
    def from_reservation(
        cls,
        reservation_code: str,
        amount: Decimal,
        currency_code: str,
        customer_email: str,
        customer_name: str,
        reservation_id: int | None = None,
    ) -> "PaymentIntentDTO":
        """Factory desde datos de reservación."""
        return cls(
            reservation_code=reservation_code,
            reservation_id=reservation_id,
            amount=amount,
            currency_code=currency_code,
            customer_email=customer_email,
            customer_name=customer_name,
            description=f"Reservación {reservation_code}",
            metadata={
                "reservation_code": reservation_code,
                "customer_email": customer_email,
            },
        )


@dataclass
class PaymentStatusDTO:
    """DTO para el estado de un pago (respuesta simplificada)."""

    payment_id: int | None = None
    reservation_code: str = ""
    status: str = "PENDING"
    amount: Decimal = Decimal("0")
    currency_code: str = "USD"
    provider: str = "STRIPE"
    captured_at: datetime | str | None = None

    # Para el cliente
    is_successful: bool = False
    is_pending: bool = True
    error_message: str | None = None


@dataclass
class StripeWebhookDTO:
    """DTO para procesar webhooks de Stripe."""

    # Evento
    event_id: str = ""
    event_type: str = ""

    # Payment Intent
    payment_intent_id: str = ""
    charge_id: str | None = None

    # Monto
    amount: int = 0  # En centavos
    currency: str = "usd"

    # Estado
    status: str = ""

    # Metadata
    metadata: dict | None = None

    # Raw payload (para logging/debugging)
    raw_payload: dict | None = None

    @property
    def amount_decimal(self) -> Decimal:
        """Convierte el monto de centavos a decimal."""
        return Decimal(self.amount) / 100

    @property
    def reservation_code(self) -> str | None:
        """Extrae el código de reservación del metadata."""
        if self.metadata:
            return self.metadata.get("reservation_code")
        return None

    @property
    def is_payment_succeeded(self) -> bool:
        """Verifica si el evento es de pago exitoso."""
        return self.event_type == "payment_intent.succeeded"

    @property
    def is_payment_failed(self) -> bool:
        """Verifica si el evento es de pago fallido."""
        return self.event_type == "payment_intent.payment_failed"
