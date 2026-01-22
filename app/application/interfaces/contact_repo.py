"""Interface ContactRepo - Puerto para repositorio de contactos."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence


@dataclass
class ContactRecord:
    """Record de contacto para persistencia."""

    id: int | None = None
    reservation_id: int | None = None
    reservation_code: str | None = None
    contact_type: str = "CUSTOMER"
    full_name: str = ""
    email: str = ""
    phone: str | None = None


class ContactRepo(ABC):
    """
    Puerto para el repositorio de contactos.

    Define las operaciones de persistencia para contactos de reservaciones.
    """

    @abstractmethod
    async def create(self, contact: ContactRecord) -> ContactRecord:
        """
        Crea un nuevo contacto.

        Args:
            contact: Datos del contacto a crear.

        Returns:
            ContactRecord con el ID asignado.
        """
        raise NotImplementedError

    @abstractmethod
    async def create_many(self, contacts: Sequence[ContactRecord]) -> Sequence[ContactRecord]:
        """
        Crea múltiples contactos en batch.

        Args:
            contacts: Lista de contactos a crear.

        Returns:
            Lista de ContactRecord con IDs asignados.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, contact_id: int) -> ContactRecord | None:
        """
        Obtiene un contacto por su ID.

        Args:
            contact_id: ID del contacto.

        Returns:
            ContactRecord o None si no existe.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by_reservation(self, reservation_code: str) -> Sequence[ContactRecord]:
        """
        Lista todos los contactos de una reservación.

        Args:
            reservation_code: Código de la reservación.

        Returns:
            Lista de contactos asociados.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by_reservation_id(self, reservation_id: int) -> Sequence[ContactRecord]:
        """
        Lista todos los contactos de una reservación por ID.

        Args:
            reservation_id: ID de la reservación.

        Returns:
            Lista de contactos asociados.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(self, contact: ContactRecord) -> ContactRecord:
        """
        Actualiza un contacto existente.

        Args:
            contact: Datos actualizados del contacto.

        Returns:
            ContactRecord actualizado.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, contact_id: int) -> None:
        """
        Elimina un contacto.

        Args:
            contact_id: ID del contacto a eliminar.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_by_reservation(self, reservation_code: str) -> int:
        """
        Elimina todos los contactos de una reservación.

        Args:
            reservation_code: Código de la reservación.

        Returns:
            Número de contactos eliminados.
        """
        raise NotImplementedError
