from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SupplierBookingResult:
    status: str  # SUCCESS, FAILED
    supplier_reservation_code: str | None = None
    payload: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    http_status: int | None = None


class SupplierGateway(ABC):
    @abstractmethod
    async def book(
        self,
        reservation_code: str,
        idem_key: str,
        reservation_snapshot: dict[str, Any] | None = None,
    ) -> SupplierBookingResult:
        """
        Confirms the booking with the external supplier.
        """
        pass

    @abstractmethod
    async def confirm_booking(self, reservation_code: str, details: dict[str, Any]) -> str:
        """
        Legacy/Simplified interface compatibility.
        """
        pass
