"""Entidad Contact - representa un contacto de la reservación."""

from dataclasses import dataclass
from enum import Enum


class ContactType(str, Enum):
    """Tipos de contacto."""

    CUSTOMER = "CUSTOMER"
    BILLING = "BILLING"
    EMERGENCY = "EMERGENCY"


@dataclass
class Contact:
    """
    Entidad que representa un contacto asociado a una reservación.

    Puede ser el cliente principal, contacto de facturación o emergencia.
    """

    # Identificadores
    id: int | None = None
    reservation_id: int | None = None
    reservation_code: str | None = None

    # Tipo
    contact_type: ContactType = ContactType.CUSTOMER

    # Datos personales
    full_name: str = ""
    email: str = ""
    phone: str | None = None

    # === Propiedades ===

    @property
    def is_customer(self) -> bool:
        """Verifica si es el contacto del cliente."""
        return self.contact_type == ContactType.CUSTOMER

    @property
    def first_name(self) -> str:
        """Extrae el primer nombre del nombre completo."""
        parts = self.full_name.split()
        return parts[0] if parts else ""

    @property
    def last_name(self) -> str:
        """Extrae el apellido del nombre completo."""
        parts = self.full_name.split()
        return " ".join(parts[1:]) if len(parts) > 1 else ""

    # === Métodos ===

    def update_info(self, full_name: str | None = None, email: str | None = None, phone: str | None = None) -> None:
        """Actualiza la información del contacto."""
        if full_name is not None:
            self.full_name = full_name
        if email is not None:
            self.email = email
        if phone is not None:
            self.phone = phone

    @classmethod
    def create_customer(
        cls,
        full_name: str,
        email: str,
        phone: str | None = None,
        reservation_id: int | None = None,
        reservation_code: str | None = None,
    ) -> "Contact":
        """Factory para crear un contacto de tipo cliente."""
        return cls(
            reservation_id=reservation_id,
            reservation_code=reservation_code,
            contact_type=ContactType.CUSTOMER,
            full_name=full_name,
            email=email,
            phone=phone,
        )

    @classmethod
    def from_customer_data(
        cls,
        first_name: str,
        last_name: str,
        email: str,
        phone: str | None = None,
    ) -> "Contact":
        """Factory para crear desde datos separados de nombre."""
        return cls(
            contact_type=ContactType.CUSTOMER,
            full_name=f"{first_name} {last_name}".strip(),
            email=email,
            phone=phone,
        )
