"""Implementación SQL del repositorio de conductores."""

from typing import Sequence

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.driver_repo import DriverRecord, DriverRepo
from app.infrastructure.db.tables import reservation_drivers


class DriverRepoSQL(DriverRepo):
    """Implementación SQL del repositorio de conductores usando SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, driver: DriverRecord) -> DriverRecord:
        """Crea un nuevo conductor en la base de datos."""
        values = {
            "reservation_id": driver.reservation_id,
            "reservation_code": driver.reservation_code,
            "is_primary_driver": 1 if driver.is_primary_driver else 0,
            "first_name": driver.first_name,
            "last_name": driver.last_name,
            "email": driver.email,
            "phone": driver.phone,
            "date_of_birth": driver.date_of_birth,
            "driver_license_number": driver.driver_license_number,
        }
        stmt = insert(reservation_drivers).values(values)
        result = await self._session.execute(stmt)
        driver.id = result.inserted_primary_key[0]
        return driver

    async def create_many(self, drivers: Sequence[DriverRecord]) -> Sequence[DriverRecord]:
        """Crea múltiples conductores en batch."""
        if not drivers:
            return []

        rows = [
            {
                "reservation_id": d.reservation_id,
                "reservation_code": d.reservation_code,
                "is_primary_driver": 1 if d.is_primary_driver else 0,
                "first_name": d.first_name,
                "last_name": d.last_name,
                "email": d.email,
                "phone": d.phone,
                "date_of_birth": d.date_of_birth,
                "driver_license_number": d.driver_license_number,
            }
            for d in drivers
        ]
        await self._session.execute(insert(reservation_drivers), rows)
        return drivers

    async def get_by_id(self, driver_id: int) -> DriverRecord | None:
        """Obtiene un conductor por su ID."""
        stmt = select(reservation_drivers).where(reservation_drivers.c.id == driver_id)
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if not row:
            return None
        return self._row_to_record(row)

    async def list_by_reservation(self, reservation_code: str) -> Sequence[DriverRecord]:
        """Lista todos los conductores de una reservación por código."""
        stmt = select(reservation_drivers).where(
            reservation_drivers.c.reservation_code == reservation_code
        )
        result = await self._session.execute(stmt)
        rows = result.mappings().all()
        return [self._row_to_record(row) for row in rows]

    async def list_by_reservation_id(self, reservation_id: int) -> Sequence[DriverRecord]:
        """Lista todos los conductores de una reservación por ID."""
        stmt = select(reservation_drivers).where(
            reservation_drivers.c.reservation_id == reservation_id
        )
        result = await self._session.execute(stmt)
        rows = result.mappings().all()
        return [self._row_to_record(row) for row in rows]

    async def get_primary_driver(self, reservation_code: str) -> DriverRecord | None:
        """Obtiene el conductor principal de una reservación."""
        stmt = (
            select(reservation_drivers)
            .where(reservation_drivers.c.reservation_code == reservation_code)
            .where(reservation_drivers.c.is_primary_driver == 1)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if not row:
            return None
        return self._row_to_record(row)

    async def update(self, driver: DriverRecord) -> DriverRecord:
        """Actualiza un conductor existente."""
        if driver.id is None:
            raise ValueError("Driver ID is required for update")

        values = {
            "is_primary_driver": 1 if driver.is_primary_driver else 0,
            "first_name": driver.first_name,
            "last_name": driver.last_name,
            "email": driver.email,
            "phone": driver.phone,
            "date_of_birth": driver.date_of_birth,
            "driver_license_number": driver.driver_license_number,
        }
        stmt = (
            update(reservation_drivers)
            .where(reservation_drivers.c.id == driver.id)
            .values(values)
        )
        await self._session.execute(stmt)
        return driver

    async def delete(self, driver_id: int) -> None:
        """Elimina un conductor por ID."""
        stmt = delete(reservation_drivers).where(reservation_drivers.c.id == driver_id)
        await self._session.execute(stmt)

    async def delete_by_reservation(self, reservation_code: str) -> int:
        """Elimina todos los conductores de una reservación."""
        stmt = delete(reservation_drivers).where(
            reservation_drivers.c.reservation_code == reservation_code
        )
        result = await self._session.execute(stmt)
        return result.rowcount

    async def set_primary_driver(self, reservation_code: str, driver_id: int) -> None:
        """Establece un conductor como principal."""
        # Primero, marcar todos como no primarios
        stmt_reset = (
            update(reservation_drivers)
            .where(reservation_drivers.c.reservation_code == reservation_code)
            .values(is_primary_driver=0)
        )
        await self._session.execute(stmt_reset)

        # Luego, marcar el seleccionado como primario
        stmt_set = (
            update(reservation_drivers)
            .where(reservation_drivers.c.id == driver_id)
            .values(is_primary_driver=1)
        )
        await self._session.execute(stmt_set)

    def _row_to_record(self, row) -> DriverRecord:
        """Convierte una fila de DB a DriverRecord."""
        return DriverRecord(
            id=row["id"],
            reservation_id=row["reservation_id"],
            reservation_code=row.get("reservation_code"),
            is_primary_driver=bool(row["is_primary_driver"]),
            first_name=row["first_name"],
            last_name=row["last_name"],
            email=row.get("email"),
            phone=row.get("phone"),
            date_of_birth=row.get("date_of_birth"),
            driver_license_number=row.get("driver_license_number"),
        )
