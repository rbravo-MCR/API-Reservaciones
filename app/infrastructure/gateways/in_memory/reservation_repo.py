from typing import Sequence

from app.application.interfaces.reservation_repo import (
    ContactInput,
    DriverInput,
    ReservationInput,
    ReservationRepo,
)


class InMemoryReservationRepo(ReservationRepo):
    def __init__(self) -> None:
        self.reservations: dict[str, ReservationInput] = {}
        self.contacts: dict[str, list[ContactInput]] = {}
        self.drivers: dict[str, list[DriverInput]] = {}
        self.supplier_codes: dict[str, str] = {}

    async def get_by_code(self, reservation_code: str) -> ReservationInput | None:
        return self.reservations.get(reservation_code)

    async def create_reservation(
        self,
        reservation: ReservationInput,
        contacts: Sequence[ContactInput],
        drivers: Sequence[DriverInput],
    ) -> None:
        # Simple collision prevention in memory
        if reservation.reservation_code in self.reservations:
            raise ValueError("Reservation code already exists")
        self.reservations[reservation.reservation_code] = reservation
        self.contacts[reservation.reservation_code] = list(contacts)
        self.drivers[reservation.reservation_code] = list(drivers)

    async def update_payment_status(
        self,
        reservation_code: str,
        payment_status: str,
        expected_lock_version: int | None = None,
    ) -> None:
        if reservation_code not in self.reservations:
            raise ValueError("Reservation not found")
        if (
            expected_lock_version is not None
            and self.reservations[reservation_code].lock_version != expected_lock_version
        ):
            raise ValueError("lock_version mismatch")
        self.reservations[reservation_code].lock_version += 1
        self.reservations[reservation_code].payment_status = payment_status

    async def update_status(
        self,
        reservation_code: str,
        status: str,
        expected_lock_version: int | None = None,
    ) -> None:
        if reservation_code not in self.reservations:
            raise ValueError("Reservation not found")
        if (
            expected_lock_version is not None
            and self.reservations[reservation_code].lock_version != expected_lock_version
        ):
            raise ValueError("lock_version mismatch")
        self.reservations[reservation_code].lock_version += 1
        self.reservations[reservation_code].status = status

    async def mark_confirmed(
        self,
        reservation_code: str,
        supplier_reservation_code: str,
        supplier_confirmed_at: str,
        expected_lock_version: int | None = None,
    ) -> None:
        if reservation_code not in self.reservations:
            raise ValueError("Reservation not found")
        if (
            expected_lock_version is not None
            and self.reservations[reservation_code].lock_version != expected_lock_version
        ):
            raise ValueError("lock_version mismatch")
        self.reservations[reservation_code].lock_version += 1
        self.reservations[reservation_code].status = "CONFIRMED"
        self.reservations[reservation_code].supplier_reservation_code = supplier_reservation_code
        self.reservations[reservation_code].supplier_confirmed_at = supplier_confirmed_at
        self.supplier_codes[reservation_code] = supplier_reservation_code
