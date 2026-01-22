"""Implementación SQL del repositorio de contactos."""

from typing import Sequence

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.contact_repo import ContactRecord, ContactRepo
from app.infrastructure.db.tables import reservation_contacts


class ContactRepoSQL(ContactRepo):
    """Implementación SQL del repositorio de contactos usando SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, contact: ContactRecord) -> ContactRecord:
        """Crea un nuevo contacto en la base de datos."""
        values = {
            "reservation_id": contact.reservation_id,
            "reservation_code": contact.reservation_code,
            "contact_type": contact.contact_type,
            "full_name": contact.full_name,
            "email": contact.email,
            "phone": contact.phone,
        }
        stmt = insert(reservation_contacts).values(values)
        result = await self._session.execute(stmt)
        contact.id = result.inserted_primary_key[0]
        return contact

    async def create_many(self, contacts: Sequence[ContactRecord]) -> Sequence[ContactRecord]:
        """Crea múltiples contactos en batch."""
        if not contacts:
            return []

        rows = [
            {
                "reservation_id": c.reservation_id,
                "reservation_code": c.reservation_code,
                "contact_type": c.contact_type,
                "full_name": c.full_name,
                "email": c.email,
                "phone": c.phone,
            }
            for c in contacts
        ]
        await self._session.execute(insert(reservation_contacts), rows)
        return contacts

    async def get_by_id(self, contact_id: int) -> ContactRecord | None:
        """Obtiene un contacto por su ID."""
        stmt = select(reservation_contacts).where(reservation_contacts.c.id == contact_id)
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if not row:
            return None
        return self._row_to_record(row)

    async def list_by_reservation(self, reservation_code: str) -> Sequence[ContactRecord]:
        """Lista todos los contactos de una reservación por código."""
        stmt = select(reservation_contacts).where(
            reservation_contacts.c.reservation_code == reservation_code
        )
        result = await self._session.execute(stmt)
        rows = result.mappings().all()
        return [self._row_to_record(row) for row in rows]

    async def list_by_reservation_id(self, reservation_id: int) -> Sequence[ContactRecord]:
        """Lista todos los contactos de una reservación por ID."""
        stmt = select(reservation_contacts).where(
            reservation_contacts.c.reservation_id == reservation_id
        )
        result = await self._session.execute(stmt)
        rows = result.mappings().all()
        return [self._row_to_record(row) for row in rows]

    async def update(self, contact: ContactRecord) -> ContactRecord:
        """Actualiza un contacto existente."""
        if contact.id is None:
            raise ValueError("Contact ID is required for update")

        values = {
            "contact_type": contact.contact_type,
            "full_name": contact.full_name,
            "email": contact.email,
            "phone": contact.phone,
        }
        stmt = (
            update(reservation_contacts)
            .where(reservation_contacts.c.id == contact.id)
            .values(values)
        )
        await self._session.execute(stmt)
        return contact

    async def delete(self, contact_id: int) -> None:
        """Elimina un contacto por ID."""
        stmt = delete(reservation_contacts).where(reservation_contacts.c.id == contact_id)
        await self._session.execute(stmt)

    async def delete_by_reservation(self, reservation_code: str) -> int:
        """Elimina todos los contactos de una reservación."""
        stmt = delete(reservation_contacts).where(
            reservation_contacts.c.reservation_code == reservation_code
        )
        result = await self._session.execute(stmt)
        return result.rowcount

    def _row_to_record(self, row) -> ContactRecord:
        """Convierte una fila de DB a ContactRecord."""
        return ContactRecord(
            id=row["id"],
            reservation_id=row["reservation_id"],
            reservation_code=row.get("reservation_code"),
            contact_type=row["contact_type"],
            full_name=row["full_name"],
            email=row["email"],
            phone=row.get("phone"),
        )
