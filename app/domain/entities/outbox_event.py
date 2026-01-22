"""Entidad OutboxEvent - representa un evento en el patrón Outbox."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class OutboxStatus(str, Enum):
    """Estados de un evento en el outbox."""

    NEW = "NEW"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"
    RETRY = "RETRY"


class OutboxEventType(str, Enum):
    """Tipos de eventos del outbox."""

    BOOK_SUPPLIER_REQUESTED = "BOOK_SUPPLIER_REQUESTED"
    PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    RESERVATION_CONFIRMED = "RESERVATION_CONFIRMED"
    RESERVATION_CANCELLED = "RESERVATION_CANCELLED"
    RETRY_SUPPLIER_BOOKING = "RETRY_SUPPLIER_BOOKING"


class AggregateType(str, Enum):
    """Tipos de agregados."""

    RESERVATION = "RESERVATION"
    PAYMENT = "PAYMENT"


@dataclass
class OutboxEvent:
    """
    Entidad que representa un evento en el patrón Transactional Outbox.

    Garantiza consistencia eventual entre operaciones de base de datos
    y llamadas a servicios externos (Stripe, Suppliers).
    """

    # Identificadores
    id: int | None = None

    # Tipo de evento
    event_type: OutboxEventType | str = OutboxEventType.BOOK_SUPPLIER_REQUESTED

    # Agregado asociado
    aggregate_type: AggregateType | str = AggregateType.RESERVATION
    aggregate_id: int | None = None
    aggregate_code: str | None = None

    # Payload del evento (JSON)
    payload: dict[str, Any] = field(default_factory=dict)

    # Estado
    status: OutboxStatus = OutboxStatus.NEW

    # Reintentos
    attempts: int = 0
    max_attempts: int = 5
    next_attempt_at: datetime | None = None

    # Locking para procesamiento distribuido
    locked_by: str | None = None
    locked_at: datetime | None = None
    lock_expires_at: datetime | None = None

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # === Propiedades ===

    @property
    def is_processable(self) -> bool:
        """Verifica si el evento puede ser procesado."""
        if self.status not in (OutboxStatus.NEW, OutboxStatus.RETRY, OutboxStatus.PENDING):
            return False
        if self.next_attempt_at and datetime.utcnow() < self.next_attempt_at:
            return False
        return True

    @property
    def is_locked(self) -> bool:
        """Verifica si el evento está bloqueado por otro worker."""
        if not self.locked_by:
            return False
        if self.lock_expires_at and datetime.utcnow() > self.lock_expires_at:
            return False  # Lock expirado
        return True

    @property
    def can_retry(self) -> bool:
        """Verifica si el evento puede ser reintentado."""
        return self.attempts < self.max_attempts

    @property
    def is_final(self) -> bool:
        """Verifica si el evento está en un estado final."""
        return self.status in (OutboxStatus.DONE, OutboxStatus.FAILED)

    # === Métodos de negocio ===

    def claim(self, worker_id: str, lock_duration_seconds: int = 300) -> bool:
        """
        Intenta reclamar el evento para procesamiento.

        Args:
            worker_id: Identificador del worker que reclama.
            lock_duration_seconds: Duración del lock en segundos.

        Returns:
            True si se pudo reclamar, False si ya está bloqueado.
        """
        if self.is_locked:
            return False

        now = datetime.utcnow()
        self.locked_by = worker_id
        self.locked_at = now
        self.lock_expires_at = now + timedelta(seconds=lock_duration_seconds)
        self.status = OutboxStatus.PROCESSING
        return True

    def release_lock(self) -> None:
        """Libera el lock del evento."""
        self.locked_by = None
        self.locked_at = None
        self.lock_expires_at = None

    def mark_done(self) -> None:
        """Marca el evento como procesado exitosamente."""
        self.status = OutboxStatus.DONE
        self.release_lock()

    def mark_retry(self, backoff_seconds: int | None = None) -> None:
        """
        Marca el evento para reintento con backoff exponencial.

        Args:
            backoff_seconds: Segundos hasta el próximo intento.
                           Si es None, usa backoff exponencial.
        """
        self.attempts += 1

        if not self.can_retry:
            self.mark_failed()
            return

        self.status = OutboxStatus.RETRY

        if backoff_seconds is None:
            # Backoff exponencial: 30s, 60s, 120s, 240s, 480s
            backoff_seconds = 30 * (2 ** (self.attempts - 1))

        self.next_attempt_at = datetime.utcnow() + timedelta(seconds=backoff_seconds)
        self.release_lock()

    def mark_failed(self) -> None:
        """Marca el evento como fallido permanentemente."""
        self.status = OutboxStatus.FAILED
        self.release_lock()

    @classmethod
    def create_book_supplier_event(
        cls,
        reservation_id: int,
        reservation_code: str,
        payload: dict[str, Any],
    ) -> "OutboxEvent":
        """Factory para crear un evento de booking a supplier."""
        return cls(
            event_type=OutboxEventType.BOOK_SUPPLIER_REQUESTED,
            aggregate_type=AggregateType.RESERVATION,
            aggregate_id=reservation_id,
            aggregate_code=reservation_code,
            payload=payload,
            status=OutboxStatus.NEW,
        )

    @classmethod
    def create_payment_captured_event(
        cls,
        reservation_id: int,
        reservation_code: str,
        payment_id: int,
        amount: str,
        currency: str,
    ) -> "OutboxEvent":
        """Factory para crear un evento de pago capturado."""
        return cls(
            event_type=OutboxEventType.PAYMENT_CAPTURED,
            aggregate_type=AggregateType.PAYMENT,
            aggregate_id=payment_id,
            aggregate_code=reservation_code,
            payload={
                "reservation_id": reservation_id,
                "reservation_code": reservation_code,
                "payment_id": payment_id,
                "amount": amount,
                "currency": currency,
            },
            status=OutboxStatus.NEW,
        )
