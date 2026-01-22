"""Entidad Reservation - Agregado raíz del dominio."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from app.domain.value_objects.datetime_range import DatetimeRange
from app.domain.value_objects.money import Money
from app.domain.value_objects.reservation_code import ReservationCode

if TYPE_CHECKING:
    from app.domain.entities.contact import Contact
    from app.domain.entities.driver import Driver


class ReservationStatus(str, Enum):
    """Estados posibles de una reservación."""

    DRAFT = "DRAFT"
    PENDING = "PENDING"
    ON_REQUEST = "ON_REQUEST"
    CONFIRMED = "CONFIRMED"
    CONFIRMED_INTERNAL = "CONFIRMED_INTERNAL"
    CANCELLED = "CANCELLED"
    CANCELLED_REFUND = "CANCELLED_REFUND"


class ReservationPaymentStatus(str, Enum):
    """Estados de pago de una reservación."""

    UNPAID = "UNPAID"
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class BookingDevice(str, Enum):
    """Dispositivo desde donde se hizo la reservación."""

    DESKTOP = "DESKTOP"
    MOBILE = "MOBILE"
    TABLET = "TABLET"
    APP = "APP"


@dataclass
class Reservation:
    """
    Entidad principal del dominio - Agregado Raíz.

    Representa una reservación de vehículo con todos sus datos asociados.
    """

    # Identificadores
    id: int | None = None
    reservation_code: ReservationCode | None = None

    # Referencias externas (FKs)
    supplier_id: int = 0
    pickup_office_id: int = 0
    dropoff_office_id: int = 0
    car_category_id: int = 0
    sales_channel_id: int = 0

    # Códigos de oficina (para supplier)
    pickup_office_code: str | None = None
    dropoff_office_code: str | None = None
    country_code: str = ""

    # Producto del supplier
    supplier_car_product_id: int | None = None
    acriss_code: str | None = None

    # Fechas y duración
    pickup_datetime: datetime | None = None
    dropoff_datetime: datetime | None = None
    rental_days: int = 0

    # Financieros
    currency_code: str = "USD"
    public_price_total: Decimal = Decimal("0")
    supplier_cost_total: Decimal = Decimal("0")
    taxes_total: Decimal = Decimal("0")
    fees_total: Decimal = Decimal("0")
    discount_total: Decimal = Decimal("0")
    commission_total: Decimal = Decimal("0")
    cashback_earned_amount: Decimal = Decimal("0")

    # Estados
    status: ReservationStatus = ReservationStatus.DRAFT
    payment_status: ReservationPaymentStatus = ReservationPaymentStatus.UNPAID

    # Marketing / Tracking
    traffic_source_id: int | None = None
    marketing_campaign_id: int | None = None
    affiliate_id: int | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_term: str | None = None
    utm_content: str | None = None

    # Dispositivo y cliente
    booking_device: BookingDevice = BookingDevice.DESKTOP
    customer_ip: str | None = None
    customer_user_agent: str | None = None

    # Confirmación del supplier
    supplier_reservation_code: str | None = None
    supplier_confirmed_at: datetime | None = None

    # Control de concurrencia
    lock_version: int = 0

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Relaciones (no persistidas directamente)
    contacts: list["Contact"] = field(default_factory=list)
    drivers: list["Driver"] = field(default_factory=list)

    # === Propiedades calculadas ===

    @property
    def datetime_range(self) -> DatetimeRange | None:
        """Retorna el rango de fechas como Value Object."""
        if self.pickup_datetime and self.dropoff_datetime:
            return DatetimeRange(start=self.pickup_datetime, end=self.dropoff_datetime)
        return None

    @property
    def public_price(self) -> Money:
        """Retorna el precio público como Value Object Money."""
        return Money(amount=self.public_price_total, currency_code=self.currency_code)

    @property
    def supplier_cost(self) -> Money:
        """Retorna el costo del supplier como Value Object Money."""
        return Money(amount=self.supplier_cost_total, currency_code=self.currency_code)

    @property
    def is_confirmed(self) -> bool:
        """Verifica si la reservación está confirmada (por supplier o internamente)."""
        return self.status in (ReservationStatus.CONFIRMED, ReservationStatus.CONFIRMED_INTERNAL)

    @property
    def is_paid(self) -> bool:
        """Verifica si la reservación está pagada."""
        return self.payment_status == ReservationPaymentStatus.PAID

    @property
    def can_be_cancelled(self) -> bool:
        """Verifica si la reservación puede ser cancelada."""
        return self.status not in (
            ReservationStatus.CANCELLED,
            ReservationStatus.CANCELLED_REFUND,
        )

    @property
    def primary_driver(self) -> "Driver | None":
        """Retorna el conductor principal."""
        for driver in self.drivers:
            if driver.is_primary_driver:
                return driver
        return self.drivers[0] if self.drivers else None

    @property
    def primary_contact(self) -> "Contact | None":
        """Retorna el contacto principal (CUSTOMER)."""
        from app.domain.entities.contact import ContactType

        for contact in self.contacts:
            if contact.contact_type == ContactType.CUSTOMER:
                return contact
        return self.contacts[0] if self.contacts else None

    # === Métodos de negocio ===

    def mark_as_pending_payment(self) -> None:
        """Marca la reservación como pendiente de pago."""
        self.status = ReservationStatus.PENDING
        self.payment_status = ReservationPaymentStatus.PENDING
        self.lock_version += 1

    def mark_as_paid(self) -> None:
        """Marca la reservación como pagada."""
        self.payment_status = ReservationPaymentStatus.PAID
        self.status = ReservationStatus.ON_REQUEST
        self.lock_version += 1

    def mark_as_payment_failed(self) -> None:
        """Marca el pago como fallido."""
        self.payment_status = ReservationPaymentStatus.FAILED
        self.lock_version += 1

    def confirm_with_supplier(self, supplier_code: str, confirmed_at: datetime) -> None:
        """Confirma la reservación con el código del supplier."""
        self.status = ReservationStatus.CONFIRMED
        self.supplier_reservation_code = supplier_code
        self.supplier_confirmed_at = confirmed_at
        self.lock_version += 1

    def confirm_internal(self) -> None:
        """Confirma internamente (cuando el supplier falla pero el pago fue exitoso)."""
        self.status = ReservationStatus.CONFIRMED_INTERNAL
        self.lock_version += 1

    def cancel(self, with_refund: bool = False) -> None:
        """Cancela la reservación."""
        self.status = (
            ReservationStatus.CANCELLED_REFUND if with_refund else ReservationStatus.CANCELLED
        )
        self.lock_version += 1

    def generate_code(self) -> None:
        """Genera un nuevo código de reservación."""
        self.reservation_code = ReservationCode.generate()

    def calculate_rental_days(self) -> int:
        """Calcula los días de renta basado en las fechas."""
        if self.datetime_range:
            return self.datetime_range.rental_days
        return self.rental_days
