"""Implementación in-memory del repositorio de contactos."""

from typing import Sequence

from app.application.interfaces.contact_repo import ContactRecord, ContactRepo


class InMemoryContactRepo(ContactRepo):
    """Implementación in-memory del repositorio de contactos para testing."""

    def __init__(self) -> None:
        self._contacts: dict[int, ContactRecord] = {}
        self._by_reservation: dict[str, list[int]] = {}
        self._next_id = 1

    async def create(self, contact: ContactRecord) -> ContactRecord:
        """Crea un nuevo contacto en memoria."""
        contact.id = self._next_id
        self._next_id += 1
        self._contacts[contact.id] = contact

        # Indexar por reservación
        res_code = contact.reservation_code or str(contact.reservation_id)
        if res_code not in self._by_reservation:
            self._by_reservation[res_code] = []
        self._by_reservation[res_code].append(contact.id)

        return contact

    async def create_many(self, contacts: Sequence[ContactRecord]) -> Sequence[ContactRecord]:
        """Crea múltiples contactos en batch."""
        result = []
        for contact in contacts:
            created = await self.create(contact)
            result.append(created)
        return result

    async def get_by_id(self, contact_id: int) -> ContactRecord | None:
        """Obtiene un contacto por su ID."""
        return self._contacts.get(contact_id)

    async def list_by_reservation(self, reservation_code: str) -> Sequence[ContactRecord]:
        """Lista todos los contactos de una reservación por código."""
        contact_ids = self._by_reservation.get(reservation_code, [])
        return [self._contacts[cid] for cid in contact_ids if cid in self._contacts]

    async def list_by_reservation_id(self, reservation_id: int) -> Sequence[ContactRecord]:
        """Lista todos los contactos de una reservación por ID."""
        return [
            c for c in self._contacts.values()
            if c.reservation_id == reservation_id
        ]

    async def update(self, contact: ContactRecord) -> ContactRecord:
        """Actualiza un contacto existente."""
        if contact.id is None or contact.id not in self._contacts:
            raise ValueError("Contact not found")
        self._contacts[contact.id] = contact
        return contact

    async def delete(self, contact_id: int) -> None:
        """Elimina un contacto por ID."""
        if contact_id in self._contacts:
            contact = self._contacts[contact_id]
            res_code = contact.reservation_code or str(contact.reservation_id)
            if res_code in self._by_reservation:
                self._by_reservation[res_code] = [
                    cid for cid in self._by_reservation[res_code] if cid != contact_id
                ]
            del self._contacts[contact_id]

    async def delete_by_reservation(self, reservation_code: str) -> int:
        """Elimina todos los contactos de una reservación."""
        contact_ids = self._by_reservation.get(reservation_code, [])
        count = len(contact_ids)
        for contact_id in contact_ids:
            if contact_id in self._contacts:
                del self._contacts[contact_id]
        self._by_reservation[reservation_code] = []
        return count

    def clear(self) -> None:
        """Limpia todos los datos (para testing)."""
        self._contacts.clear()
        self._by_reservation.clear()
        self._next_id = 1
