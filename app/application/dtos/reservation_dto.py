"""DTOs para reservaciones."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class ContactDTO:
    """DTO para datos de contacto."""

    contact_type: str = "CUSTOMER"
    full_name: str = ""
    email: str = ""
    phone: str | None = None

    @property
    def first_name(self) -> str:
        """Extrae el primer nombre."""
        parts = self.full_name.split()
        return parts[0] if parts else ""

    @property
    def last_name(self) -> str:
        """Extrae el apellido."""
        parts = self.full_name.split()
        return " ".join(parts[1:]) if len(parts) > 1 else ""


@dataclass
class DriverDTO:
    """DTO para datos de conductor."""

    first_name: str = ""
    last_name: str = ""
    email: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None
    driver_license_number: str | None = None
    is_primary_driver: bool = True

    @property
    def full_name(self) -> str:
        """Retorna el nombre completo."""
        return f"{self.first_name} {self.last_name}".strip()


@dataclass
class CreateReservationDTO:
    """DTO para crear una nueva reservación."""

    # Datos del cliente
    customer_email: str
    customer_first_name: str
    customer_last_name: str
    customer_phone: str | None = None

    # Referencias
    supplier_id: int = 0
    pickup_office_id: int = 0
    dropoff_office_id: int = 0
    car_category_id: int = 0
    sales_channel_id: int = 0

    # Códigos de oficina (para supplier)
    pickup_office_code: str | None = None
    dropoff_office_code: str | None = None
    country_code: str = ""

    # Producto
    supplier_car_product_id: int | None = None
    acriss_code: str | None = None

    # Fechas
    pickup_datetime: datetime | str = ""
    dropoff_datetime: datetime | str = ""

    # Financieros
    currency_code: str = "USD"
    public_price_total: Decimal = Decimal("0")
    supplier_cost_total: Decimal = Decimal("0")
    taxes_total: Decimal = Decimal("0")
    fees_total: Decimal = Decimal("0")
    discount_total: Decimal = Decimal("0")
    commission_total: Decimal = Decimal("0")
    cashback_earned_amount: Decimal = Decimal("0")

    # Marketing / Tracking
    traffic_source_id: int | None = None
    marketing_campaign_id: int | None = None
    affiliate_id: int | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_term: str | None = None
    utm_content: str | None = None

    # Dispositivo
    booking_device: str = "DESKTOP"
    customer_ip: str | None = None
    customer_user_agent: str | None = None

    # Conductores adicionales
    drivers: list[DriverDTO] = field(default_factory=list)

    # Idempotencia
    idempotency_key: str | None = None

    @property
    def customer_full_name(self) -> str:
        """Retorna el nombre completo del cliente."""
        return f"{self.customer_first_name} {self.customer_last_name}".strip()


@dataclass
class ReservationDTO:
    """DTO completo de una reservación."""

    # Identificadores
    id: int | None = None
    reservation_code: str = ""

    # Estados
    status: str = "DRAFT"
    payment_status: str = "UNPAID"

    # Cliente
    customer_email: str = ""
    customer_name: str = ""

    # Referencias
    supplier_id: int = 0
    pickup_office_id: int = 0
    dropoff_office_id: int = 0
    car_category_id: int = 0
    sales_channel_id: int = 0

    # Códigos
    pickup_office_code: str | None = None
    dropoff_office_code: str | None = None
    country_code: str = ""
    acriss_code: str | None = None

    # Fechas
    pickup_datetime: datetime | str | None = None
    dropoff_datetime: datetime | str | None = None
    rental_days: int = 0

    # Financieros
    currency_code: str = "USD"
    public_price_total: Decimal = Decimal("0")
    supplier_cost_total: Decimal = Decimal("0")
    taxes_total: Decimal = Decimal("0")
    fees_total: Decimal = Decimal("0")
    discount_total: Decimal = Decimal("0")

    # Supplier
    supplier_reservation_code: str | None = None
    supplier_confirmed_at: datetime | str | None = None

    # Control
    lock_version: int = 0
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None

    # Relaciones
    contacts: list[ContactDTO] = field(default_factory=list)
    drivers: list[DriverDTO] = field(default_factory=list)


@dataclass
class ReservationSummaryDTO:
    """DTO resumido de una reservación (para listados)."""

    reservation_code: str = ""
    status: str = ""
    payment_status: str = ""
    customer_email: str = ""
    customer_name: str = ""
    pickup_datetime: datetime | str | None = None
    dropoff_datetime: datetime | str | None = None
    public_price_total: Decimal = Decimal("0")
    currency_code: str = "USD"
    created_at: datetime | str | None = None


@dataclass
class ReservationReceiptDTO:
    """DTO para el recibo de una reservación confirmada."""

    # Reservación
    reservation_code: str = ""
    status: str = ""

    # Cliente
    customer_email: str = ""
    customer_name: str = ""

    # Fechas
    pickup_datetime: datetime | str | None = None
    dropoff_datetime: datetime | str | None = None
    rental_days: int = 0

    # Financieros
    total_amount: Decimal = Decimal("0")
    currency_code: str = "USD"

    # Pago
    payment_id: str | None = None
    payment_status: str | None = None
    payment_provider: str | None = None

    # Supplier
    supplier_confirmation_code: str | None = None
    supplier_confirmed_at: datetime | str | None = None

    # Vehículo
    car_category: str | None = None
    acriss_code: str | None = None

    # Oficinas
    pickup_office: str | None = None
    dropoff_office: str | None = None

    # Contactos y conductores
    contacts: list[ContactDTO] = field(default_factory=list)
    drivers: list[DriverDTO] = field(default_factory=list)
