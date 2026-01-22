"""Interface DriverRepo - Puerto para repositorio de conductores."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence


@dataclass
class DriverRecord:
    """Record de conductor para persistencia."""

    id: int | None = None
    reservation_id: int | None = None
    reservation_code: str | None = None
    is_primary_driver: bool = True
    first_name: str = ""
    last_name: str = ""
    email: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None
    driver_license_number: str | None = None


class DriverRepo(ABC):
    """
    Puerto para el repositorio de conductores.

    Define las operaciones de persistencia para conductores de reservaciones.
    """

    @abstractmethod
    async def create(self, driver: DriverRecord) -> DriverRecord:
        """
        Crea un nuevo conductor.

        Args:
            driver: Datos del conductor a crear.

        Returns:
            DriverRecord con el ID asignado.
        """
        raise NotImplementedError

    @abstractmethod
    async def create_many(self, drivers: Sequence[DriverRecord]) -> Sequence[DriverRecord]:
        """
        Crea múltiples conductores en batch.

        Args:
            drivers: Lista de conductores a crear.

        Returns:
            Lista de DriverRecord con IDs asignados.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, driver_id: int) -> DriverRecord | None:
        """
        Obtiene un conductor por su ID.

        Args:
            driver_id: ID del conductor.

        Returns:
            DriverRecord o None si no existe.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by_reservation(self, reservation_code: str) -> Sequence[DriverRecord]:
        """
        Lista todos los conductores de una reservación.

        Args:
            reservation_code: Código de la reservación.

        Returns:
            Lista de conductores asociados.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by_reservation_id(self, reservation_id: int) -> Sequence[DriverRecord]:
        """
        Lista todos los conductores de una reservación por ID.

        Args:
            reservation_id: ID de la reservación.

        Returns:
            Lista de conductores asociados.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_primary_driver(self, reservation_code: str) -> DriverRecord | None:
        """
        Obtiene el conductor principal de una reservación.

        Args:
            reservation_code: Código de la reservación.

        Returns:
            DriverRecord del conductor principal o None.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(self, driver: DriverRecord) -> DriverRecord:
        """
        Actualiza un conductor existente.

        Args:
            driver: Datos actualizados del conductor.

        Returns:
            DriverRecord actualizado.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, driver_id: int) -> None:
        """
        Elimina un conductor.

        Args:
            driver_id: ID del conductor a eliminar.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_by_reservation(self, reservation_code: str) -> int:
        """
        Elimina todos los conductores de una reservación.

        Args:
            reservation_code: Código de la reservación.

        Returns:
            Número de conductores eliminados.
        """
        raise NotImplementedError

    @abstractmethod
    async def set_primary_driver(self, reservation_code: str, driver_id: int) -> None:
        """
        Establece un conductor como principal (y los demás como secundarios).

        Args:
            reservation_code: Código de la reservación.
            driver_id: ID del conductor a establecer como principal.
        """
        raise NotImplementedError
