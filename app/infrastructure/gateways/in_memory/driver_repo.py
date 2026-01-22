"""Implementación in-memory del repositorio de conductores."""

from typing import Sequence

from app.application.interfaces.driver_repo import DriverRecord, DriverRepo


class InMemoryDriverRepo(DriverRepo):
    """Implementación in-memory del repositorio de conductores para testing."""

    def __init__(self) -> None:
        self._drivers: dict[int, DriverRecord] = {}
        self._by_reservation: dict[str, list[int]] = {}
        self._next_id = 1

    async def create(self, driver: DriverRecord) -> DriverRecord:
        """Crea un nuevo conductor en memoria."""
        driver.id = self._next_id
        self._next_id += 1
        self._drivers[driver.id] = driver

        # Indexar por reservación
        res_code = driver.reservation_code or str(driver.reservation_id)
        if res_code not in self._by_reservation:
            self._by_reservation[res_code] = []
        self._by_reservation[res_code].append(driver.id)

        return driver

    async def create_many(self, drivers: Sequence[DriverRecord]) -> Sequence[DriverRecord]:
        """Crea múltiples conductores en batch."""
        result = []
        for driver in drivers:
            created = await self.create(driver)
            result.append(created)
        return result

    async def get_by_id(self, driver_id: int) -> DriverRecord | None:
        """Obtiene un conductor por su ID."""
        return self._drivers.get(driver_id)

    async def list_by_reservation(self, reservation_code: str) -> Sequence[DriverRecord]:
        """Lista todos los conductores de una reservación por código."""
        driver_ids = self._by_reservation.get(reservation_code, [])
        return [self._drivers[did] for did in driver_ids if did in self._drivers]

    async def list_by_reservation_id(self, reservation_id: int) -> Sequence[DriverRecord]:
        """Lista todos los conductores de una reservación por ID."""
        return [
            d for d in self._drivers.values()
            if d.reservation_id == reservation_id
        ]

    async def get_primary_driver(self, reservation_code: str) -> DriverRecord | None:
        """Obtiene el conductor principal de una reservación."""
        drivers = await self.list_by_reservation(reservation_code)
        for driver in drivers:
            if driver.is_primary_driver:
                return driver
        return drivers[0] if drivers else None

    async def update(self, driver: DriverRecord) -> DriverRecord:
        """Actualiza un conductor existente."""
        if driver.id is None or driver.id not in self._drivers:
            raise ValueError("Driver not found")
        self._drivers[driver.id] = driver
        return driver

    async def delete(self, driver_id: int) -> None:
        """Elimina un conductor por ID."""
        if driver_id in self._drivers:
            driver = self._drivers[driver_id]
            res_code = driver.reservation_code or str(driver.reservation_id)
            if res_code in self._by_reservation:
                self._by_reservation[res_code] = [
                    did for did in self._by_reservation[res_code] if did != driver_id
                ]
            del self._drivers[driver_id]

    async def delete_by_reservation(self, reservation_code: str) -> int:
        """Elimina todos los conductores de una reservación."""
        driver_ids = self._by_reservation.get(reservation_code, [])
        count = len(driver_ids)
        for driver_id in driver_ids:
            if driver_id in self._drivers:
                del self._drivers[driver_id]
        self._by_reservation[reservation_code] = []
        return count

    async def set_primary_driver(self, reservation_code: str, driver_id: int) -> None:
        """Establece un conductor como principal."""
        driver_ids = self._by_reservation.get(reservation_code, [])
        for did in driver_ids:
            if did in self._drivers:
                self._drivers[did].is_primary_driver = (did == driver_id)

    def clear(self) -> None:
        """Limpia todos los datos (para testing)."""
        self._drivers.clear()
        self._by_reservation.clear()
        self._next_id = 1
