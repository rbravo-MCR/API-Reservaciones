"""Entidad Driver - representa un conductor de la reservación."""

from dataclasses import dataclass
from datetime import date


@dataclass
class Driver:
    """
    Entidad que representa un conductor asociado a una reservación.

    Puede haber múltiples conductores, pero solo uno es el principal.
    """

    # Identificadores
    id: int | None = None
    reservation_id: int | None = None
    reservation_code: str | None = None

    # Rol
    is_primary_driver: bool = True

    # Datos personales
    first_name: str = ""
    last_name: str = ""
    email: str | None = None
    phone: str | None = None

    # Documentación
    date_of_birth: date | str | None = None
    driver_license_number: str | None = None

    # === Propiedades ===

    @property
    def full_name(self) -> str:
        """Retorna el nombre completo del conductor."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def age(self) -> int | None:
        """Calcula la edad del conductor basado en la fecha de nacimiento."""
        if not self.date_of_birth:
            return None

        dob = self.date_of_birth
        if isinstance(dob, str):
            try:
                dob = date.fromisoformat(dob)
            except ValueError:
                return None

        today = date.today()
        age = today.year - dob.year
        if (today.month, today.day) < (dob.month, dob.day):
            age -= 1
        return age

    @property
    def is_adult(self) -> bool:
        """Verifica si el conductor es mayor de 18 años."""
        age = self.age
        return age is not None and age >= 18

    @property
    def meets_minimum_age(self) -> bool:
        """Verifica si cumple la edad mínima para rentar (generalmente 21-25)."""
        age = self.age
        return age is not None and age >= 21

    # === Métodos ===

    def update_info(
        self,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        date_of_birth: date | str | None = None,
        driver_license_number: str | None = None,
    ) -> None:
        """Actualiza la información del conductor."""
        if first_name is not None:
            self.first_name = first_name
        if last_name is not None:
            self.last_name = last_name
        if email is not None:
            self.email = email
        if phone is not None:
            self.phone = phone
        if date_of_birth is not None:
            self.date_of_birth = date_of_birth
        if driver_license_number is not None:
            self.driver_license_number = driver_license_number

    def set_as_primary(self) -> None:
        """Marca este conductor como el principal."""
        self.is_primary_driver = True

    def set_as_secondary(self) -> None:
        """Marca este conductor como secundario."""
        self.is_primary_driver = False

    @classmethod
    def create_primary(
        cls,
        first_name: str,
        last_name: str,
        email: str | None = None,
        phone: str | None = None,
        date_of_birth: date | str | None = None,
        driver_license_number: str | None = None,
        reservation_id: int | None = None,
        reservation_code: str | None = None,
    ) -> "Driver":
        """Factory para crear un conductor principal."""
        return cls(
            reservation_id=reservation_id,
            reservation_code=reservation_code,
            is_primary_driver=True,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            date_of_birth=date_of_birth,
            driver_license_number=driver_license_number,
        )

    @classmethod
    def create_additional(
        cls,
        first_name: str,
        last_name: str,
        email: str | None = None,
        phone: str | None = None,
        date_of_birth: date | str | None = None,
        driver_license_number: str | None = None,
        reservation_id: int | None = None,
        reservation_code: str | None = None,
    ) -> "Driver":
        """Factory para crear un conductor adicional."""
        return cls(
            reservation_id=reservation_id,
            reservation_code=reservation_code,
            is_primary_driver=False,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            date_of_birth=date_of_birth,
            driver_license_number=driver_license_number,
        )
